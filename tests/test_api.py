import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.db import get_db, Base
from backend.models import SessionRecord
from backend.services.model_service import model_service
from ml.config import FEATURE_COLUMNS, THREAT_LEVEL

# Test Database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(scope="function", autouse=True)
def clean_db():
    # Setup
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Teardown
    pass

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["db_ok"] is True
    assert "model_loaded" in data

def test_predict_success():
    if not model_service.model_loaded:
        pytest.skip("Model not loaded")
        
    features = {col: 0.0 for col in FEATURE_COLUMNS}
    payload = {
        "features": features
    }
    
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "predicted_label" in data
    assert "threat_level" in data

def test_predict_missing_features():
    payload = {
        "features": {"duration_sec": 10.0} # Missing all other features
    }
    
    response = client.post("/predict", json=payload)
    assert response.status_code == 422

def test_batch_limit():
    features = {col: 0.0 for col in FEATURE_COLUMNS}
    payload = [{"features": features} for _ in range(501)]
    
    response = client.post("/predict/batch", json=payload)
    assert response.status_code == 400
    assert "limit is 500" in response.json()["detail"]
    
def test_stats_and_security_score():
    db = TestingSessionLocal()
    import time
    now = time.time()
    
    records = [
        SessionRecord(session_id="1", src_ip="1.1.1.1", start_time=now, predicted_label="normal", threat_level="Low", created_at=now, is_demo=False),
        SessionRecord(session_id="2", src_ip="2.2.2.2", start_time=now, predicted_label="recon", threat_level="Medium", created_at=now, is_demo=False),
        SessionRecord(session_id="3", src_ip="1.1.1.1", start_time=now, predicted_label="command_attack", threat_level="Critical", created_at=now, is_demo=True),
    ]
    db.add_all(records)
    db.commit()
    db.close()
    
    # Check stats with include_demo=True
    response = client.get("/stats/summary?include_demo=true")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_events"] == 3
    assert data["unique_source_ips"] == 2
    # Penalties: Low(0) + Medium(1) + Critical(5) = 6
    # Score = 100 - 6 = 94
    assert data["security_score"] == 94
    
    # Check stats with include_demo=False
    response = client.get("/stats/summary?include_demo=false")
    data = response.json()
    assert data["total_events"] == 2
    # Penalties: Low(0) + Medium(1) = 1
    # Score = 100 - 1 = 99
    assert data["security_score"] == 99

def test_timeline_zero_filling():
    response = client.get("/stats/timeline?hours=24&bucket_minutes=60")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 24
    
    for bucket in data:
        assert "Low" in bucket
        assert "Medium" in bucket
        assert "High" in bucket
        assert "Critical" in bucket
        
def test_event_filtering():
    db = TestingSessionLocal()
    import time
    now = time.time()
    db.add(SessionRecord(
        session_id="e1", src_ip="10.0.0.1", start_time=now, 
        predicted_label="recon", threat_level="Medium", 
        confidence=0.9, model_version="v1", model_mode="real", created_at=now,
        is_demo=False
    ))
    db.commit()
    db.close()
    
    response = client.get("/events?threat_level=Medium")
    data = response.json()
    assert len(data) == 1
    assert data[0]["session_id"] == "e1"
    
    response = client.get("/events?threat_level=Critical")
    data = response.json()
    assert len(data) == 0

def test_stats_time_window_strict_and_all_time():
    db = TestingSessionLocal()
    import time
    now = time.time()
    old_time = now - (48 * 3600)  # 48 hours ago
    
    # Old event
    db.add(SessionRecord(
        session_id="old_sess", src_ip="9.9.9.9", start_time=old_time,
        predicted_label="recon", threat_level="High",
        confidence=0.85, model_version="v1", model_mode="real", created_at=old_time,
        is_demo=False
    ))
    db.commit()
    db.close()
    
    # hours=24 strictly filters out the 48h-old event
    res_24 = client.get("/stats/summary?hours=24&include_demo=false")
    assert res_24.status_code == 200
    # The old event should NOT be in the 24h summary
    data_24 = res_24.json()
    assert data_24["events_per_threat"]["High"] == 0
    
    # hours=0 includes all time, including the 48h-old event
    res_all = client.get("/stats/summary?hours=0&include_demo=false")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["events_per_threat"]["High"] >= 1

def test_event_detail_includes_credentials_and_commands():
    db = TestingSessionLocal()
    import time
    now = time.time()
    db.add(SessionRecord(
        session_id="detail_test", src_ip="192.168.1.100", start_time=now,
        predicted_label="command_attack", threat_level="Critical",
        confidence=0.95, model_version="v1", model_mode="real", created_at=now,
        usernames=["admin"], passwords=["secret123"], commands=["cat /etc/passwd", "uname -a"],
        is_demo=True
    ))
    db.commit()
    db.close()
    
    # List endpoint omits commands and passwords
    list_res = client.get("/events?src_ip=192.168.1.100")
    assert list_res.status_code == 200
    item = list_res.json()[0]
    assert "commands" not in item
    assert "passwords" not in item
    
    # Detail endpoint includes commands and passwords
    detail_res = client.get("/events/detail_test")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["usernames"] == ["admin"]
    assert detail["passwords"] == ["secret123"]
    assert detail["commands"] == ["cat /etc/passwd", "uname -a"]
