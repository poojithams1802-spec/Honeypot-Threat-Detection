#!/usr/bin/env python3
"""
attacks/normal.py — Simulate benign/legitimate SSH user behaviour.

Logs in with a valid Cowrie credential, runs a handful of harmless
commands with human-like pauses, then disconnects cleanly.
"""

import argparse
import random
import sys
import time

import paramiko

from common import VALID_CREDENTIALS, validate_target

# Harmless commands a real admin might run
HARMLESS_COMMANDS = [
    "ls",
    "ls -la",
    "ls /tmp",
    "pwd",
    "whoami",
    "id",
    "cat /etc/os-release",
    "uptime",
    "df -h",
    "free -m",
    "date",
    "hostname",
    "echo hello",
    "cat /etc/hostname",
    "w",
    "last -5",
    "ps aux",
    "env",
]


def run(target: str, port: int, seed: int, sessions: int,
        min_cmds: int, max_cmds: int) -> dict:
    """Execute 1‑N benign SSH sessions against *target*."""
    rng = random.Random(seed)
    total_cmds_run = 0

    for sess_idx in range(sessions):
        # Pick a valid credential pair
        username, password = rng.choice(VALID_CREDENTIALS)
        num_cmds = rng.randint(min_cmds, max_cmds)
        cmds = rng.sample(HARMLESS_COMMANDS, min(num_cmds, len(HARMLESS_COMMANDS)))

        print(f"  [session {sess_idx+1}/{sessions}] {username}@{target}:{port}"
              f"  cmds={len(cmds)}")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=target, port=port,
                username=username, password=password,
                timeout=10, look_for_keys=False, allow_agent=False,
            )
        except Exception as exc:
            print(f"    [!] Connection/login failed: {exc}", file=sys.stderr)
            continue

        # Execute commands with human-like pauses
        for cmd in cmds:
            pre_delay = rng.uniform(0.5, 3.0)
            time.sleep(pre_delay)
            try:
                stdin, stdout, stderr = client.exec_command(cmd)
                stdout.channel.recv_exit_status()
            except Exception:
                pass
            total_cmds_run += 1

        # Pause before disconnecting (simulating "reading output")
        time.sleep(rng.uniform(0.5, 2.0))
        client.close()

        # Optional inter-session gap
        if sess_idx < sessions - 1:
            time.sleep(rng.uniform(1.0, 4.0))

    return {
        "sessions": sessions,
        "total_commands": total_cmds_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Normal/benign SSH session simulation")
    parser.add_argument("--target", required=True, help="Target IP")
    parser.add_argument("--port",   type=int, default=2222)
    parser.add_argument("--seed",   type=int, required=True)
    parser.add_argument("--sessions", type=int, default=0,
                        help="Number of sessions (0 = random 1-3)")
    parser.add_argument("--min-cmds", type=int, default=2)
    parser.add_argument("--max-cmds", type=int, default=6)
    args = parser.parse_args()

    validate_target(args.target)

    sessions = args.sessions if args.sessions > 0 else random.Random(args.seed).randint(1, 3)
    print(f"[normal] seed={args.seed}  sessions={sessions}")

    result = run(
        target=args.target, port=args.port, seed=args.seed,
        sessions=sessions, min_cmds=args.min_cmds, max_cmds=args.max_cmds,
    )
    print(f"[normal] Done. {result}")


if __name__ == "__main__":
    main()
