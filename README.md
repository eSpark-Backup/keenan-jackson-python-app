# 🧠 Board Operations Agent - Square Trivia

## Overview

The **Board Operations Agent** is an autonomous system that powers **Square Trivia’s** dynamic game board generation and optimization.  
It uses **FastAPI** for a secure RESTful API, **Prometheus** for monitoring, and **machine learning-based decision logic** to generate and manage trivia boards every few hours.

This agent automatically monitors performance, adjusts strategies based on demand, and provides detailed operational metrics for transparency.

---

## 🚀 Features

### 🎯 Core Functionalities

- **Autonomous Board Generation** – Automatically creates new trivia boards every 2 hours.  
- **Reach Mode Engine** – Dynamically adjusts difficulty and engagement strategies using real-time metrics.  
- **ML-Driven Decisions** – Learns from outcomes to improve future board creation efficiency.  
- **Metrics Dashboard** – Prometheus-compatible metrics for Grafana visualization.  
- **Authentication & Security** – JWT-based API token system for admin and service access.  
- **Full Monitoring Support** – Tracks API latency, performance counters, and operational trends.

---

## 🧩 Architecture

```txt
Square Trivia
│
├── api_server.py              # FastAPI backend with all REST endpoints
├── board_operations_agent.py  # Core ML + board creation logic
├── test_reach_mode.py         # Unit and integration tests for Reach Mode logic
└── requirements.txt           # Dependency list
```

### System Components

| Component | Description |
|------------|-------------|
| **FastAPI Server** | Manages API routes, security, health checks, and background jobs |
| **BoardOperationsAgent** | Core orchestrator for automated board generation |
| **ProposalGenerator** | Creates and evaluates proposals using Reach Mode ML model |
| **GovernorClient** | Handles approval workflows for generated boards |
| **LearningService** | Records board outcomes and retrains predictive models |
| **Prometheus Metrics** | Provides metrics for Grafana dashboards |
| **Reach Mode Engine** | Adjusts alpha/bias dynamically based on live performance |

---

## ⚙️ API Endpoints Summary

| Endpoint | Method | Description |
|-----------|--------|-------------|
| `/` | GET | Root info and version |
| `/health` | GET | Health status of the agent |
| `/proposals/generate` | POST | Generate board proposals manually |
| `/proposals/submit` | POST | Submit proposals for approval |
| `/outcomes/record` | POST | Record board performance outcomes |
| `/model/retrain` | POST | Retrain the ML model |
| `/metrics` | GET | Exposes Prometheus metrics |
| `/metrics/summary` | GET | Summary of operational metrics |
| `/cycle/trigger` | POST | Manually trigger a decision cycle |
| `/auth/token` | POST | Generate JWT token |
| `/reach/status` | GET | Get current Reach Mode state |
| `/reach/override` | POST | Override Reach Mode manually |

---

## 🛡️ Authentication

This API uses **JWT (JSON Web Token)** for secure access.

Example token request:

```bash
curl -X POST http://localhost:8080/auth/token -d "username=admin&password=admin123"
```

Then include in future requests:

```bash
-H "Authorization: Bearer <token>"
```

---

## 📊 Metrics and Monitoring

Prometheus metrics include:

- `proposals_generated_total`
- `proposals_approved_total`
- `api_request_duration_seconds`
- `model_confidence_average`
- `reach_social_buzz`, `reach_event_intensity`, etc.

### Grafana Integration

Once metrics are available on `/metrics`, you can configure Grafana:

1. Add a **Prometheus data source** with your FastAPI server URL.  
2. Import or create a **dashboard** for the metrics listed above.  
3. Visualize Reach Mode parameters (`alpha`, `reach_ratio`, etc.) over time.

Example dashboard panels:

- **Reach Mode Alpha vs Fill Rate**
- **API Request Latency**
- **Proposal Generation Count**
- **Board Efficiency Trends**

---

## 🧪 Testing

All Reach Mode and Board Operations tests are under `test_reach_mode.py` using **pytest** and **pytest-asyncio**.

Run tests:

```bash
pytest -v
```

---

## 🧰 Setup and Run

### 1️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 2️⃣ Run the API server

```bash
uvicorn api_server:app --host 0.0.0.0 --port 8080 --reload
```

### 3️⃣ View metrics (Prometheus endpoint)

```bash
http://localhost:8080/metrics
```

### 4️⃣ Open Grafana Dashboard

- Configure Prometheus as source
- Import `Board Operations Agent` dashboard JSON

---

## 🧠 Reach Mode Engine

Reach Mode adapts engagement dynamically based on platform performance:

| Mode | Description | Trigger |
|------|--------------|----------|
| `default` | Normal steady-state operation | Balanced metrics |
| `base_reach` | Standard engagement phase | Normal conditions |
| `hype_surge` | High user engagement | High social buzz or fill rate |
| `recovery` | Low engagement recovery | Low fill rate or slow cycles |
| `ops_cooldown` | High system load | High ops_load |
| `quiet_hours` | Off-peak stabilization | Late-night hours |

---

## 🧩 File Descriptions

| File | Description |
|------|-------------|
| `api_server.py` | FastAPI REST API with authentication, metrics, and scheduling |
| `board_operations_agent.py` | Core logic for proposal generation, learning, and board control |
| `test_reach_mode.py` | Pytest suite testing all Reach Mode and agent behaviors |

---

## 🧱 Requirements

Refer to the `requirements.txt` file for dependencies.

Example key libraries:

```txt
fastapi, uvicorn, pyjwt, prometheus-client, pytest, aiohttp, httpx
```

## Build & Run Instructions

### Build Docker Image

```txt
docker build -t board-operations-agent .
```

### Run Container

```txt
docker run -d \
  -p 8080:8080 \
  -e JWT_SECRET=mysecretkey \
  -e DECISION_CYCLE_HOURS=2 \
  --name board-agent \
  board-operations-agent
```

### Verify API

```txt
Swagger Docs: http://localhost:8080/docs
Metrics: http://localhost:8080/metrics
```

---

## 📚 License

© 2025 Square Trivia. All Rights Reserved.
