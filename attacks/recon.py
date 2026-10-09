#!/usr/bin/env python3
"""
attacks/recon.py — Reconnaissance / port‑scanning simulation.

Runs Nmap scans and netcat banner grabs against the Cowrie honeypot.
Minimal or zero login attempts — this is pure network reconnaissance.
"""

import argparse
import random
import subprocess
import sys
import time

from common import validate_target

# Nmap scan‑type flags and their descriptions (for logging)
SCAN_TYPES = [
    ["-sT"],                    # TCP connect scan
    ["-sS"],                    # SYN stealth scan (needs root in container)
    ["-sV"],                    # Version detection
    ["-sT", "-sV"],             # Connect + version
    ["-sS", "-sV"],             # SYN + version
]

TIMING_FLAGS = ["-T2", "-T3", "-T4", "-T5"]

PORT_SPECS = [
    "22",
    "2222",
    "22,23",
    "2222,2223",
    "22,23,80,443,2222,2223",
    "1-1024",
    "2200-2250",
    "22,2222,8080,8443",
]


def nmap_scan(target: str, rng: random.Random) -> None:
    """Run a single randomised Nmap scan."""
    scan_type = rng.choice(SCAN_TYPES)
    timing = rng.choice(TIMING_FLAGS)
    ports = rng.choice(PORT_SPECS)
    extra = []
    if rng.random() < 0.5:
        extra.append("-Pn")           # skip host‑discovery ping
    if rng.random() < 0.3:
        extra.append("--open")        # only show open ports

    cmd = ["nmap"] + scan_type + [timing, "-p", ports] + extra + [target]
    print(f"  [nmap] {' '.join(cmd)}")
    try:
        subprocess.run(cmd, timeout=60, capture_output=True)
    except subprocess.TimeoutExpired:
        print("  [nmap] timed out")
    except FileNotFoundError:
        print("  [nmap] nmap not found — skipping", file=sys.stderr)


def netcat_banner(target: str, port: int, rng: random.Random) -> None:
    """Connect with netcat and grab the SSH banner."""
    timeout = rng.randint(2, 5)
    cmd = ["nc", "-w", str(timeout), "-v", target, str(port)]
    print(f"  [nc] {' '.join(cmd)}")
    try:
        subprocess.run(cmd, timeout=timeout + 2, capture_output=True)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def run(target: str, port: int, seed: int,
        num_scans: int, num_banners: int) -> dict:
    """Execute a reconnaissance campaign."""
    rng = random.Random(seed)

    actions: list = []
    for _ in range(num_scans):
        actions.append(("nmap", None))
    for _ in range(num_banners):
        p = rng.choice([port, 2223]) if port == 2222 else port
        actions.append(("nc", p))
    rng.shuffle(actions)

    for action_type, action_port in actions:
        delay = rng.uniform(0.5, 3.0)
        time.sleep(delay)
        if action_type == "nmap":
            nmap_scan(target, rng)
        else:
            netcat_banner(target, action_port, rng)

    return {
        "nmap_scans": num_scans,
        "banner_grabs": num_banners,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconnaissance / port scan simulation")
    parser.add_argument("--target", required=True)
    parser.add_argument("--port",   type=int, default=2222)
    parser.add_argument("--seed",   type=int, required=True)
    parser.add_argument("--num-scans",   type=int, default=0,
                        help="Nmap scans (0 = random 2-5)")
    parser.add_argument("--num-banners", type=int, default=0,
                        help="Netcat banner grabs (0 = random 1-4)")
    args = parser.parse_args()

    validate_target(args.target)

    rng = random.Random(args.seed)
    num_scans   = args.num_scans   if args.num_scans   > 0 else rng.randint(2, 5)
    num_banners = args.num_banners if args.num_banners > 0 else rng.randint(1, 4)

    print(f"[recon] seed={args.seed}  scans={num_scans}  banners={num_banners}")
    result = run(args.target, args.port, args.seed, num_scans, num_banners)
    print(f"[recon] Done. {result}")


if __name__ == "__main__":
    main()
