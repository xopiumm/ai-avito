# Quick Start Guide - Weather Alerts API

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- jq (for test script): `brew install jq` (macOS) or `apt-get install jq` (Linux)

## One-Command Startup

### Option 1: Automatic Script (Recommended)

```bash
cd /path/to/itmo-practice-xopiumm
chmod +x scripts/run_dev.sh
./scripts/run_dev.sh
```

This script automatically:
- ✅ Creates/activates virtual environment
- ✅ Installs dependencies
- ✅ Starts PostgreSQL & Redis (docker-compose)
- ✅ Initializes database
- ✅ Starts uvicorn server with auto-reload

### Option 2: Manual Steps

```bash
# 1. Activate venv
source .venv/bin/activate

# 2. Start services
docker-compose up -d

# 3. Run server
uvicorn src.weather_alerts.api.main:app --reload
```

## Verify It's Working

### Access Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Quick Test

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```

## Run Full Test Suite

```bash
chmod +x scripts/test_api.sh
./scripts/test_api.sh
```

This runs all 9 test scenarios:
1. Health check
2. Create subscription
3. List subscriptions
4. Get subscription
5. Update subscription (partial)
6. Pause subscription
7. Resume subscription
8. Delete subscription
9. Error scenarios (404, 422, 400)

## Common Endpoints

```bash
# Create
curl -X POST http://localhost:8000/alerts/subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "location": {"id": 1},
    "conditions": [{"type": "rain_probability_above", "threshold_value": 70}],
    "delivery_channels": [{"type": "email", "destination": "user@example.com"}]
  }'

# List
curl http://localhost:8000/alerts/subscriptions

# Get
curl http://localhost:8000/alerts/subscriptions/1

# Update (partial)
curl -X PATCH http://localhost:8000/alerts/subscriptions/1 \
  -H "Content-Type: application/json" \
  -d '{"schedule": {"active_from": "09:00", "active_to": "18:00"}}'

# Pause
curl -X POST http://localhost:8000/alerts/subscriptions/1/pause

# Resume
curl -X POST http://localhost:8000/alerts/subscriptions/1/resume

# Delete
curl -X DELETE http://localhost:8000/alerts/subscriptions/1
```

## Troubleshooting

### Port 8000 Already in Use
```bash
# Find process using port 8000
lsof -i :8000

# Kill it
kill -9 <PID>
```

### Database Connection Failed
```bash
# Check docker-compose status
docker-compose ps

# Restart services
docker-compose restart
```

### Module Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Or in dev mode
pip install -e .
```

### Virtual Environment Issues
```bash
# Recreate venv
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## IDE Setup

### VS Code
1. Select interpreter: `.venv/bin/python`
2. Install extensions: Python, REST Client
3. Use `/docs` endpoint for API testing

### PyCharm
1. Settings → Project → Python Interpreter
2. Select `.venv/bin/python`
3. Built-in REST Client available in sidebar

## Project Structure

```
itmo-practice-xopiumm/
├── src/weather_alerts/
│   ├── api/
│   │   ├── main.py              # FastAPI app definition
│   │   ├── routes/              # API endpoints
│   │   │   ├── subscriptions.py # All subscription endpoints
│   │   │   └── __init__.py
│   │   └── schemas/             # Request/response schemas
│   ├── config/                  # Configuration
│   │   ├── settings.py          # Pydantic settings
│   │   ├── database.py          # SQLAlchemy setup
│   │   └── redis.py             # Redis client
│   ├── domain/
│   │   └── models/              # ORM models
│   ├── services/                # Business logic
│   │   ├── subscription_service.py
│   │   └── exceptions.py
│   └── ...
├── scripts/
│   ├── run_dev.sh               # Development server startup
│   └── test_api.sh              # API testing
├── docker-compose.yml           # PostgreSQL + Redis
├── requirements.txt             # Dependencies
└── .venv/                       # Virtual environment
```

## Next Steps

1. ✅ API running locally
2. ✅ Database connected
3. ✅ All endpoints working

What's next?
- Scale with workers: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.weather_alerts.api.main:app`
- Add authentication: JWT tokens in Authorization header
- Deploy to cloud: Docker image + Kubernetes
- Monitor: Prometheus metrics + Sentry error tracking

