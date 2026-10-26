"""Run: python tests/test_ssh_keys.py

SSH keys are checked when a server is saved, so a job never meets a key it
cannot use: any key type, with or without a passphrase, is stored unlocked
(the app encrypts it at rest), and ssh-keyscan output pins the host key.
"""
import base64, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test@localhost/test"

from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from app.services.ssh_client import check_ssh_fields, parse_host_keys, unlock_private_key


def pem(key, fmt, passphrase=None):
    enc = ser.BestAvailableEncryption(passphrase) if passphrase else ser.NoEncryption()
    return key.private_bytes(ser.Encoding.PEM, fmt, enc).decode()


def error(fn):
    try:
        fn()
    except ValueError as e:
        return str(e)
    raise AssertionError("expected ValueError")


keys = [ed25519.Ed25519PrivateKey.generate(), ec.generate_private_key(ec.SECP256R1()),
        rsa.generate_private_key(public_exponent=65537, key_size=2048)]
for key in keys:
    for fmt in (ser.PrivateFormat.OpenSSH, ser.PrivateFormat.PKCS8):
        locked = pem(key, fmt, b"secret-pw")
        for text, pw in ((pem(key, fmt), ""), (locked, "secret-pw"), (pem(key, fmt), "not-needed")):
            out = unlock_private_key(text, pw)
            assert "OPENSSH PRIVATE KEY" in out and "secret" not in out
            assert ser.load_ssh_private_key(out.encode(), None).public_key().public_bytes(
                ser.Encoding.OpenSSH, ser.PublicFormat.OpenSSH) == key.public_key().public_bytes(ser.Encoding.OpenSSH, ser.PublicFormat.OpenSSH)
        assert "passphrase" in error(lambda: unlock_private_key(locked, ""))
        assert "wrong" in error(lambda: unlock_private_key(locked, "nope"))
assert "Not a valid" in error(lambda: unlock_private_key("-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----", ""))

pub = keys[0].public_key().public_bytes(ser.Encoding.OpenSSH, ser.PublicFormat.OpenSSH).decode()
rsa_pub = keys[2].public_key().public_bytes(ser.Encoding.OpenSSH, ser.PublicFormat.OpenSSH).decode()
assert [t for t, _ in parse_host_keys(pub)] == ["ssh-ed25519"]
assert [t for t, _ in parse_host_keys(f"# 1.2.3.4:22 SSH-2.0\n1.2.3.4 {pub}\n1.2.3.4 {rsa_pub}\n")] == ["ssh-ed25519", "ssh-rsa"]
assert parse_host_keys(f"1.2.3.4 {pub}")[0][1].asbytes() == base64.b64decode(pub.split()[1])
assert "Host key" in error(lambda: parse_host_keys("server.example.com ssh-rsa not-base64!"))

assert check_ssh_fields("", "", "  ") == (None, None)
assert check_ssh_fields(pem(keys[0], ser.PrivateFormat.OpenSSH, b"pw"), "pw", pub)[1] == pub
print("ok")
