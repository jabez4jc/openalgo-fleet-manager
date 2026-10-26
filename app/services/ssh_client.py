import base64
import io
import logging
import time
from datetime import datetime, timezone

import paramiko
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

from app.config import SCRIPTS_REPO_URL, SCRIPTS_REPO_PATH, SCRIPTS_REF
from app.encryption import decrypt_value

logger = logging.getLogger("fleetmgr.ssh")


def unlock_private_key(key_text: str, passphrase: str = "") -> str:
    """Any OpenSSH or PEM private key (RSA, ed25519, ECDSA), unlocked with its
    passphrase, as an unencrypted OpenSSH key. Stored keys are already encrypted
    at rest, and jobs run unattended, so the passphrase is not kept.
    Raises ValueError with a message fit for the form."""
    data, password = key_text.strip().encode(), passphrase.encode() or None
    load = serialization.load_ssh_private_key if b"OPENSSH PRIVATE KEY" in data else serialization.load_pem_private_key
    try:
        key = load(data, password)
    except TypeError as e:  # passphrase missing, or given for a key that has none
        if password is None:
            raise ValueError("This SSH key has a passphrase - enter it in the SSH Key Passphrase field") from e
        key = load(data, None)
    except (ValueError, UnsupportedAlgorithm) as e:
        if password:
            raise ValueError("The SSH key passphrase is wrong (or the key is damaged)") from e
        raise ValueError("Not a valid SSH private key - paste the whole file, including the BEGIN/END lines") from e
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                             serialization.NoEncryption()).decode()


def parse_host_keys(text: str) -> list[tuple[str, paramiko.PKey]]:
    """Host keys from ssh-keyscan output or .pub lines ("[host] type base64 [comment]").
    Raises ValueError when no line holds a usable key."""
    keys = []
    for line in (text or "").splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if len(parts) > 2 and not parts[0].startswith(("ssh-", "ecdsa-", "sk-")):
            parts = parts[1:]  # drop the hostname ssh-keyscan puts first
        try:
            keys.append((parts[0], paramiko.PKey.from_type_string(parts[0], base64.b64decode(parts[1]))))
        except Exception:
            continue
    if not keys:
        raise ValueError('Host key not recognised - paste a line of `ssh-keyscan <host>` output, e.g. "host ssh-ed25519 AAAA..."')
    return keys


def check_ssh_fields(key_text: str, passphrase: str, host_key: str) -> tuple[str | None, str | None]:
    """Form input -> (unlocked key or None, host key text or None); ValueError on bad input."""
    pem = unlock_private_key(key_text, passphrase) if key_text.strip() else None
    host_key = host_key.strip() or None
    if host_key:
        parse_host_keys(host_key)
    return pem, host_key


class SSHClient:
    def __init__(self, host: str, port: int, username: str, private_key_pem: str, host_key: str | None = None):
        self.host = host
        self.port = port
        self.username = username
        self.private_key_pem = private_key_pem
        self.host_key = host_key
        self._client: paramiko.SSHClient | None = None

    def connect(self):
        # Keys saved before unlock_private_key existed may be RSA PEM or passphrase-protected.
        try:
            pem = unlock_private_key(self.private_key_pem)
        except ValueError as e:
            raise ValueError(f"{e}. Re-enter the key on the server's Edit page.") from e
        for key_class in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
            try:
                pkey = key_class.from_private_key(io.StringIO(pem))
                break
            except paramiko.SSHException:
                continue
        else:
            raise ValueError("Unsupported SSH key type - use an ed25519, ECDSA or RSA key")

        self._client = paramiko.SSHClient()
        if self.host_key:
            name = self.host if self.port == 22 else f"[{self.host}]:{self.port}"
            for key_type, key in parse_host_keys(self.host_key):
                self._client.get_host_keys().add(name, key_type, key)
        else:
            self._client.set_missing_host_key_policy(paramiko.RejectPolicy())

        self._client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            pkey=pkey,
            timeout=30,
            look_for_keys=False,
            allow_agent=False,
        )

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def _run(self, command: str, timeout: int = 900) -> tuple[int, str, str]:
        if not self._client:
            raise RuntimeError("SSH not connected")
        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return exit_code, out, err

    def git_sync_then_invoke(self, command: str, timeout: int = 900) -> tuple[int, str]:
        sync_cmd = (
            f"if [ -d {SCRIPTS_REPO_PATH}/.git ]; then "
            f"sudo git -C {SCRIPTS_REPO_PATH} fetch --quiet origin && "
            f"sudo git -C {SCRIPTS_REPO_PATH} reset --hard 'origin/{SCRIPTS_REF}'; "
            f"else "
            f"sudo git clone --quiet -b '{SCRIPTS_REF}' {SCRIPTS_REPO_URL} {SCRIPTS_REPO_PATH}; "
            f"fi"
        )
        logger.info("SSH %s: running git-sync", self.host)
        exit_code, out, err = self._run(sync_cmd, timeout=30)
        combined = out + ("\n" + err if err else "")
        if exit_code != 0:
            logger.error("SSH %s: git-sync failed (exit %d): %s", self.host, exit_code, combined[:500])
            return exit_code, combined

        logger.info("SSH %s: invoking: %s", self.host, command[:120])
        exit_code, out, err = self._run(command, timeout=timeout)
        combined = out + ("\n" + err if err else "")
        return exit_code, combined

    def run_script(self, script_name: str, args: str = "", timeout: int = 900) -> tuple[int, str]:
        cmd = f"sudo bash {SCRIPTS_REPO_PATH}/{script_name} {args}"
        return self.git_sync_then_invoke(cmd, timeout=timeout)

    def write_temp_file(self, content: str, remote_path: str):
        sftp = self._client.open_sftp()
        try:
            f = sftp.open(remote_path, "w")
            f.write(content)
            f.close()
            sftp.chmod(remote_path, 0o600)
        finally:
            sftp.close()

    def delete_temp_file(self, remote_path: str):
        self._run(f"shred -u {remote_path} 2>/dev/null || rm -f {remote_path}", timeout=10)

    def set_admin_password(self, username: str, password: str):
        api_path = "/usr/local/bin/openalgo-restart-api.py"
        check_cmd = f"test -f {api_path} && echo 'exists' || echo 'missing'"
        _, out, _ = self._run(check_cmd, timeout=10)
        if "missing" in out:
            return 1, "openalgo-restart-api.py not found at /usr/local/bin"

        cmd = f"sudo python3 {api_path} --set-admin-password --username {username} --password-stdin"
        stdin, stdout, stderr = self._client.exec_command(cmd, timeout=15)
        stdin.write(password)
        stdin.close()
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return exit_code, out + err
