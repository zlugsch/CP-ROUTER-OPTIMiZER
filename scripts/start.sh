#!/bin/bash
# =============================================================================
# CP Router Optimizer - Start Script
# Spustí všechny služby
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."

# Barvy pro výstup
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

cd "$PROJECT_DIR"

log_header "CP Router Optimizer - Startup"

# 1. Kontrola prerekvizit
log_info "Checking prerequisites..."

# Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed"
    exit 1
fi

# Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    log_error "Docker Compose is not installed"
    exit 1
fi

# NVIDIA Docker (volitelné)
if command -v nvidia-smi &> /dev/null; then
    log_info "NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    GPU_AVAILABLE=true
else
    log_warn "NVIDIA GPU not detected - cuOpt will be unavailable"
    GPU_AVAILABLE=false
fi

# 2. Kontrola OSRM dat
OSRM_DATA="$PROJECT_DIR/osrm/data/czech-republic-latest.osrm"
if [ ! -f "${OSRM_DATA}.ebg" ]; then
    log_warn "OSRM data not found!"
    log_info "Running setup script..."
    ./scripts/setup.sh
fi

# 3. Vytvoření .env souboru pokud neexistuje
if [ ! -f "$PROJECT_DIR/.env" ]; then
    log_info "Creating default .env file..."
    cat > "$PROJECT_DIR/.env" << EOF
# CP Router Optimizer Configuration
OSRM_URL=http://osrm:5000
CUOPT_URL=http://cuopt:8080
API_PORT=8000
LOG_LEVEL=info
ENVIRONMENT=production
EOF
fi

# 4. Build a start
log_info "Building and starting services..."

if [ "$GPU_AVAILABLE" = true ]; then
    # S GPU - všechny služby
    docker-compose up -d --build
else
    # Bez GPU - pouze OSRM a API
    log_warn "Starting without GPU services (cuOpt disabled)"
    docker-compose up -d --build osrm api webapp
fi

# 5. Čekání na služby
log_info "Waiting for services to start..."
sleep 5

# 6. Health check
log_info "Running health checks..."

# API
if curl -s http://localhost:8888/health | grep -q "healthy"; then
    log_info "✅ API is healthy"
else
    log_warn "⚠️ API may not be fully ready"
fi

# OSRM
if curl -s "http://localhost:5050/route/v1/driving/13.378,49.725;13.406,49.729?overview=false" | grep -q "Ok"; then
    log_info "✅ OSRM is healthy"
else
    log_warn "⚠️ OSRM may not be fully ready"
fi

# cuOpt (pokud GPU)
if [ "$GPU_AVAILABLE" = true ]; then
    if curl -s http://localhost:9080/cuopt/health | grep -q "healthy"; then
        log_info "✅ cuOpt is healthy"
    else
        log_warn "⚠️ cuOpt may not be fully ready"
    fi
fi

# 7. Výpis URL
log_header "Services Ready"
echo ""
echo "  🌐 Web Application:  http://localhost:8880"
echo "  📚 API Documentation: http://localhost:8888/docs"
echo "  🗺️  OSRM Server:      http://localhost:5050"
if [ "$GPU_AVAILABLE" = true ]; then
    echo "  🚀 cuOpt Server:     http://localhost:9080"
fi
echo ""
echo "  📊 Health Check:     http://localhost:8888/health"
echo ""
log_info "Logs: docker-compose logs -f"
log_info "Stop: docker-compose down"
