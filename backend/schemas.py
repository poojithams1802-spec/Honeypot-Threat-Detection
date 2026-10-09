from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, Any, List, Optional

class PredictRequest(BaseModel):
    # Metadata (Optional)
    session_id: Optional[str] = None
    src_ip: Optional[str] = None
    start_time: Optional[float] = None
    dst_port: Optional[int] = None
    protocol: Optional[int] = None
    end_time: Optional[float] = None
    usernames: Optional[List[str]] = []
    passwords: Optional[List[str]] = []
    commands: Optional[List[str]] = []
    is_demo: Optional[bool] = False
    
    # Feature columns (can just take a dict for arbitrary features, but we will take them in a generic features dict or flat)
    features: Dict[str, float] = Field(..., description="Dictionary containing all required feature columns")

class PredictResponse(BaseModel):
    predicted_label: str
    probabilities: Dict[str, float]
    confidence: float
    threat_level: str
    anomaly_score: Optional[float]
    is_anomalous: Optional[bool]
    model_mode: str

class SessionListItem(BaseModel):
    id: int
    session_id: str
    src_ip: str
    dst_port: Optional[int] = None
    protocol: Optional[int] = None
    start_time: float
    end_time: Optional[float] = None
    duration_sec: Optional[float] = None
    n_login_failed: Optional[int] = None
    n_login_success: Optional[int] = None
    n_commands: Optional[int] = None
    usernames: Optional[List[str]] = None
    predicted_label: str
    confidence: float
    threat_level: str
    anomaly_score: Optional[float] = None
    is_anomalous: Optional[bool] = None
    model_version: str
    model_mode: str
    created_at: float
    is_demo: bool

    model_config = ConfigDict(from_attributes=True)

class SessionDetail(BaseModel):
    id: int
    session_id: str
    src_ip: str
    dst_port: Optional[int]
    protocol: Optional[int]
    start_time: float
    end_time: Optional[float]
    duration_sec: Optional[float]
    n_login_failed: Optional[int]
    n_login_success: Optional[int]
    n_commands: Optional[int]
    usernames: Optional[List[str]]
    passwords: Optional[List[str]]
    commands: Optional[List[str]]
    features: Optional[Dict[str, float]]
    predicted_label: str
    probabilities: Optional[Dict[str, float]]
    confidence: float
    threat_level: str
    anomaly_score: Optional[float]
    is_anomalous: Optional[bool]
    model_version: str
    model_mode: str
    created_at: float
    is_demo: bool

    model_config = ConfigDict(from_attributes=True)

class StatsSummary(BaseModel):
    total_events: int
    events_per_threat: Dict[str, int]
    critical_alerts: int
    unique_source_ips: int
    anomalous_count: int
    security_score: int
    penalty_breakdown: Dict[str, int]
