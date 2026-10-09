import argparse
import os
import pandas as pd
import numpy as np
import joblib

from sklearn.ensemble import IsolationForest
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, precision_score, recall_score, classification_report

from ml.config import FEATURE_COLUMNS, LABELS

def train_anomaly_detector(mode, seed):
    np.random.seed(seed)
    
    real_data_path = 'data/processed/dataset.csv'
    synthetic_data_path = 'data/processed/synthetic_dataset.csv'
    
    if mode == 'auto':
        if os.path.exists(real_data_path):
            df_temp = pd.read_csv(real_data_path)
            counts = df_temp['label'].value_counts()
            if all(counts.get(l, 0) >= 30 for l in LABELS):
                mode = 'real'
            else:
                mode = 'synthetic'
        else:
            mode = 'synthetic'
            
    if mode == 'synthetic':
        dataset_path = synthetic_data_path
        prefix = 'synthetic_'
        print("Using SYNTHETIC mode for anomaly detector.")
    else:
        dataset_path = real_data_path
        prefix = ''
        print("Using REAL mode for anomaly detector.")
        
    df = pd.read_csv(dataset_path)
    
    # Split using same random_state to align with train.py
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
    train_idx, test_idx = next(gss.split(df[FEATURE_COLUMNS], df['label'], groups=df['run_id']))
    
    df_train = df.iloc[train_idx]
    df_test = df.iloc[test_idx]
    
    # Train ONLY on 'normal'
    df_train_normal = df_train[df_train['label'] == 'normal']
    X_train_normal = df_train_normal[FEATURE_COLUMNS]
    
    print(f"Training IsolationForest on {len(X_train_normal)} normal sessions...")
    iso = IsolationForest(random_state=seed, contamination='auto') # Auto assumes small contamination in normal data, or we could set to 0.05
    iso.fit(X_train_normal)
    
    X_test = df_test[FEATURE_COLUMNS]
    y_test_labels = df_test['label']
    
    # Ground truth: 1 for normal (inlier), -1 for attack (outlier)
    y_true = np.where(y_test_labels == 'normal', 1, -1)
    
    # Predictions: 1 for inlier, -1 for outlier
    y_pred = iso.predict(X_test)
    
    # Anomaly scores (lower is more anomalous). We use -score_samples for ROC-AUC where higher = more anomalous.
    anomaly_scores = -iso.score_samples(X_test)
    y_true_binary = np.where(y_true == -1, 1, 0) # 1 for attack, 0 for normal
    
    roc_auc = roc_auc_score(y_true_binary, anomaly_scores)
    print(f"ROC-AUC (Anomaly Score vs Attack Label): {roc_auc:.3f}")
    
    y_pred_binary = np.where(y_pred == -1, 1, 0)
    precision = precision_score(y_true_binary, y_pred_binary)
    recall = recall_score(y_true_binary, y_pred_binary)
    
    print(f"Precision: {precision:.3f}")
    print(f"Recall: {recall:.3f}")
    
    # Per-class detection rate (recall for that specific attack class)
    print("Per-class Detection Rate (Outlier == True):")
    detection_rates = {}
    for label in LABELS:
        if label == 'normal': continue
        mask = (y_test_labels == label)
        detected = np.sum(y_pred_binary[mask])
        total = np.sum(mask)
        rate = detected / total if total > 0 else 0
        detection_rates[label] = rate
        print(f"  {label}: {rate:.1%} ({detected}/{total})")
        
    # Append to report
    report_file = f'docs/{prefix}model_report.md'
    if os.path.exists(report_file):
        with open(report_file, 'a', encoding='utf-8') as f:
            f.write("\n## Anomaly Detection (Isolation Forest)\n")
            f.write("Note: This is an auxiliary component trained only on `normal` sessions. Real-world normal traffic is highly varied, so synthetic/lab normal traffic may yield over-optimistic results.\n\n")
            f.write(f"- ROC-AUC: {roc_auc:.3f}\n")
            f.write(f"- Precision: {precision:.3f}\n")
            f.write(f"- Recall: {recall:.3f}\n\n")
            f.write("### Per-class Detection Rate\n")
            for lbl, rate in detection_rates.items():
                f.write(f"- {lbl}: {rate:.1%}\n")
                
    # Save Model Bundle
    bundle = {
        'model': iso,
        'FEATURE_COLUMNS': FEATURE_COLUMNS,
        'threshold_default': iso.offset_, # Threshold used internally by predict()
        'mode': mode
    }
    
    joblib.dump(bundle, f'models/{prefix}anomaly_detector.joblib')
    print("Anomaly detector trained and saved.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=['auto', 'real', 'synthetic'], default='auto')
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    
    train_anomaly_detector(args.mode, args.seed)
