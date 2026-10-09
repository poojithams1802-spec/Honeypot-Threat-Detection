import os
import pandas as pd
import numpy as np
import random
from ml.config import FEATURE_COLUMNS, LABELS

def generate_synthetic_data(out_path, runs_per_class=40, seed=42):
    np.random.seed(seed)
    random.seed(seed)
    
    rows = []
    
    # We want multiple sessions per run. We will do 1 to 5 sessions per run.
    run_counter = 1
    
    for label in LABELS:
        for _ in range(runs_per_class):
            run_id = f"syn_run_{run_counter}"
            run_counter += 1
            num_sessions = np.random.randint(1, 6)
            
            for _ in range(num_sessions):
                # Base features
                row = {col: 0.0 for col in FEATURE_COLUMNS}
                row['label'] = label
                row['run_id'] = run_id
                
                # Introduce some noise and overlap
                if label == 'normal':
                    row['duration_sec'] = np.clip(np.random.normal(15, 5), 2, 60)
                    row['protocol'] = 0
                    row['has_client_version'] = 1
                    row['n_login_success'] = 1
                    row['n_login_failed'] = np.random.randint(0, 2)
                    row['login_success_ratio'] = row['n_login_success'] / (row['n_login_success'] + row['n_login_failed'] + 1e-5)
                    row['n_unique_usernames'] = 1
                    row['n_unique_passwords'] = 1 + row['n_login_failed']
                    row['n_commands'] = np.clip(np.random.normal(4, 2), 1, 10)
                    row['n_unique_commands'] = max(1, row['n_commands'] - np.random.randint(0, 2))
                    row['n_failed_commands'] = 0
                    row['avg_command_length'] = np.clip(np.random.normal(6, 2), 2, 20)
                    
                elif label == 'recon':
                    row['duration_sec'] = np.clip(np.random.normal(2, 1), 0.1, 5)
                    row['has_client_version'] = np.random.choice([0, 1])
                    row['no_login_attempted'] = 1 if np.random.rand() > 0.1 else 0
                    if row['no_login_attempted'] == 0:
                        row['n_login_failed'] = 1
                        row['n_unique_usernames'] = 1
                        row['n_unique_passwords'] = 1
                    row['ip_sessions_last_60s'] = np.random.randint(1, 10)
                    row['ip_sessions_last_300s'] = row['ip_sessions_last_60s'] + np.random.randint(0, 15)
                    
                elif label == 'brute_force':
                    row['duration_sec'] = np.clip(np.random.normal(60, 30), 10, 300)
                    row['has_client_version'] = 1
                    row['n_login_failed'] = np.clip(np.random.normal(50, 20), 5, 200)
                    row['n_login_success'] = 1 if np.random.rand() > 0.8 else 0
                    row['login_success_ratio'] = row['n_login_success'] / (row['n_login_failed'] + row['n_login_success'] + 1e-5)
                    row['n_unique_usernames'] = np.clip(np.random.randint(1, 10), 1, 10)
                    row['n_unique_passwords'] = np.clip(np.random.normal(20, 10), 5, 100)
                    row['avg_secs_between_logins'] = np.clip(np.random.normal(0.5, 0.2), 0.1, 2.0)
                    row['ip_failed_logins_last_300s'] = row['n_login_failed'] + np.random.randint(0, 100)
                    
                elif label == 'command_attack':
                    row['duration_sec'] = np.clip(np.random.normal(45, 15), 10, 120)
                    row['has_client_version'] = 1
                    row['n_login_success'] = 1
                    row['login_success_ratio'] = 1.0
                    row['n_unique_usernames'] = 1
                    row['n_unique_passwords'] = 1
                    row['n_commands'] = np.clip(np.random.normal(15, 5), 5, 30)
                    row['n_unique_commands'] = max(2, row['n_commands'] - np.random.randint(0, 5))
                    row['n_suspicious_commands'] = np.clip(np.random.normal(3, 1), 1, 6)
                    row['n_download_attempts'] = np.random.randint(0, 3)
                    row['avg_command_length'] = np.clip(np.random.normal(15, 5), 5, 50)

                # Add some global noise to avoid perfect separation
                for col in FEATURE_COLUMNS:
                    if np.random.rand() < 0.05: # 5% chance of random noise per feature
                        row[col] += np.random.normal(0, 1.0)
                        if col.startswith('n_') or col.startswith('ip_'):
                            row[col] = max(0, int(row[col]))
                            
                rows.append(row)
                
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Generated {len(df)} synthetic sessions across {run_counter-1} runs -> {out_path}")

if __name__ == "__main__":
    generate_synthetic_data("data/processed/synthetic_dataset.csv")
