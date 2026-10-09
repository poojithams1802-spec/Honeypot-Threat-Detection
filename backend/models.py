from sqlalchemy import Column, Integer, String, Float, Boolean, JSON, Index, BigInteger
from backend.db import Base

class SessionRecord(Base):
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    src_ip = Column(String, index=True, nullable=False)
    dst_port = Column(Integer)
    protocol = Column(Integer)  # 0: ssh, 1: telnet
    start_time = Column(Float, index=True, nullable=False)
    end_time = Column(Float)
    duration_sec = Column(Float)
    n_login_failed = Column(Integer)
    n_login_success = Column(Integer)
    n_commands = Column(Integer)
    
    # JSON Lists (capped)
    usernames = Column(JSON)
    passwords = Column(JSON)
    commands = Column(JSON)
    features = Column(JSON)
    
    # Predictions
    predicted_label = Column(String, index=True)
    probabilities = Column(JSON)
    confidence = Column(Float)
    threat_level = Column(String, index=True)
    anomaly_score = Column(Float)
    is_anomalous = Column(Boolean)
    
    # Metadata
    model_version = Column(String)
    model_mode = Column(String)
    created_at = Column(Float)
    is_demo = Column(Boolean, default=False)
    needs_rescore = Column(Boolean, default=False)  # True when stored without model
    
    # Indexes
    __table_args__ = (
        Index('idx_sessions_start_time', 'start_time'),
        Index('idx_sessions_src_ip', 'src_ip'),
        Index('idx_sessions_predicted_label', 'predicted_label'),
        Index('idx_sessions_threat_level', 'threat_level'),
        Index('idx_sessions_needs_rescore', 'needs_rescore'),
        {'extend_existing': True},
    )


class IngestStatus(Base):
    """Single-row heartbeat table updated by the ingestor every 30 s."""
    __tablename__ = "ingest_status"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, default=1)
    last_event_time = Column(Float)    # Unix timestamp of last seen event
    last_session_time = Column(Float)  # Unix timestamp of last stored session
    lines_read = Column(Integer, default=0)
    malformed_lines = Column(Integer, default=0)
    sessions_stored = Column(Integer, default=0)
    heartbeat_at = Column(Float)       # When this row was last written
    lag_seconds = Column(Float)        # Seconds behind live
