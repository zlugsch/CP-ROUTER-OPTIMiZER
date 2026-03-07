"""
CP Router Optimizer - FastAPI Backend
GPU-akcelerovaný optimalizátor svozových tras
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

from routers import optimize, routing

# Konfigurace loggeru
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Globální HTTP klient
http_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management - startup a shutdown"""
    global http_client
    
    # Startup
    logger.info("🚀 Starting CP Router Optimizer API...")
    http_client = httpx.AsyncClient(timeout=60.0)
    
    # Ověření připojení k OSRM
    osrm_url = os.getenv("OSRM_URL", "http://localhost:5000")
    try:
        response = await http_client.get(f"{osrm_url}/health")
        logger.info(f"✅ OSRM connected: {osrm_url}")
    except Exception as e:
        logger.warning(f"⚠️ OSRM not available: {e}")
    
    # Ověření připojení k cuOpt
    cuopt_url = os.getenv("CUOPT_URL", "http://localhost:8080")
    try:
        response = await http_client.get(f"{cuopt_url}/cuopt/health")
        logger.info(f"✅ cuOpt connected: {cuopt_url}")
    except Exception as e:
        logger.warning(f"⚠️ cuOpt not available: {e}")
    
    logger.info("✅ API ready to serve requests")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down...")
    await http_client.aclose()

# Inicializace FastAPI
app = FastAPI(
    title="CP Router Optimizer API",
    description="GPU-akcelerovaný optimalizátor svozových tras",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # V produkci omezit na konkrétní domény
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrace routerů
app.include_router(optimize.router, prefix="/api/v1", tags=["Optimization"])
app.include_router(routing.router, prefix="/api/v1", tags=["Routing"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "CP Router Optimizer API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    global http_client
    
    osrm_url = os.getenv("OSRM_URL", "http://localhost:5000")
    cuopt_url = os.getenv("CUOPT_URL", "http://localhost:8080")
    
    status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "api": "up",
            "osrm": "unknown",
            "cuopt": "unknown"
        }
    }
    
    # Check OSRM
    try:
        response = await http_client.get(f"{osrm_url}/health", timeout=5.0)
        status["services"]["osrm"] = "up" if response.status_code == 200 else "degraded"
    except:
        status["services"]["osrm"] = "down"
    
    # Check cuOpt
    try:
        response = await http_client.get(f"{cuopt_url}/cuopt/health", timeout=5.0)
        status["services"]["cuopt"] = "up" if response.status_code == 200 else "degraded"
    except:
        status["services"]["cuopt"] = "down"
    
    # Celkový status
    if status["services"]["osrm"] == "down" and status["services"]["cuopt"] == "down":
        status["status"] = "unhealthy"
    elif "down" in status["services"].values() or "degraded" in status["services"].values():
        status["status"] = "degraded"
    
    return status


@app.get("/metrics")
async def metrics():
    """Prometheus metriky"""
    # TODO: Implementovat Prometheus metriky
    return {"message": "Metrics endpoint - coming soon"}


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Internal server error",
            "status_code": 500
        }
    )


def get_http_client():
    """Getter pro HTTP klienta"""
    global http_client
    return http_client
