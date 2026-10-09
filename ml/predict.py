import os
import argparse
import pandas as pd
import numpy as np
import joblib

class ThreatPredictor:
    def __init__(self, classifier_path, anomaly_path=None):
        if not os.path.exists(classifier_path):
            raise FileNotFoundError(f"Classifier bundle not found at {classifier_path}")
            
        self.clf_bundle = joblib.load(classifier_path)
        self.clf = self.clf_bundle['model']
        self.features = self.clf_bundle['FEATURE_COLUMNS']
        self.labels = self.clf_bundle['LABELS']
        self.threat_levels = self.clf_bundle['THREAT_LEVEL']
        
        self.anomaly_detector = None
        if anomaly_path and os.path.exists(anomaly_path):
            self.anom_bundle = joblib.load(anomaly_path)
            self.anomaly_detector = self.anom_bundle['model']
            
    def predict(self, data):
        """
        data: dict or pd.DataFrame
        returns: list of dicts with predictions per session
        """
        if isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            raise TypeError("Data must be a dict or pandas DataFrame")
            
        # Validate features
        missing = [f for f in self.features if f not in df.columns]
        if missing:
            raise ValueError(f"Missing required features: {missing}")
            
        # Reorder and extract features
        X = df[self.features]
        
        # Predict classifier
        preds = self.clf.predict(X)
        probs = self.clf.predict_proba(X)
        
        # Predict anomaly
        is_anomalous = [None] * len(df)
        anomaly_score = [None] * len(df)
        if self.anomaly_detector:
            anom_preds = self.anomaly_detector.predict(X)
            anom_scores = -self.anomaly_detector.score_samples(X)
            is_anomalous = [bool(p == -1) for p in anom_preds]
            anomaly_score = [float(s) for s in anom_scores]
            
        results = []
        for i in range(len(df)):
            label = preds[i]
            prob_dist = {self.clf.classes_[j]: float(probs[i][j]) for j in range(len(self.clf.classes_))}
            confidence = float(np.max(probs[i]))
            threat = self.threat_levels.get(label, 'Unknown')
            
            res = {
                'predicted_label': label,
                'class_probabilities': prob_dist,
                'confidence': confidence,
                'threat_level': threat,
                'is_anomalous': is_anomalous[i],
                'anomaly_score': anomaly_score[i]
            }
            results.append(res)
            
        return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to CSV containing features")
    parser.add_argument("--classifier", default="models/synthetic_threat_classifier.joblib")
    parser.add_argument("--anomaly", default="models/synthetic_anomaly_detector.joblib")
    args = parser.parse_args()
    
    predictor = ThreatPredictor(args.classifier, args.anomaly)
    df = pd.read_csv(args.csv)
    
    results = predictor.predict(df)
    for i, res in enumerate(results):
        print(f"--- Session {i+1} ---")
        for k, v in res.items():
            print(f"{k}: {v}")
