"""
scripts/rescore_sessions.py
============================
Re-score sessions that were stored without a model prediction
(needs_rescore=True / predicted_label IS NULL).

Usage
-----
    python scripts/rescore_sessions.py [--dry-run] [--batch-size N]

Environment Variables
---------------------
    DATABASE_URL   SQLAlchemy URL (default: sqlite:///./data/dev.db)
    MODEL_MODE     auto | real | synthetic (default: auto)
"""

import argparse
import logging
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("rescore")


def main():
    parser = argparse.ArgumentParser(description="Re-score sessions with NULL predictions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be rescored without writing to DB",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of sessions to process per DB batch (default: 100)",
    )
    args = parser.parse_args()

    # Import after path setup
    from backend.db import SessionLocal, Base, engine, init_db
    from backend.models import SessionRecord
    from backend.services.model_service import model_service
    from ml.config import FEATURE_COLUMNS

    init_db(engine)

    if not model_service.model_loaded:
        logger.error("Model is not loaded. Cannot rescore. Exiting.")
        sys.exit(1)

    db = SessionLocal()
    try:
        q = db.query(SessionRecord).filter(
            (SessionRecord.needs_rescore == True) |  # noqa: E712
            (SessionRecord.predicted_label == None)   # noqa: E711
        )
        total = q.count()
        logger.info("Found %d sessions to rescore.", total)

        if args.dry_run:
            logger.info("Dry-run mode: no changes will be made.")
            for row in q.limit(10):
                logger.info("  Would rescore: %s (src_ip=%s)", row.session_id, row.src_ip)
            return

        rescored = 0
        errors = 0
        offset = 0

        while True:
            batch = q.offset(offset).limit(args.batch_size).all()
            if not batch:
                break

            for row in batch:
                feat_dict = row.features or {}
                if not feat_dict:
                    # Rebuild features dict from individual columns
                    feat_dict = {
                        col: (row.features or {}).get(col, 0.0)
                        for col in FEATURE_COLUMNS
                    }

                # Fill missing feature columns with 0.0
                for col in FEATURE_COLUMNS:
                    if col not in feat_dict:
                        feat_dict[col] = 0.0

                try:
                    result = model_service.predict_single(feat_dict)
                    row.predicted_label = result["predicted_label"]
                    row.probabilities = result["class_probabilities"]
                    row.confidence = result["confidence"]
                    row.threat_level = result["threat_level"]
                    row.anomaly_score = result["anomaly_score"]
                    row.is_anomalous = result["is_anomalous"]
                    row.model_version = model_service.model_version
                    row.model_mode = model_service.model_mode
                    row.needs_rescore = False
                    rescored += 1
                except Exception as exc:
                    logger.error(
                        "Failed to rescore %s: %s", row.session_id, exc
                    )
                    errors += 1

            db.commit()
            offset += args.batch_size
            logger.info("Progress: %d/%d rescored, %d errors.", rescored, total, errors)

        logger.info(
            "Rescore complete: %d updated, %d errors, %d skipped.",
            rescored, errors, total - rescored - errors,
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
