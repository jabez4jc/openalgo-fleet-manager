import io
import logging
import time
from datetime import datetime, timezone

import paramiko

from app.config import SCRIPTS_REPO_URL, SCRIPTS_REPO_PATH, SCRIPTS_REF
from app.encryption import decrypt_value

logger = logging.getLogger("fleetmgr.ssh")


class SSHClient:
    def __init__(self, host: str, port: int, username: str, private_key_pem: str, host_key: str | None = None):
        self.host = host
        self.port = port
        self.username = username
        self.private_key_pem = private_key_pem
        self.host_key = host_key
        self._client: paramiko.SSHClient | None = None

    def connect(self):
        key_file = io.StringIO(self.private_key_pem)
        pkey = paramiko.RSAKey.from_private_key(key_file)

        self._client = paramiko.SSHClient()
        if self.host_key:
            key_type, key_data = self.host_key.split(" ", 1)
            self._client.get_host_keys().add(self.host, key_type, paramiko.PKey.from_type_string(key_type, key_data.encode()))
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
