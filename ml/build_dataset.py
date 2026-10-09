import argparse
import pandas as pd
import numpy as np
import os
from ml.parse_logs import read_and_group_events, parse_iso8601
from ml.features import extract_all_features

def build_dataset(log_file, manifest_file, out_dir, report_file):
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    
    # 1. Parse logs and extract features
    print(f"Reading logs from {log_file}...")
    sessions_dict, total_lines, malformed = read_and_group_events(log_file)
    print(f"Parsed {len(sessions_dict)} sessions from {total_lines} lines ({malformed} malformed).")
    
    features_list = extract_all_features(sessions_dict)
    df_features = pd.DataFrame(features_list)
    
    if df_features.empty:
        print("No features extracted. Exiting.")
        return
        
    df_features.to_csv(os.path.join(out_dir, 'sessions_features.csv'), index=False)
    
    # 2. Read manifest
    print(f"Reading manifest from {manifest_file}...")
    try:
        df_manifest = pd.read_csv(manifest_file)
        # Parse times to timestamps
        df_manifest['start_ts'] = df_manifest['start_time_utc'].apply(parse_iso8601)
        df_manifest['end_ts'] = df_manifest['end_time_utc'].apply(parse_iso8601)
    except FileNotFoundError:
        print(f"Manifest not found: {manifest_file}")
        return
        
    # 3. Label sessions
    labels = []
    run_ids = []
    
    ambiguous_count = 0
    unlabelled_count = 0
    
    for _, row in df_features.iterrows():
        src_ip = row['src_ip']
        start_time = row['start_time']
        
        # Match condition: src_ip == attacker_ip AND start_time within [start_ts - 2, end_ts + 5]
        matches = df_manifest[
            (df_manifest['attacker_ip'] == src_ip) & 
            (start_time >= df_manifest['start_ts'] - 2) & 
            (start_time <= df_manifest['end_ts'] + 5)
        ]
        
        if len(matches) == 1:
            labels.append(matches.iloc[0]['label'])
            run_ids.append(matches.iloc[0]['run_id'])
        elif len(matches) > 1:
            labels.append('AMBIGUOUS')
            run_ids.append(None)
            ambiguous_count += 1
        else:
            labels.append('UNLABELLED')
            run_ids.append(None)
            unlabelled_count += 1
            
    df_features['label'] = labels
    df_features['run_id'] = run_ids
    
    # 4. Split datasets
    df_ambiguous = df_features[df_features['label'] == 'AMBIGUOUS']
    df_unlabelled = df_features[df_features['label'] == 'UNLABELLED']
    df_labelled = df_features[~df_features['label'].isin(['AMBIGUOUS', 'UNLABELLED'])].copy()
    
    df_unlabelled.to_csv(os.path.join(out_dir, 'unlabelled_sessions.csv'), index=False)
    
    # Separation of metadata and features for the labelled dataset
    meta_cols = ['session_id', 'src_ip', 'start_time', 'end_time']
    feature_cols = [c for c in df_labelled.columns if c not in meta_cols and c not in ['label', 'run_id']]
    
    df_meta = df_labelled[meta_cols].copy()
    df_dataset = df_labelled[feature_cols + ['label', 'run_id']].copy()
    
    df_meta.to_csv(os.path.join(out_dir, 'dataset_meta.csv'), index=False)
    df_dataset.to_csv(os.path.join(out_dir, 'dataset.csv'), index=False)
    
    # 5. Generate Report
    generate_report(df_dataset, df_manifest, report_file, ambiguous_count, unlabelled_count, malformed)
    
    print("Dataset building complete!")

def generate_report(df_dataset, df_manifest, report_file, ambiguous, unlabelled, malformed):
    lines = ["# Dataset Report\n"]
    lines.append(f"- **Malformed log lines:** {malformed}")
    lines.append(f"- **Unlabelled sessions:** {unlabelled}")
    lines.append(f"- **Ambiguous sessions (dropped):** {ambiguous}\n")
    
    if df_dataset.empty:
        lines.append("## No Labelled Data Found")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        return

    lines.append("## Class Distribution\n")
    class_counts = df_dataset['label'].value_counts()
    for cls, count in class_counts.items():
        lines.append(f"- **{cls}:** {count} sessions")
        if count < 30:
            lines.append(f"  - ⚠️ WARNING: Class '{cls}' has fewer than 30 sessions.")

    lines.append("\n## Feature Statistics per Class\n")
    feature_cols = [c for c in df_dataset.columns if c not in ['label', 'run_id']]

    grouped = df_dataset.groupby('label')
    for cls, group in grouped:
        lines.append(f"### {cls}\n")
        lines.append("| Feature | Min | Mean | Max |")
        lines.append("|---|---|---|---|")
        for col in feature_cols:
            cmin = group[col].min()
            cmean = group[col].mean()
            cmax = group[col].max()
            lines.append(f"| {col} | {cmin:.2f} | {cmean:.2f} | {cmax:.2f} |")
        lines.append("\n")

    # Check for perfect separation
    lines.append("## Potential Leakage Warnings\n")
    warnings = []
    classes = df_dataset['label'].unique()
    if len(classes) > 1:
        for col in feature_cols:
            # Simple heuristic: if min of one class > max of all others, it perfectly separates
            for cls in classes:
                cls_min = df_dataset[df_dataset['label'] == cls][col].min()
                other_max = df_dataset[df_dataset['label'] != cls][col].max()
                if cls_min > other_max:
                    warnings.append(f"- Feature `{col}` perfectly separates class `{cls}` (min {cls_min} > max {other_max}).")

    if warnings:
        lines.extend(warnings)
    else:
        lines.append("No obvious single-feature perfect separation detected.")

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--report-file", default="docs/dataset_report.md")
    args = parser.parse_args()
    
    build_dataset(args.logs, args.manifest, args.out_dir, args.report_file)
