import argparse
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
import joblib

from sklearn.model_selection import GroupShuffleSplit, GroupKFold, GridSearchCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.inspection import permutation_importance
import matplotlib.pyplot as plt
import seaborn as sns

from ml.config import FEATURE_COLUMNS, LABELS, THREAT_LEVEL
from ml.make_synthetic_dataset import generate_synthetic_data

def train_model(mode, seed):
    np.random.seed(seed)
    
    real_data_path = 'data/processed/dataset.csv'
    synthetic_data_path = 'data/processed/synthetic_dataset.csv'
    
    # Mode resolution
    if mode == 'auto':
        if os.path.exists(real_data_path):
            df_temp = pd.read_csv(real_data_path)
            counts = df_temp['label'].value_counts()
            if all(counts.get(l, 0) >= 30 for l in LABELS):
                mode = 'real'
            else:
                print("Real dataset has classes with < 30 samples. Falling back to synthetic.")
                mode = 'synthetic'
        else:
            print("Real dataset not found. Falling back to synthetic.")
            mode = 'synthetic'
            
    if mode == 'synthetic':
        if not os.path.exists(synthetic_data_path):
            generate_synthetic_data(synthetic_data_path, seed=seed)
        dataset_path = synthetic_data_path
        prefix = 'synthetic_'
        print("Using SYNTHETIC mode - pipeline test only, not valid results.")
    else:
        dataset_path = real_data_path
        prefix = ''
        print("Using REAL mode.")
        
    df = pd.read_csv(dataset_path)
    
    # Verifications
    assert not df.isnull().values.any(), "Dataset contains NaN"
    assert not np.isinf(df[FEATURE_COLUMNS].values).any(), "Dataset contains inf"
    
    extra_cols = set(df.columns) - set(FEATURE_COLUMNS) - {'label', 'run_id'}
    assert not extra_cols, f"Metadata columns found in features: {extra_cols}"
    
    # Class counts
    counts = df['label'].value_counts()
    print("Class counts:")
    print(counts)
    
    imbalance_ratio = counts.max() / max(counts.min(), 1)
    if imbalance_ratio > 3:
        print(f"WARNING: Dataset is imbalanced (ratio {imbalance_ratio:.1f})")
        
    # Split
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
    train_idx, test_idx = next(gss.split(df[FEATURE_COLUMNS], df['label'], groups=df['run_id']))
    
    df_train = df.iloc[train_idx]
    df_test = df.iloc[test_idx]
    
    train_runs = set(df_train['run_id'])
    test_runs = set(df_test['run_id'])
    assert train_runs.isdisjoint(test_runs), "Train and test runs are not disjoint!"
    
    print(f"Train runs per class: {df_train.groupby('label')['run_id'].nunique().to_dict()}")
    print(f"Test runs per class: {df_test.groupby('label')['run_id'].nunique().to_dict()}")
    
    X_train = df_train[FEATURE_COLUMNS]
    y_train = df_train['label']
    groups_train = df_train['run_id']
    
    X_test = df_test[FEATURE_COLUMNS]
    y_test = df_test['label']
    
    # Cross Validation
    gkf = GroupKFold(n_splits=5)
    
    # Models
    rf = RandomForestClassifier(class_weight="balanced", n_estimators=300, random_state=seed)
    dummy = DummyClassifier(strategy="most_frequent")
    dt = DecisionTreeClassifier(max_depth=5, random_state=seed)
    lr = Pipeline([('scaler', StandardScaler()), ('lr', LogisticRegression(max_iter=1000, random_state=seed))])
    
    # Hyperparameter search for RF
    param_grid = {
        'max_depth': [None, 8, 15],
        'min_samples_leaf': [1, 3],
        'max_features': ['sqrt', 0.5]
    }
    
    print("Running GridSearchCV for RandomForest...")
    grid_search = GridSearchCV(rf, param_grid, cv=gkf, scoring='f1_macro', n_jobs=-1)
    grid_search.fit(X_train, y_train, groups=groups_train)
    
    best_rf = grid_search.best_estimator_
    print(f"Best RF params: {grid_search.best_params_}")
    print(f"Best CV macro-F1: {grid_search.best_score_:.3f}")
    
    # Train baselines
    models = {
        'RandomForest': best_rf,
        'Dummy': dummy.fit(X_train, y_train),
        'DecisionTree': dt.fit(X_train, y_train),
        'LogisticRegression': lr.fit(X_train, y_train)
    }
    
    # Evaluation
    metrics = {}
    for name, model in models.items():
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        macro_f1 = f1_score(y_test, y_pred, average='macro', zero_division=0)
        weighted_f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
        metrics[name] = {'accuracy': acc, 'macro_f1': macro_f1, 'weighted_f1': weighted_f1}
        
    print("Test Metrics:", metrics)
    
    # Visualizations
    os.makedirs('docs/figures', exist_ok=True)
    
    # Confusion Matrix
    y_pred_rf = best_rf.predict(X_test)
    cm = confusion_matrix(y_test, y_pred_rf, labels=LABELS)
    plt.figure(figsize=(8,6))
    sns.heatmap(cm, annot=True, fmt='d', xticklabels=LABELS, yticklabels=LABELS)
    if mode == 'synthetic':
        plt.title('SYNTHETIC - pipeline test only\nConfusion Matrix')
    else:
        plt.title('Confusion Matrix')
    plt.ylabel('True')
    plt.xlabel('Predicted')
    plt.tight_layout()
    plt.savefig(f'docs/figures/{prefix}confusion_matrix.png')
    plt.close()
    
    # Feature Importance
    importances = best_rf.feature_importances_
    indices = np.argsort(importances)[::-1]
    plt.figure(figsize=(10,8))
    plt.bar(range(len(FEATURE_COLUMNS)), importances[indices])
    plt.xticks(range(len(FEATURE_COLUMNS)), [FEATURE_COLUMNS[i] for i in indices], rotation=90)
    if mode == 'synthetic':
        plt.title('SYNTHETIC - pipeline test only\nFeature Importance (Impurity)')
    else:
        plt.title('Feature Importance (Impurity)')
    plt.tight_layout()
    plt.savefig(f'docs/figures/{prefix}feature_importance.png')
    plt.close()
    
    # Permutation Importance
    perm_importance = permutation_importance(best_rf, X_test, y_test, n_repeats=5, random_state=seed, n_jobs=-1)
    perm_indices = np.argsort(perm_importance.importances_mean)[::-1][:15]
    plt.figure(figsize=(10,8))
    plt.bar(range(15), perm_importance.importances_mean[perm_indices])
    plt.xticks(range(15), [FEATURE_COLUMNS[i] for i in perm_indices], rotation=90)
    if mode == 'synthetic':
        plt.title('SYNTHETIC - pipeline test only\nPermutation Importance (Top 15)')
    else:
        plt.title('Permutation Importance (Top 15)')
    plt.tight_layout()
    plt.savefig(f'docs/figures/{prefix}permutation_importance.png')
    plt.close()
    
    # Leakage Checks
    leakage_findings = []
    
    # (i) Single feature > 95% accuracy
    for col in FEATURE_COLUMNS:
        stump = DecisionTreeClassifier(max_depth=1, random_state=seed)
        stump.fit(X_train[[col]], y_train)
        score = stump.score(X_test[[col]], y_test)
        if score > 0.95:
            leakage_findings.append(f"LEAKAGE WARNING: Feature '{col}' alone achieves {score*100:.1f}% accuracy.")
            
    # (ii) Drop top 3 features
    top_3_features = [FEATURE_COLUMNS[i] for i in indices[:3]]
    X_train_dropped = X_train.drop(columns=top_3_features)
    X_test_dropped = X_test.drop(columns=top_3_features)
    rf_dropped = RandomForestClassifier(class_weight="balanced", n_estimators=300, random_state=seed)
    rf_dropped.fit(X_train_dropped, y_train)
    y_pred_dropped = rf_dropped.predict(X_test_dropped)
    f1_dropped = f1_score(y_test, y_pred_dropped, average='macro', zero_division=0)
    f1_drop = metrics['RandomForest']['macro_f1'] - f1_dropped
    leakage_findings.append(f"Dropping top 3 features ({', '.join(top_3_features)}) resulted in a macro-F1 drop of {f1_drop:.3f}.")
    
    # (iii) Shuffled labels
    y_train_shuffled = np.random.permutation(y_train)
    rf_shuffled = RandomForestClassifier(class_weight="balanced", n_estimators=300, random_state=seed)
    rf_shuffled.fit(X_train, y_train_shuffled)
    y_pred_shuffled = rf_shuffled.predict(X_test)
    f1_shuffled = f1_score(y_test, y_pred_shuffled, average='macro', zero_division=0)
    leakage_findings.append(f"Sanity check: Training on shuffled labels gave macro-F1 of {f1_shuffled:.3f} (expected near chance).")
    
    # Error Analysis
    errors = df_test[y_test != y_pred_rf].copy()
    errors['predicted'] = y_pred_rf[y_test != y_pred_rf]
    common_misclassifications = errors.groupby(['label', 'predicted']).size().reset_index(name='count').sort_values('count', ascending=False)
    
    sample_errors = errors.head(5)
    
    # Report
    report_lines = [f"# Model Report ({mode.upper()})"]
    if mode == 'synthetic':
        report_lines.append("\n**SYNTHETIC - pipeline test only, not valid results.**\n")
        
    report_lines.append("## Dataset Statistics")
    report_lines.append(f"- Train runs: {len(train_runs)}")
    report_lines.append(f"- Test runs: {len(test_runs)}\n")
    
    report_lines.append("## Metrics")
    for name, m in metrics.items():
        report_lines.append(f"### {name}")
        report_lines.append(f"- Accuracy: {m['accuracy']:.3f}")
        report_lines.append(f"- Macro F1: {m['macro_f1']:.3f}")
        report_lines.append(f"- Weighted F1: {m['weighted_f1']:.3f}\n")
        
    if metrics['RandomForest']['accuracy'] > 0.99:
        report_lines.append("Note: The model scored ~100%. This likely means the attack scenarios are too easy to tell apart (especially in synthetic data). To make it harder, you could add more noise, vary command sets more organically, or blend normal behavior with attack runs.\n")
        
    report_lines.append("## Leakage Checks")
    for lf in leakage_findings:
        report_lines.append(f"- {lf}")
        
    report_lines.append("\n## Error Analysis")
    report_lines.append("Most common misclassifications (True -> Predicted):")
    for _, row in common_misclassifications.iterrows():
        report_lines.append(f"- {row['label']} -> {row['predicted']}: {row['count']} times")
        
    report_lines.append("\nSample Misclassified Sessions (True -> Predicted):")
    for _, row in sample_errors.iterrows():
        report_lines.append(f"\n**{row['label']} -> {row['predicted']}**")
        for col in FEATURE_COLUMNS:
            report_lines.append(f"- {col}: {row[col]}")
            
    with open(f'docs/{prefix}model_report.md', 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    # Save Model Bundle
    import sklearn
    bundle = {
        'model': best_rf,
        'FEATURE_COLUMNS': FEATURE_COLUMNS,
        'LABELS': LABELS,
        'THREAT_LEVEL': THREAT_LEVEL,
        'training_date': datetime.now().isoformat(),
        'sklearn_version': sklearn.__version__,
        'mode': mode,
        'row_counts': {'train': len(X_train), 'test': len(X_test)},
        'test_metrics': metrics['RandomForest']
    }
    
    os.makedirs('models', exist_ok=True)
    joblib.dump(bundle, f'models/{prefix}threat_classifier.joblib')
    
    with open(f'models/{prefix}metrics.json', 'w') as f:
        json.dump(metrics, f, indent=4)
        
    print(f"Training complete. Check docs/{prefix}model_report.md for details.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=['auto', 'real', 'synthetic'], default='auto')
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    
    train_model(args.mode, args.seed)
