"""
attacks/common.py — Shared safety utilities for all attack scripts.

Every attack script MUST call validate_target() before doing anything
on the network. This ensures attack traffic only ever reaches the
Cowrie honeypot inside our isolated Docker network.
"""

import sys

# ── The ONLY hosts that attack scripts are allowed to target ──
# 172.28.0.10 = Cowrie container on the honeynet bridge network
# 127.0.0.1   = Cowrie published on the host loopback (Phase 1 legacy)
ALLOWED_TARGETS = frozenset({"172.28.0.10", "127.0.0.1"})

# ── Cowrie default credentials (from default etc/userdb.txt) ──
# These are username/password pairs that Cowrie's default userdb accepts.
# Used by normal.py and command_attack.py to log in successfully.
VALID_CREDENTIALS = [
    ("root", ""),           # root with empty password
    ("root", "123456"),
    ("root", "password"),
    ("root", "root"),
    ("root", "admin"),
    ("root", "qwerty"),
    ("admin", "admin"),
    ("admin", "password"),
    ("admin", "1234"),
    ("test", "test"),
    ("test", "password"),
    ("user", ""),           # user with empty password
]

# ── Common usernames for brute-force wordlists ──
COMMON_USERNAMES = [
    "root", "admin", "test", "user", "ubuntu", "guest",
    "oracle", "ftp", "www", "mysql", "postgres", "pi",
    "deploy", "ansible", "vagrant", "ec2-user", "centos",
    "nagios", "operator", "backup", "service", "daemon",
]

# ── Common passwords for brute-force wordlists ──
COMMON_PASSWORDS = [
    "123456", "password", "root", "admin", "toor", "qwerty",
    "letmein", "abc123", "monkey", "master", "dragon", "login",
    "iloveyou", "alpine", "1234", "12345", "test", "guest",
    "changeme", "passw0rd", "welcome", "shadow", "sunshine",
    "trustno1", "batman", "access", "hello", "charlie",
    "donald", "654321", "ashley", "michael", "123123",
    "P@ssw0rd", "pass123", "qwerty123", "admin123", "root123",
    "", "ftpuser", "uploader", "user", "ftp123",
]


def validate_target(target: str) -> None:
    """Abort the script immediately if *target* is not in the allowlist.

    This is a hard safety guard — no flags, env-vars, or arguments can
    override it. If someone accidentally points an attack script at a
    real host, it will refuse to run.
    """
    if target not in ALLOWED_TARGETS:
        print(
            f"[SAFETY] BLOCKED — target '{target}' is NOT in the allowlist.\n"
            f"         Allowed targets: {sorted(ALLOWED_TARGETS)}\n"
            f"         Aborting to prevent accidental damage.",
            file=sys.stderr,
        )
        sys.exit(1)
    # Passed — print confirmation so the operator sees the guard fired.
    print(f"[SAFETY] Target '{target}' is allowed. Proceeding.")
