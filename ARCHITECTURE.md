# Honeypot-ML Architecture

## System Overview
The Honeypot-ML system is an end-to-end machine learning pipeline that ingests, processes, and classifies raw honeypot events (Cowrie logs) in real-time. It provides a FastAPI backend for data serving and ML inference, coupled with a React-based SOC dashboard for visualization.

## Architecture Components

### 1. Data Ingestion (`backend/ingest/`)
- **LogTailer**: Tails `cowrie.json` efficiently, implementing file rotation and robust retry logic. It uses Windows-compatible file sharing (`FILE_SHARE_DELETE`) for atomicity.
- **SessionTracker**: Aggregates atomic honeypot events (e.g., login attempts, command executions) into coherent user sessions.
- **IPContextTracker**: Maintains recent history of IP activities to enrich individual sessions with contextual features (e.g., `ip_sessions_last_300s`, `ip_failed_logins_last_300s`).

### 2. Machine Learning Pipeline (`ml/`)
- **Features (`ml/features.py`)**: Responsible for extracting session-level features and applying constraints to prevent training/serving skew.
- **Predictor (`ml/predict.py`)**: Uses a trained RandomForest model to classify sessions into threat categories (`normal`, `recon`, `brute_force`, `command_attack`). It outputs probabilities, confidence levels, anomaly scores, and threat levels.

### 3. Backend Services (`backend/`)
- **FastAPI**: Serves the REST API with endpoints for health checks, pagination (`/events`), aggregations (`/stats/summary`), and a Server-Sent Events (SSE) stream (`/events/stream`).
- **Database (`backend/models.py`)**: Uses SQLAlchemy and SQLite. The primary tables are `SessionRecord` and `IngestStatus`. The schema uses `extend_existing=True` to support dynamic migrations and testing.

### 4. Frontend Application (`frontend/`)
- **React + Vite**: An offline-first, responsive dashboard built without external UI libraries (vanilla CSS).
- **Features**: Real-time SSE event consumption, animated API failover handles, dynamic threat-level badges, and an interactive KPI summary.

## Data Flow
1. Raw logs are written by Cowrie to `cowrie.json`.
2. The `Ingestor` tails the file and passes events to `SessionTracker`.
3. `SessionTracker` finalizes a session and passes it to `model_service.predict_single()`.
4. The enriched session is saved to the SQLite database.
5. The frontend consumes the data via REST and updates in real-time using SSE.
