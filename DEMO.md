# Honeypot-ML Demo Guide

This guide explains how to present the Honeypot-ML project during your viva or project presentation.

## 1. Prerequisites
Ensure you have the following installed:
- Python 3.10+
- Node.js 18+

## 2. Setup
Before presenting, start the necessary services in three separate terminal windows.

### Terminal 1: Backend API
```bash
# Activate your virtual environment
.\venv\Scripts\activate

# Start the FastAPI backend
python -m uvicorn backend.main:app --port 8000
```

### Terminal 2: Live Ingestion (Replay Mode)
Instead of waiting for real attacks, you will replay a sample log file to simulate live traffic.
```bash
# Activate your virtual environment
.\venv\Scripts\activate

# Run the ingestor in replay mode
python -m backend.ingest.run_ingest --log tests/fixtures/sample_cowrie.json --replay-speed 0
```
*Note: This will process the sample data instantly and mark rows with `is_demo=True`.*

### Terminal 3: Frontend Dashboard
```bash
cd frontend
npm install
npm run dev
```

## 3. Presenting the Features
1. **Open the Dashboard**: Navigate to `http://localhost:3000` in your browser.
2. **SOC Theme**: Point out the modern, dark SOC aesthetics, glassmorphism, and responsive layout.
3. **Demo Banner**: Highlight the "DEMO / SYNTHETIC" banner at the top, which clearly delineates real traffic from demo replay traffic.
4. **Real-time SSE**: Explain that as new events are ingested, they are streamed in real-time via Server-Sent Events (SSE).
5. **Interactive UI**: Click on any row in the "Recent Activity" table to open the details drawer and view the raw session features, model confidence, and anomaly scores.
6. **API Failover**: (Optional) Stop the backend server and show that the dashboard handles the failure gracefully.
