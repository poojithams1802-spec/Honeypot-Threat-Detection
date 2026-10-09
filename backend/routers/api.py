import time
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from backend.db import get_db, engine, Base
from backend.models import SessionRecord
from backend.schemas import PredictRequest, PredictResponse, SessionDetail, SessionListItem, StatsSummary
from backend.services.model_service import model_service
from backend.config import THREAT_WEIGHTS

router = APIRouter()

def check_model_loaded():
    if not model_service.model_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Model is not loaded or unavailable."
        )

@router.get("/health")
def health_check():
    try:
        # Simple DB check
        with engine.connect() as conn:
            pass
        db_ok = True
    except Exception:
        db_ok = False
        
    return {
        "status": "ok" if db_ok else "degraded",
        "db_ok": db_ok,
        "model_loaded": model_service.model_loaded,
        "model_mode": model_service.model_mode,
        "model_version": model_service.model_version
    }

@router.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest, db: Session = Depends(get_db)):
    check_model_loaded()
    
    try:
        pred = model_service.predict_single(req.features)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
        
    session_id = req.session_id or str(uuid.uuid4())
    src_ip = req.src_ip or "0.0.0.0"
    start_time = req.start_time or time.time()
    
    # Cap lists
    usernames = (req.usernames or [])[:20]
    passwords = (req.passwords or [])[:20]
    commands = (req.commands or [])[:50]
    
    record = SessionRecord(
        session_id=session_id,
        src_ip=src_ip,
        dst_port=req.dst_port,
        protocol=req.protocol,
        start_time=start_time,
        end_time=req.end_time,
        duration_sec=req.features.get('duration_sec'),
        n_login_failed=req.features.get('n_login_failed'),
        n_login_success=req.features.get('n_login_success'),
        n_commands=req.features.get('n_commands'),
        usernames=usernames,
        passwords=passwords,
        commands=commands,
        features=req.features,
        predicted_label=pred['predicted_label'],
        probabilities=pred['class_probabilities'],
        confidence=pred['confidence'],
        threat_level=pred['threat_level'],
        anomaly_score=pred['anomaly_score'],
        is_anomalous=pred['is_anomalous'],
        model_version=model_service.model_version,
        model_mode=model_service.model_mode,
        created_at=time.time(),
        is_demo=req.is_demo
    )
    
    db.add(record)
    db.commit()
    
    return PredictResponse(
        predicted_label=pred['predicted_label'],
        probabilities=pred['class_probabilities'],
        confidence=pred['confidence'],
        threat_level=pred['threat_level'],
        anomaly_score=pred['anomaly_score'],
        is_anomalous=pred['is_anomalous'],
        model_mode=model_service.model_mode
    )

@router.post("/predict/batch", response_model=List[PredictResponse])
def predict_batch(reqs: List[PredictRequest], db: Session = Depends(get_db)):
    check_model_loaded()
    if len(reqs) > 500:
        raise HTTPException(status_code=400, detail="Batch size limit is 500")
        
    try:
        preds = model_service.predict_batch([r.features for r in reqs])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
        
    responses = []
    records = []
    
    now = time.time()
    
    for r, p in zip(reqs, preds):
        session_id = r.session_id or str(uuid.uuid4())
        src_ip = r.src_ip or "0.0.0.0"
        start_time = r.start_time or now
        
        record = SessionRecord(
            session_id=session_id,
            src_ip=src_ip,
            dst_port=r.dst_port,
            protocol=r.protocol,
            start_time=start_time,
            end_time=r.end_time,
            duration_sec=r.features.get('duration_sec'),
            n_login_failed=r.features.get('n_login_failed'),
            n_login_success=r.features.get('n_login_success'),
            n_commands=r.features.get('n_commands'),
            usernames=(r.usernames or [])[:20],
            passwords=(r.passwords or [])[:20],
            commands=(r.commands or [])[:50],
            features=r.features,
            predicted_label=p['predicted_label'],
            probabilities=p['class_probabilities'],
            confidence=p['confidence'],
            threat_level=p['threat_level'],
            anomaly_score=p['anomaly_score'],
            is_anomalous=p['is_anomalous'],
            model_version=model_service.model_version,
            model_mode=model_service.model_mode,
            created_at=now,
            is_demo=r.is_demo
        )
        records.append(record)
        
        responses.append(PredictResponse(
            predicted_label=p['predicted_label'],
            probabilities=p['class_probabilities'],
            confidence=p['confidence'],
            threat_level=p['threat_level'],
            anomaly_score=p['anomaly_score'],
            is_anomalous=p['is_anomalous'],
            model_mode=model_service.model_mode
        ))
        
    db.add_all(records)
    db.commit()
    
    return responses

@router.get("/events", response_model=List[SessionListItem])
def get_events(
    page: int = 1, 
    page_size: int = 50,
    threat_level: Optional[str] = None,
    label: Optional[str] = None,
    src_ip: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    is_anomalous: Optional[bool] = None,
    include_demo: bool = True,
    db: Session = Depends(get_db)
):
    page_size = min(page_size, 100)
    query = db.query(SessionRecord)
    
    if not include_demo:
        query = query.filter(SessionRecord.is_demo == False)
    if threat_level:
        query = query.filter(SessionRecord.threat_level == threat_level)
    if label:
        query = query.filter(SessionRecord.predicted_label == label)
    if src_ip:
        query = query.filter(SessionRecord.src_ip == src_ip)
    if since:
        query = query.filter(SessionRecord.start_time >= since)
    if until:
        query = query.filter(SessionRecord.start_time <= until)
    if is_anomalous is not None:
        query = query.filter(SessionRecord.is_anomalous == is_anomalous)
        
    events = query.order_by(desc(SessionRecord.start_time)).offset((page - 1) * page_size).limit(page_size).all()
    return events

@router.get("/events/{session_id}", response_model=SessionDetail)
def get_event(session_id: str, db: Session = Depends(get_db)):
    event = db.query(SessionRecord).filter(SessionRecord.session_id == session_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Session not found")
    return event

@router.get("/stats/summary", response_model=StatsSummary)
def get_stats_summary(hours: float = 24, include_demo: bool = True, db: Session = Depends(get_db)):
    base_query = db.query(SessionRecord)
    if not include_demo:
        base_query = base_query.filter(SessionRecord.is_demo == False)

    if hours > 0:
        cutoff = time.time() - (hours * 3600)
        events = base_query.filter(SessionRecord.start_time >= cutoff).all()
    else:
        events = base_query.all()
    
    total_events = len(events)
    events_per_threat = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
    critical_alerts = 0
    unique_ips = set()
    anomalous_count = 0
    
    penalty_breakdown = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
    
    for e in events:
        events_per_threat[e.threat_level] = events_per_threat.get(e.threat_level, 0) + 1
        if e.threat_level == 'Critical':
            critical_alerts += 1
        unique_ips.add(e.src_ip)
        if e.is_anomalous:
            anomalous_count += 1
            
        penalty_breakdown[e.threat_level] += THREAT_WEIGHTS.get(e.threat_level, 0)
        
    total_penalty = sum(penalty_breakdown.values())
    security_score = max(0, 100 - total_penalty)
    
    return StatsSummary(
        total_events=total_events,
        events_per_threat=events_per_threat,
        critical_alerts=critical_alerts,
        unique_source_ips=len(unique_ips),
        anomalous_count=anomalous_count,
        security_score=security_score,
        penalty_breakdown=penalty_breakdown
    )

@router.get("/stats/attack-types")
def get_attack_types(hours: float = 24, include_demo: bool = True, db: Session = Depends(get_db)):
    base_query = db.query(SessionRecord.predicted_label, func.count(SessionRecord.id))
    if not include_demo:
        base_query = base_query.filter(SessionRecord.is_demo == False)
    
    if hours > 0:
        cutoff = time.time() - (hours * 3600)
        base_query = base_query.filter(SessionRecord.start_time >= cutoff)
        
    res = base_query.group_by(SessionRecord.predicted_label).all()
    return {k: v for k, v in res}

@router.get("/stats/timeline")
def get_timeline(hours: float = 24, bucket_minutes: int = 60, include_demo: bool = True, db: Session = Depends(get_db)):
    now = time.time()
    bucket_sec = bucket_minutes * 60
    
    base_query = db.query(SessionRecord.threat_level, SessionRecord.start_time)
    if not include_demo:
        base_query = base_query.filter(SessionRecord.is_demo == False)
        
    if hours > 0:
        cutoff = now - (hours * 3600)
        events = base_query.filter(SessionRecord.start_time >= cutoff).all()
    else:
        events = base_query.all()
        if events:
            min_ts = min(e.start_time for e in events)
            max_ts = max(e.start_time for e in events)
            cutoff = int(min_ts // bucket_sec) * bucket_sec
            now = int(max_ts // bucket_sec) * bucket_sec + bucket_sec
        else:
            cutoff = now - (24 * 3600)
    
    # Fill empty buckets with zeros
    buckets = {}
    curr = cutoff
    while curr <= now:
        b_key = int(curr // bucket_sec) * bucket_sec
        if b_key not in buckets:
            buckets[b_key] = {"timestamp": b_key, "Low": 0, "Medium": 0, "High": 0, "Critical": 0}
        curr += bucket_sec
        
    for e in events:
        b_key = int(e.start_time // bucket_sec) * bucket_sec
        if b_key in buckets:
            buckets[b_key][e.threat_level] = buckets[b_key].get(e.threat_level, 0) + 1
            
    sorted_buckets = [buckets[k] for k in sorted(buckets.keys())]
    return sorted_buckets

@router.get("/stats/top-ips")
def get_top_ips(hours: float = 24, limit: int = 10, include_demo: bool = True, db: Session = Depends(get_db)):
    base_query = db.query(SessionRecord)
    if not include_demo:
        base_query = base_query.filter(SessionRecord.is_demo == False)
        
    if hours > 0:
        cutoff = time.time() - (hours * 3600)
        events = base_query.filter(SessionRecord.start_time >= cutoff).all()
    else:
        events = base_query.all()
    
    ip_stats = {}
    th_order = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
    
    for e in events:
        ip = e.src_ip
        if ip not in ip_stats:
            ip_stats[ip] = {"count": 0, "highest_threat": "Low", "labels": {}}
        ip_stats[ip]["count"] += 1
        
        curr_th = ip_stats[ip]["highest_threat"]
        if th_order.get(e.threat_level, 0) > th_order.get(curr_th, 0):
            ip_stats[ip]["highest_threat"] = e.threat_level
            
        ip_stats[ip]["labels"][e.predicted_label] = ip_stats[ip]["labels"].get(e.predicted_label, 0) + 1
        
    results = []
    for ip, stat in ip_stats.items():
        most_common_label = max(stat["labels"].items(), key=lambda x: x[1])[0] if stat["labels"] else "Unknown"
        results.append({
            "src_ip": ip,
            "event_count": stat["count"],
            "highest_threat_level": stat["highest_threat"],
            "most_common_label": most_common_label
        })
        
    results.sort(key=lambda x: x["event_count"], reverse=True)
    return results[:limit]

@router.get("/stats/top-credentials")
def get_top_credentials(limit: int = 10, include_demo: bool = True, db: Session = Depends(get_db)):
    query = db.query(SessionRecord.usernames, SessionRecord.passwords)
    if not include_demo:
        query = query.filter(SessionRecord.is_demo == False)
        
    events = query.all()
    
    user_counts = {}
    pass_counts = {}
    
    for e in events:
        if e.usernames:
            for u in e.usernames:
                user_counts[u] = user_counts.get(u, 0) + 1
        if e.passwords:
            for p in e.passwords:
                pass_counts[p] = pass_counts.get(p, 0) + 1
                
    top_users = [{"username": k, "count": v} for k, v in sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:limit]]
    top_passes = [{"password": k, "count": v} for k, v in sorted(pass_counts.items(), key=lambda x: x[1], reverse=True)[:limit]]
    
    return {"usernames": top_users, "passwords": top_passes}

@router.get("/alerts", response_model=List[SessionDetail])
def get_alerts(hours: float = 24, include_demo: bool = True, db: Session = Depends(get_db)):
    query = db.query(SessionRecord).filter(
        SessionRecord.threat_level.in_(["High", "Critical"])
    )
    if hours > 0:
        cutoff = time.time() - (hours * 3600)
        query = query.filter(SessionRecord.start_time >= cutoff)
    if not include_demo:
        query = query.filter(SessionRecord.is_demo == False)
        
    return query.order_by(desc(SessionRecord.start_time)).all()
