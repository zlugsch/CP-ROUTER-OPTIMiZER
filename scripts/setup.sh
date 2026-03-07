#!/bin/bash
# =============================================================================
# OSRM Data Download and Preparation Script
# Stáhne OSM data pro Českou republiku a připraví je pro OSRM
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/../osrm/data"
REGION="${1:-czech-republic}"
PROFILE="${2:-car}"  # car, truck, foot, bicycle

# Barvy pro výstup
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Vytvoření adresáře pro data
mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

log_info "=== OSRM Data Preparation ==="
log_info "Region: $REGION"
log_info "Profile: $PROFILE"
log_info "Data directory: $DATA_DIR"

# 1. Stažení OSM dat
OSM_FILE="${REGION}-latest.osm.pbf"
DOWNLOAD_URL="https://download.geofabrik.de/europe/${OSM_FILE}"

if [ -f "$OSM_FILE" ]; then
    log_warn "OSM file already exists: $OSM_FILE"
    read -p "Download again? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -f "$OSM_FILE"
    fi
fi

if [ ! -f "$OSM_FILE" ]; then
    log_info "Downloading OSM data from Geofabrik..."
    wget -c "$DOWNLOAD_URL" -O "$OSM_FILE"
    log_info "Download complete: $(du -h $OSM_FILE | cut -f1)"
fi

# 2. Vytvoření OSRM profilu
log_info "Selecting OSRM profile: $PROFILE"

case $PROFILE in
    car)
        PROFILE_FILE="/opt/car.lua"
        ;;
    truck)
        PROFILE_FILE="/opt/truck.lua"
        ;;
    foot)
        PROFILE_FILE="/opt/foot.lua"
        ;;
    bicycle)
        PROFILE_FILE="/opt/bicycle.lua"
        ;;
    *)
        log_error "Unknown profile: $PROFILE"
        exit 1
        ;;
esac

# 3. OSRM Extract
OSRM_FILE="${REGION}-latest.osrm"

if [ -f "${OSRM_FILE}.ebg" ]; then
    log_warn "OSRM files already exist"
    read -p "Re-extract? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Skipping extraction"
        exit 0
    fi
fi

log_info "Running OSRM extract (this may take 10-30 minutes)..."
docker run --rm -t \
    -v "${DATA_DIR}:/data" \
    osrm/osrm-backend:latest \
    osrm-extract -p "$PROFILE_FILE" /data/"$OSM_FILE"

# 4. OSRM Partition
log_info "Running OSRM partition..."
docker run --rm -t \
    -v "${DATA_DIR}:/data" \
    osrm/osrm-backend:latest \
    osrm-partition /data/"$OSRM_FILE"

# 5. OSRM Customize
log_info "Running OSRM customize..."
docker run --rm -t \
    -v "${DATA_DIR}:/data" \
    osrm/osrm-backend:latest \
    osrm-customize /data/"$OSRM_FILE"

log_info "=== OSRM Data Preparation Complete ==="
log_info "Files created in: $DATA_DIR"
ls -lh "$DATA_DIR"/*.osrm* 2>/dev/null | head -20

echo ""
log_info "You can now start OSRM server with:"
echo "  docker-compose up osrm"
