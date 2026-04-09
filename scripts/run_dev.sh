#!/usr/bin/env bash
# Development server startup script for Weather Alerts API

set -e  # Exit on error

# Colors for terminal output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"

echo -e "${BLUE}Weather Alerts API - Development Server${NC}"
echo -e "${YELLOW}=====================================${NC}\n"

# Check if venv exists
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${YELLOW}No virtual environment found. Creating...${NC}"
    python3 -m venv "$VENV_PATH"
    echo -e "${GREEN}✓ Virtual environment created${NC}\n"
fi

# Activate venv
source "$VENV_PATH/bin/activate"
echo -e "${GREEN}✓ Virtual environment activated${NC}\n"

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -q -r "${PROJECT_ROOT}/requirements.txt"
    echo -e "${GREEN}✓ Dependencies installed${NC}\n"
fi

# Check if database is running (docker-compose)
if command -v docker-compose &> /dev/null; then
    if ! docker-compose ps --filter "status=running" | grep -q "postgres"; then
        echo -e "${YELLOW}Starting PostgreSQL and Redis with docker-compose...${NC}"
        cd "$PROJECT_ROOT" && docker-compose up -d
        sleep 3
        echo -e "${GREEN}✓ Database services started${NC}\n"
    fi
fi

# Start server
echo -e "${BLUE}Starting server on http://localhost:8000${NC}\n"
echo -e "${YELLOW}API Documentation:${NC}"
echo -e "  • Swagger UI: http://localhost:8000/docs"
echo -e "  • ReDoc: http://localhost:8000/redoc"
echo -e "  • OpenAPI JSON: http://localhost:8000/openapi.json\n"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"

cd "$PROJECT_ROOT"
exec uvicorn src.weather_alerts.api.main:app --reload --host 0.0.0.0 --port 8000
