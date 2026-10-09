import argparse
import os
import sys
import time
import random
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure we can import from backend and ml
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.db import Base, engine, SessionLocal
from backend.models import SessionRecord
from backend.services.model_service import model_service
from ml.config import FEATURE_COLUMNS

def clear_demo_data():
    db = SessionLocal()
    try:
        deleted = db.query(SessionRecord).filter(SessionRecord.is_demo == True).delete()
        db.commit()
        print(f"Cleared {deleted} demo records from database.")
    finally:
        db.close()

def seed_data():
    if not model_service.model_loaded:
        print("Model not loaded, cannot generate predictions. Exiting.")
        return
        
    real_data = 'data/processed/dataset.csv'
    syn_data = 'data/processed/synthetic_dataset.csv'
    
    if os.path.exists(real_data):
        df = pd.read_csv(real_data)
        print("Using real dataset for demo seeding.")
    elif os.path.exists(syn_data):
        df = pd.read_csv(syn_data)
        print("Using synthetic dataset for demo seeding.")
    else:
        print("No dataset found to seed from. Run Phase 3/4 first.")
        return
        
    # Generate random times over last 48 hours
    now = time.time()
    forty_eight_hours_ago = now - (48 * 3600)
    
    # Generate some plausible IPs
    subnets = ["192.168.1.", "10.0.0.", "172.16.5.", "45.33.12.", "8.8.8.", "1.1.1."]
    
    records = []
    
    # We will insert them batch by batch
    db = SessionLocal()
    
    try:
        print("Generating predictions and objects...")
        for i, row in df.iterrows():
            features = {col: row[col] for col in FEATURE_COLUMNS if col in row}
            pred = model_service.predict_single(features)
            
            start_time = random.uniform(forty_eight_hours_ago, now)
            duration = features.get('duration_sec', 0)
            end_time = start_time + duration
            
            subnet = random.choice(subnets)
            src_ip = f"{subnet}{random.randint(1, 254)}"
            
            rec = SessionRecord(
                session_id=f"demo_session_{i}_{int(time.time())}",
                src_ip=src_ip,
                dst_port=2222,
                protocol=0,
                start_time=start_time,
                end_time=end_time,
                duration_sec=duration,
                n_login_failed=features.get('n_login_failed'),
                n_login_success=features.get('n_login_success'),
                n_commands=features.get('n_commands'),
                usernames=["demo_user"] if features.get('n_login_failed', 0) > 0 else [],
                passwords=["demo_pass"] if features.get('n_login_failed', 0) > 0 else [],
                commands=["ls -la", "whoami"] if features.get('n_commands', 0) > 0 else [],
                features=features,
                predicted_label=pred['predicted_label'],
                probabilities=pred['class_probabilities'],
                confidence=pred['confidence'],
                threat_level=pred['threat_level'],
                anomaly_score=pred['anomaly_score'],
                is_anomalous=pred['is_anomalous'],
                model_version=model_service.model_version,
                model_mode=model_service.model_mode,
                created_at=time.time(),
                is_demo=True
            )
            records.append(rec)
            
        print(f"Inserting {len(records)} records...")
        # Make tables if they don't exist
        Base.metadata.create_all(bind=engine)
        
        db.add_all(records)
        db.commit()
        print("Demo data seeded successfully.")
    except Exception as e:
        print(f"Error seeding data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Confirm you want to run this script")
    parser.add_argument("--clear-demo", action="store_true", help="Delete all demo records and exit")
    
    args = parser.parse_args()
    
    if args.clear_demo:
        clear_demo_data()
        sys.exit(0)
        
    if not args.yes:
        print("You must pass --yes to seed demo data.")
        sys.exit(1)
        
    seed_data()
