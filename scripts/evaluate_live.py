"""
scripts/evaluate_live.py
=========================
Evaluate live prediction accuracy by joining stored sessions to the run manifest.

Requires data/raw/run_manifest.csv to exist (same format as training).
Ground truth from the manifest is used ONLY for evaluation; it is never
used as a feature.

Usage
-----
    python scripts/evaluate_live.py [--manifest PATH] [--hours H]
"""

import argparse
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("evaluate_live")

DEFAULT_MANIFEST = os.path.join("data", "raw", "run_manifest.csv")


def main():
    parser = argparse.ArgumentParser(description="Live prediction accuracy evaluator")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST,
                        help=f"Path to run_manifest.csv (default: {DEFAULT_MANIFEST})")
    parser.add_argument("--hours", type=float, default=24,
                        help="Evaluate sessions from the last N hours (default: 24)")
    parser.add_argument("--include-demo", action="store_true",
                        help="Include demo/replay sessions in evaluation")
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        logger.error("Manifest not found: %s", args.manifest)
        logger.error("Skipping evaluation (manifest is optional).")
        sys.exit(0)

    import time
    import pandas as pd
    from collections import Counter

    from backend.db import SessionLocal, Base, engine, init_db
    from backend.models import SessionRecord
    from ml.build_dataset import parse_iso8601

    init_db(engine)

    # Load manifest
    df_manifest = pd.read_csv(args.manifest)
    df_manifest["start_ts"] = df_manifest["start_time_utc"].apply(parse_iso8601)
    df_manifest["end_ts"] = df_manifest["end_time_utc"].apply(parse_iso8601)

    # Load sessions from DB
    cutoff = time.time() - args.hours * 3600
    db = SessionLocal()
    try:
        q = db.query(SessionRecord).filter(SessionRecord.start_time >= cutoff)
        if not args.include_demo:
            q = q.filter(SessionRecord.is_demo == False)  # noqa: E712
        rows = q.all()
    finally:
        db.close()

    if not rows:
        logger.info("No sessions found in the last %.0f hours.", args.hours)
        return

    # Join with manifest (same rule as build_dataset.py)
    matched_true = []
    matched_pred = []

    for row in rows:
        src_ip = row.src_ip
        start_time = row.start_time
        matches = df_manifest[
            (df_manifest["attacker_ip"] == src_ip) &
            (start_time >= df_manifest["start_ts"] - 2) &
            (start_time <= df_manifest["end_ts"] + 5)
        ]
        if len(matches) == 1:
            true_label = matches.iloc[0]["label"]
            pred_label = row.predicted_label
            if pred_label is not None:
                matched_true.append(true_label)
                matched_pred.append(pred_label)

    if not matched_true:
        logger.info(
            "No sessions matched the manifest (checked %d sessions).", len(rows)
        )
        return

    logger.info(
        "Matched %d sessions out of %d stored.", len(matched_true), len(rows)
    )

    # Accuracy
    correct = sum(t == p for t, p in zip(matched_true, matched_pred))
    accuracy = correct / len(matched_true)
    print(f"\n=== Live Accuracy Report ===")
    print(f"Sessions evaluated : {len(matched_true)}")
    print(f"Overall accuracy   : {accuracy:.3f} ({correct}/{len(matched_true)})")

    # Per-class recall
    labels = sorted(set(matched_true))
    print("\nPer-class recall:")
    for lbl in labels:
        total_lbl = matched_true.count(lbl)
        recall = sum(
            1 for t, p in zip(matched_true, matched_pred) if t == lbl and p == lbl
        ) / total_lbl if total_lbl else 0
        print(f"  {lbl:<20} recall={recall:.3f} (support={total_lbl})")

    # Confusion matrix
    print("\nConfusion matrix (rows=true, cols=predicted):")
    header = f"{'':20}" + "".join(f"{l:>15}" for l in labels)
    print(header)
    for true_lbl in labels:
        row_str = f"{true_lbl:<20}"
        for pred_lbl in labels:
            count = sum(
                1 for t, p in zip(matched_true, matched_pred)
                if t == true_lbl and p == pred_lbl
            )
            row_str += f"{count:>15}"
        print(row_str)

    print()


if __name__ == "__main__":
    main()
