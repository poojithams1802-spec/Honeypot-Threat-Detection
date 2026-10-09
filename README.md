# Honeypot-ML

Honeypot-ML is a machine learning pipeline and SOC dashboard that ingests Cowrie honeypot logs, extracts features, and predicts threat levels in real-time.

## Features
- **Live Event Ingestion**: Robustly tails log files, aggregates events into sessions, and calculates contextual features.
- **Machine Learning Inference**: Predicts threat types (`normal`, `recon`, `brute_force`, `command_attack`) using a trained model.
- **REST API & SSE**: FastAPI backend serving real-time Server-Sent Events stream.
- **SOC Dashboard**: A beautiful, offline-first React dashboard using vanilla CSS for rendering real-time KPI metrics, charts, and activity logs.

## Documentation
- [Architecture](ARCHITECTURE.md)
- [Demo Guide](DEMO.md)
- [Known Limitations](LIMITATIONS.md)

## Quick Start

### 1. Install Dependencies
```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

cd frontend
npm install
```

### 2. Run the Backend API
```bash
.\venv\Scripts\activate
python -m uvicorn backend.main:app --port 8000
```

### 3. Run the Dashboard
```bash
cd frontend
npm run dev
```

### 4. Replay Sample Logs
To simulate live attacks:
```bash
.\venv\Scripts\activate
python -m backend.ingest.run_ingest --log tests/fixtures/sample_cowrie.json --replay-speed 0
```
