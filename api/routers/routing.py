"""
Routing Router - OSRM wrapper pro výpočet tras
"""

import os
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================
# Pydantic modely
# ============================================

class Waypoint(BaseModel):
    """Bod na trase"""
    lat: float
    lng: float
    name: Optional[str] = None


class RouteRequest(BaseModel):
    """Request pro výpočet trasy"""
    waypoints: List[Waypoint] = Field(..., min_items=2)
    profile: str = Field(default="driving", description="driving | truck | walking | cycling")
    alternatives: bool = Field(default=False)
    steps: bool = Field(default=False)
    overview: str = Field(default="simplified", description="full | simplified | false")


class RouteLeg(BaseModel):
    """Úsek trasy"""
    distance: float  # metry
    duration: float  # sekundy
    summary: str


class RouteResponse(BaseModel):
    """Response s trasou"""
    distance_m: float
    distance_km: float
    duration_s: float
    duration_min: float
    geometry: Optional[str] = None
    legs: List[RouteLeg]


class DistanceMatrixRequest(BaseModel):
    """Request pro matici vzdáleností"""
    locations: List[Waypoint]
    profile: str = Field(default="driving")


class DistanceMatrixResponse(BaseModel):
    """Matice vzdáleností"""
    distances: List[List[float]]  # v km
    durations: List[List[float]]  # v minutách
    sources: int
    destinations: int


class NearestRequest(BaseModel):
    """Request pro nejbližší bod na silnici"""
    lat: float
    lng: float
    number: int = Field(default=1, ge=1, le=10)


class NearestResponse(BaseModel):
    """Nejbližší bod na silnici"""
    waypoints: List[dict]


# ============================================
# API Endpoints
# ============================================

@router.post("/route", response_model=RouteResponse)
async def calculate_route(request: RouteRequest):
    """
    Výpočet trasy mezi waypoints
    
    Používá lokální OSRM server pro rychlý a spolehlivý routing.
    """
    osrm_url = os.getenv("OSRM_URL", "http://localhost:5000")
    
    # Formát: lng,lat;lng,lat;...
    coordinates = ";".join([f"{w.lng},{w.lat}" for w in request.waypoints])
    
    params = {
        "overview": request.overview,
        "alternatives": str(request.alternatives).lower(),
        "steps": str(request.steps).lower()
    }
    
    url = f"{osrm_url}/route/v1/{request.profile}/{coordinates}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if data.get("code") != "Ok":
                raise HTTPException(400, f"OSRM error: {data.get('message', 'Route not found')}")
            
            route = data["routes"][0]
            
            legs = []
            for leg in route.get("legs", []):
                legs.append(RouteLeg(
                    distance=leg["distance"],
                    duration=leg["duration"],
                    summary=leg.get("summary", "")
                ))
            
            return RouteResponse(
                distance_m=route["distance"],
                distance_km=round(route["distance"] / 1000, 2),
                duration_s=route["duration"],
                duration_min=round(route["duration"] / 60, 1),
                geometry=route.get("geometry"),
                legs=legs
            )
            
        except httpx.RequestError as e:
            logger.error(f"OSRM request failed: {e}")
            raise HTTPException(503, "OSRM service unavailable")


@router.post("/matrix", response_model=DistanceMatrixResponse)
async def calculate_distance_matrix(request: DistanceMatrixRequest):
    """
    Výpočet matice vzdáleností mezi všemi body
    
    Efektivní pro VRP - jeden request místo n² jednotlivých tras.
    """
    osrm_url = os.getenv("OSRM_URL", "http://localhost:5000")
    
    if len(request.locations) > 200:
        raise HTTPException(400, "Maximum 200 locations for matrix calculation")
    
    # Formát souřadnic
    coordinates = ";".join([f"{loc.lng},{loc.lat}" for loc in request.locations])
    
    url = f"{osrm_url}/table/v1/{request.profile}/{coordinates}"
    params = {"annotations": "distance,duration"}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if data.get("code") != "Ok":
                raise HTTPException(400, f"OSRM error: {data.get('message', 'Matrix calculation failed')}")
            
            # Konverze na km a minuty
            distances = [[d / 1000 if d else 0 for d in row] for row in data["distances"]]
            durations = [[d / 60 if d else 0 for d in row] for row in data["durations"]]
            
            return DistanceMatrixResponse(
                distances=distances,
                durations=durations,
                sources=len(request.locations),
                destinations=len(request.locations)
            )
            
        except httpx.RequestError as e:
            logger.error(f"OSRM request failed: {e}")
            raise HTTPException(503, "OSRM service unavailable")


@router.get("/nearest")
async def find_nearest_road(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    number: int = Query(default=1, ge=1, le=10)
):
    """
    Najde nejbližší bod na silniční síti
    
    Užitečné pro snap-to-road a validaci GPS souřadnic.
    """
    osrm_url = os.getenv("OSRM_URL", "http://localhost:5000")
    
    url = f"{osrm_url}/nearest/v1/driving/{lng},{lat}"
    params = {"number": number}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params=params)
            data = response.json()
            
            if data.get("code") != "Ok":
                raise HTTPException(400, f"OSRM error: {data.get('message', 'Point not found')}")
            
            waypoints = []
            for wp in data.get("waypoints", []):
                waypoints.append({
                    "lat": wp["location"][1],
                    "lng": wp["location"][0],
                    "distance": wp["distance"],
                    "name": wp.get("name", "")
                })
            
            return {"waypoints": waypoints}
            
        except httpx.RequestError as e:
            logger.error(f"OSRM request failed: {e}")
            raise HTTPException(503, "OSRM service unavailable")


@router.get("/health")
async def osrm_health():
    """Ověření dostupnosti OSRM serveru"""
    osrm_url = os.getenv("OSRM_URL", "http://localhost:5000")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Test route request
            response = await client.get(
                f"{osrm_url}/route/v1/driving/13.378361,49.725588;13.4067,49.7292",
                params={"overview": "false"}
            )
            data = response.json()
            
            return {
                "status": "healthy" if data.get("code") == "Ok" else "degraded",
                "osrm_url": osrm_url,
                "response_code": data.get("code")
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "osrm_url": osrm_url,
                "error": str(e)
            }


@router.get("/profiles")
async def list_profiles():
    """Seznam dostupných routing profilů"""
    return {
        "profiles": [
            {
                "id": "driving",
                "name": "Auto",
                "description": "Standardní osobní automobil"
            },
            {
                "id": "truck",
                "name": "Nákladní vůz",
                "description": "Nákladní vozidlo s omezeními (hmotnost, výška)"
            },
            {
                "id": "walking",
                "name": "Pěšky",
                "description": "Pěší trasa"
            },
            {
                "id": "cycling",
                "name": "Kolo",
                "description": "Cyklistická trasa"
            }
        ],
        "note": "Dostupnost profilů závisí na konfiguraci OSRM serveru"
    }
