import os

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/dev.db")

# Model configuration
MODEL_MODE = os.getenv("MODEL_MODE", "auto")

# CORS config
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
env_cors = os.getenv("CORS_ORIGINS")
if env_cors:
    CORS_ORIGINS.extend(env_cors.split(","))

# Security Score Weights
# Penalty = sum(weight[threat_level])
# Score = max(0, 100 - Penalty)
THREAT_WEIGHTS = {
    "Low": 0,
    "Medium": 1,
    "High": 3,
    "Critical": 5
}
