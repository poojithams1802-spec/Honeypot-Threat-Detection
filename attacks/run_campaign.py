#!/usr/bin/env python3
"""
attacks/run_campaign.py — Campaign orchestrator for labelled attack runs.

Launches attack scripts inside the Docker attacker containers via
`docker compose exec`, rotating across attacker IPs, and records
every run with ground-truth labels to data/raw/run_manifest.csv.

Usage:
    python attacks/run_campaign.py --runs-per-class 1 --seed 42
    python attacks/run_campaign.py --runs-per-class 40 --seed 1337 \
        --classes normal,recon,brute_force,command_attack
"""

import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Project paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "raw" / "run_manifest.csv"

# ── Attacker containers and their fixed IPs ──
ATTACKER_CONTAINERS = [
    ("attacker-1", "172.28.0.21"),
    ("attacker-2", "172.28.0.22"),
    ("attacker-3", "172.28.0.23"),
    ("attacker-4", "172.28.0.24"),
]

COWRIE_TARGET = "172.28.0.10"

# ── Scenario definitions ──
# Maps class label → (script file, manifest label)
# "mixed" is labelled "command_attack" because that's what it fundamentally is.
SCENARIOS = {
    "normal": {
        "script": "normal.py",
        "label": "normal",
    },
    "recon": {
        "script": "recon.py",
        "label": "recon",
    },
    "brute_force": {
        "script": "brute_force.py",
        "label": "brute_force",
    },
    "command_attack": {
        "script": "command_attack.py",
        "label": "command_attack",
    },
}

# For command_attack class, randomly pick between command_attack.py and mixed.py
# to add variety. Both get the label "command_attack".
COMMAND_ATTACK_SCRIPTS = ["command_attack.py", "mixed.py"]

MANIFEST_FIELDS = [
    "run_id", "label", "scenario_script", "attacker_ip", "target",
    "start_time_utc", "end_time_utc", "seed", "parameters_json",
]


def ensure_manifest_exists() -> None:
    """Create the manifest CSV with headers if it doesn't exist yet."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()


def append_manifest_row(row: dict) -> None:
    """Append a single run record to the manifest CSV."""
    with open(MANIFEST_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writerow(row)


def docker_compose_cmd() -> list[str]:
    """Return the docker compose command prefix."""
    # Try 'docker compose' (v2 plugin) first; fall back to 'docker-compose'
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, check=True,
        )
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["docker-compose"]


def exec_attack(container: str, script: str, target: str, seed: int,
                extra_args: list[str], compose_cmd: list[str]) -> tuple[str, str]:
    """Run an attack script inside a container. Return (start_utc, end_utc)."""
    cmd = compose_cmd + [
        "exec", "-T", container,
        "python3", f"/attacks/{script}",
        "--target", target,
        "--seed", str(seed),
    ] + extra_args

    start_utc = datetime.now(timezone.utc).isoformat()
    print(f"    $ {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd, timeout=300, capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
        )
        # Stream output for visibility
        if result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                print(f"      {line}")
        if result.stderr.strip():
            for line in result.stderr.strip().split("\n"):
                print(f"      [stderr] {line}")
    except subprocess.TimeoutExpired:
        print(f"      [!] Script timed out after 300s")

    end_utc = datetime.now(timezone.utc).isoformat()
    return start_utc, end_utc


def build_run_plan(classes: list[str], runs_per_class: int,
                   rng: random.Random) -> list[dict]:
    """Build a shuffled list of run specifications."""
    runs = []
    run_id = 0

    for cls in classes:
        for i in range(runs_per_class):
            run_id += 1
            scenario = SCENARIOS[cls]

            # For command_attack, randomly pick between the two scripts
            if cls == "command_attack":
                script = rng.choice(COMMAND_ATTACK_SCRIPTS)
            else:
                script = scenario["script"]

            # Assign attacker container (round-robin across available)
            container, attacker_ip = ATTACKER_CONTAINERS[
                (run_id - 1) % len(ATTACKER_CONTAINERS)
            ]

            # Generate a unique per-run seed derived from the master seed
            run_seed = rng.randint(1, 2**31 - 1)

            runs.append({
                "run_id": f"run_{run_id:04d}",
                "cls": cls,
                "label": scenario["label"],
                "script": script,
                "container": container,
                "attacker_ip": attacker_ip,
                "run_seed": run_seed,
            })

    # Shuffle run order across all classes
    rng.shuffle(runs)
    return runs


def run_campaign(classes: list[str], runs_per_class: int,
                 master_seed: int) -> None:
    """Orchestrate the full campaign."""
    rng = random.Random(master_seed)
    compose_cmd = docker_compose_cmd()
    ensure_manifest_exists()

    run_plan = build_run_plan(classes, runs_per_class, rng)
    total = len(run_plan)

    print(f"{'='*60}")
    print(f"  Campaign: {total} runs  ({runs_per_class}/class × {len(classes)} classes)")
    print(f"  Classes:  {classes}")
    print(f"  Seed:     {master_seed}")
    print(f"  Manifest: {MANIFEST_PATH}")
    print(f"{'='*60}\n")

    for idx, spec in enumerate(run_plan, 1):
        # Random inter-run gap (5-20 s) to avoid overlapping time windows
        if idx > 1:
            gap = rng.uniform(5.0, 20.0)
            print(f"  [gap] Waiting {gap:.1f}s before next run...")
            time.sleep(gap)

        print(f"\n[{idx}/{total}] {spec['run_id']}  class={spec['cls']}  "
              f"label={spec['label']}  script={spec['script']}  "
              f"container={spec['container']}")

        # Build extra args (currently none; scripts use internal defaults)
        extra_args: list[str] = []

        start_utc, end_utc = exec_attack(
            container=spec["container"],
            script=spec["script"],
            target=COWRIE_TARGET,
            seed=spec["run_seed"],
            extra_args=extra_args,
            compose_cmd=compose_cmd,
        )

        # Record to manifest
        params = {
            "master_seed": master_seed,
            "run_seed": spec["run_seed"],
        }
        append_manifest_row({
            "run_id": spec["run_id"],
            "label": spec["label"],
            "scenario_script": spec["script"],
            "attacker_ip": spec["attacker_ip"],
            "target": COWRIE_TARGET,
            "start_time_utc": start_utc,
            "end_time_utc": end_utc,
            "seed": spec["run_seed"],
            "parameters_json": json.dumps(params),
        })

        print(f"  → Recorded {spec['run_id']} to manifest.")

    print(f"\n{'='*60}")
    print(f"  Campaign complete. {total} runs logged to:")
    print(f"    {MANIFEST_PATH}")
    print(f"{'='*60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrate labelled attack runs against the Cowrie honeypot")
    parser.add_argument(
        "--runs-per-class", type=int, required=True,
        help="Number of runs to generate for each class",
    )
    parser.add_argument(
        "--seed", type=int, required=True,
        help="Master random seed for reproducibility",
    )
    parser.add_argument(
        "--classes", type=str,
        default="normal,recon,brute_force,command_attack",
        help="Comma-separated list of attack classes to run",
    )
    args = parser.parse_args()

    classes = [c.strip() for c in args.classes.split(",")]
    for cls in classes:
        if cls not in SCENARIOS:
            print(f"[!] Unknown class '{cls}'. Available: {list(SCENARIOS.keys())}",
                  file=sys.stderr)
            sys.exit(1)

    run_campaign(classes, args.runs_per_class, args.seed)


if __name__ == "__main__":
    main()
