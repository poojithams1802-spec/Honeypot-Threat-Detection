import os
import pytest
import pandas as pd
import numpy as np
import joblib

from ml.config import FEATURE_COLUMNS, THREAT_LEVEL
from ml.predict import ThreatPredictor
from sklearn.model_selection import GroupShuffleSplit

def test_split_disjointness():
    # Test GroupShuffleSplit ensures disjoint run_ids
    df = pd.DataFrame({
        'run_id': ['r1', 'r1', 'r2', 'r3', 'r3', 'r3', 'r4', 'r5'],
        'label': ['normal', 'normal', 'recon', 'brute_force', 'brute_force', 'brute_force', 'command_attack', 'normal'],
        'f1': [1,2,3,4,5,6,7,8]
    })
    
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(gss.split(df[['f1']], df['label'], groups=df['run_id']))
    
    train_runs = set(df.iloc[train_idx]['run_id'])
    test_runs = set(df.iloc[test_idx]['run_id'])
    
    assert train_runs.isdisjoint(test_runs)

def test_predictor_missing_features(tmp_path):
    # Dummy bundle
    bundle_path = tmp_path / "dummy_clf.joblib"
    bundle = {
        'model': "dummy_model",
        'FEATURE_COLUMNS': FEATURE_COLUMNS,
        'LABELS': ['normal'],
        'THREAT_LEVEL': THREAT_LEVEL
    }
    joblib.dump(bundle, bundle_path)
    
    predictor = ThreatPredictor(str(bundle_path))
    
    df_missing = pd.DataFrame({'duration_sec': [10]})
    with pytest.raises(ValueError, match="Missing required features"):
        predictor.predict(df_missing)

class MockModel:
    def __init__(self, classes_):
        self.classes_ = classes_
    def predict(self, X):
        return np.array(['command_attack'] * len(X))
    def predict_proba(self, X):
        return np.array([[0.1, 0.1, 0.1, 0.7]] * len(X))
        
class MockAnomaly:
    def predict(self, X):
        return np.array([-1] * len(X))
    def score_samples(self, X):
        return np.array([-0.8] * len(X))

def test_predictor_output(tmp_path):
    clf_path = tmp_path / "clf.joblib"
    anom_path = tmp_path / "anom.joblib"
    
    clf_bundle = {
        'model': MockModel(classes_=['normal', 'recon', 'brute_force', 'command_attack']),
        'FEATURE_COLUMNS': FEATURE_COLUMNS,
        'LABELS': ['normal', 'recon', 'brute_force', 'command_attack'],
        'THREAT_LEVEL': THREAT_LEVEL
    }
    joblib.dump(clf_bundle, clf_path)
    
    anom_bundle = {
        'model': MockAnomaly(),
        'FEATURE_COLUMNS': FEATURE_COLUMNS,
        'threshold_default': 0
    }
    joblib.dump(anom_bundle, anom_path)
    
    predictor = ThreatPredictor(str(clf_path), str(anom_path))
    
    row = {col: 0.0 for col in FEATURE_COLUMNS}
    results = predictor.predict(row)
    
    assert len(results) == 1
    res = results[0]
    assert res['predicted_label'] == 'command_attack'
    assert res['threat_level'] == 'Critical'
    assert res['confidence'] == 0.7
    assert res['is_anomalous'] is True
    assert res['anomaly_score'] == 0.8 # -(-0.8)
    
    # Check feature order preservation
    # X = df[self.features] in predict will preserve order.
