# Honeypot-Based Threat Detection System with ML Classifier & SOC Dashboard

A modular cybersecurity project that deploys an isolated Cowrie SSH/Telnet honeypot, captures live adversary telemetry, extracts behavioral features, classifies attack patterns using Machine Learning, and visualizes security metrics on a SOC dashboard.

---

## Project Structure

```text
honeypot-ml/
├── backend/            # FastAPI application (API endpoints, DB integration - later phase)
├── frontend/           # React + Vite SOC Dashboard (analytics UI - later phase)
├── ml/                 # Model training, feature engineering & inference pipelines (later phase)
├── attacks/            # Attack simulation scripts (brute force, recon, command injection - later phase)
├── data/
│   ├── cowrie_logs/    # Cowrie JSON logs (cowrie.json) mounted from honeypot container
│   ├── raw/            # Cleaned/raw telemetry datasets for ML
│   └── processed/      # Preprocessed feature vectors & splits
├── models/             # Trained ML model weights and serializations (*.joblib)
├── scripts/            # Operational scripts (Docker setup, honeypot verification)
│   ├── install_docker.sh
│   └── verify_cowrie.sh
├── docs/               # Architecture diagrams and project documentation
├── docker-compose.yml  # Isolated container configuration for Cowrie
├── requirements.txt    # Python dependencies
├── .gitignore          # Version control ignore rules
└── README.md           # Project documentation and operational guide
```

---

## Phase 1: Setup

### 1. Environment & Lab Safety Notice

> **CRITICAL SECURITY NOTE:**
> - This project is designed strictly for **isolated lab environments** (e.g. host-only Ubuntu VM).
> - All ports are bound exclusively to the VM's local interface (`127.0.0.1`).
> - **NEVER** expose ports `2222` or `2223` to `0.0.0.0` or the public internet.

---

### 2. Install Docker and Docker Compose (Ubuntu Lab VM)

If Docker is not yet installed on your Ubuntu VM, run the automated installation script:

```bash
# Make script executable and run
chmod +x scripts/install_docker.sh
./scripts/install_docker.sh

# Apply docker group permissions to current shell session (without rebooting)
newgrp docker
```

To verify Docker is ready:
```bash
docker --version
docker compose version
```

---

### 3. Python Virtual Environment Setup

Create and activate the Python virtual environment, then install the dependencies:

#### On Linux / Ubuntu VM:
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install required packages
pip install --upgrade pip
pip install -r requirements.txt
```

#### On Windows (PowerShell):
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install required packages
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 4. Cowrie Honeypot Lifecycle Commands

Manage the Cowrie honeypot container from the project root using `docker compose`:

#### Start Cowrie (Background Daemon):
```bash
docker compose up -d
```

#### Check Container Status:
```bash
docker compose ps
```

#### View Live Honeypot Logs:
```bash
docker compose logs -f cowrie
```

#### Stop Cowrie:
```bash
docker compose down
```

#### Restart Cowrie:
```bash
docker compose restart cowrie
```

---

### 5. Automated Honeypot Verification

Run the automated verification script to start Cowrie, simulate an SSH probe, and inspect captured logs:

```bash
chmod +x scripts/verify_cowrie.sh
./scripts/verify_cowrie.sh
```

#### What `verify_cowrie.sh` Does:
1. Spawns the Cowrie container via `docker compose up -d`.
2. Waits until port `2222` is accepting connections on `127.0.0.1`.
3. Issues a test SSH connection using fake credentials (`threat_actor:P@ssw0rdFake99`).
4. Prints the last 10 lines of `data/cowrie_logs/cowrie.json`.
5. Confirms telemetry events like `cowrie.session.connect` and `cowrie.login` were recorded.

---

### 6. Manual Verification & Telemetry Inspection

You can also simulate an attack probe manually and monitor real-time event logs:

#### Send a Test SSH Probe:
```bash
ssh -p 2222 fakeuser@127.0.0.1
```
*(Enter any dummy password when prompted)*

#### Inspect Live JSON Log Stream:
```bash
tail -f data/cowrie_logs/cowrie.json
```

#### Example Output in `data/cowrie_logs/cowrie.json`:
```json
{"eventid": "cowrie.session.connect", "src_ip": "127.0.0.1", "src_port": 54321, "dst_port": 2222, "session": "a1b2c3d4", "timestamp": "2026-10-08T09:30:00.000000Z"}
{"eventid": "cowrie.login.failed", "username": "threat_actor", "password": "P@ssw0rdFake99", "src_ip": "127.0.0.1", "session": "a1b2c3d4", "timestamp": "2026-10-08T09:30:02.000000Z"}
```

---

## Upcoming Phases

- **Phase 2:** Attack simulation script suite & telemetry dataset collection.
- **Phase 3:** Feature engineering pipeline & ML threat classifier (`models/`).
- **Phase 4:** FastAPI backend service with ingestion API and real-time inference.
- **Phase 5:** React + Vite SOC analytics dashboard.
