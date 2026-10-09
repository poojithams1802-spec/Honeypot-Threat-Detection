import os
import logging
from ml.predict import ThreatPredictor
from backend.config import MODEL_MODE

logger = logging.getLogger(__name__)

class ModelService:
    def __init__(self):
        self.predictor = None
        self.model_mode = None
        self.model_version = None
        self.model_loaded = False
        self.load_model()

    def load_model(self):
        real_clf = "models/threat_classifier.joblib"
        real_anom = "models/anomaly_detector.joblib"
        syn_clf = "models/synthetic_threat_classifier.joblib"
        syn_anom = "models/synthetic_anomaly_detector.joblib"
        
        mode = MODEL_MODE
        if mode == "auto":
            if os.path.exists(real_clf):
                mode = "real"
            elif os.path.exists(syn_clf):
                mode = "synthetic"
            else:
                mode = "real" # Will fail below

        if mode == "real":
            clf_path = real_clf
            anom_path = real_anom
        else:
            clf_path = syn_clf
            anom_path = syn_anom
            
        if not os.path.exists(clf_path):
            logger.error(f"Model file not found: {clf_path}")
            self.model_loaded = False
            return
            
        try:
            self.predictor = ThreatPredictor(clf_path, anom_path if os.path.exists(anom_path) else None)
            self.model_mode = mode
            self.model_version = os.path.basename(clf_path) + " (" + self.predictor.clf_bundle.get('training_date', 'unknown') + ")"
            self.model_loaded = True
            
            if mode == "synthetic":
                logger.warning("="*50)
                logger.warning("SYNTHETIC MODEL IN USE - DEMO MODE ONLY")
                logger.warning("="*50)
                
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.model_loaded = False

    def predict_single(self, features: dict):
        if not self.model_loaded:
            raise RuntimeError("Model is not loaded")
        return self.predictor.predict(features)[0]

    def predict_batch(self, features_list: list):
        if not self.model_loaded:
            raise RuntimeError("Model is not loaded")
        # We can pass a list of dicts directly as it will be converted to DataFrame in ThreatPredictor
        import pandas as pd
        df = pd.DataFrame(features_list)
        return self.predictor.predict(df)

model_service = ModelService()
