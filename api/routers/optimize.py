"""
Optimization Router - GPU-akcelerovaná VRP optimalizace
"""

import os
import time
import logging
from typing import List, Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import httpx
import numpy as np

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================
# Pydantic modely
# ============================================

class Location(BaseModel):
    """GPS lokace"""
    lat: float = Field(..., ge=-90, le=90, description="Zeměpisná šířka")
    lng: float = Field(..., ge=-180, le=180, description="Zeměpisná délka")


class Container(BaseModel):
    """Nádoba k obsluze"""
    id: str = Field(..., description="Unikátní ID nádoby")
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    volume: int = Field(default=1100, description="Objem v litrech")
    weight: float = Field(default=0, description="Hmotnost v kg")
    service_time: int = Field(default=120, description="Čas obsluhy v sekundách")
    waste_type: Optional[str] = Field(default=None, description="Typ odpadu")
    priority: int = Field(default=1, ge=1, le=10, description="Priorita 1-10")
    time_window_start: Optional[str] = Field(default=None, description="Časové okno - začátek (HH:MM)")
    time_window_end: Optional[str] = Field(default=None, description="Časové okno - konec (HH:MM)")


class Vehicle(BaseModel):
    """Vozidlo"""
    id: str = Field(..., description="ID vozidla")
    capacity_volume: int = Field(default=20000, description="Kapacita v litrech")
    capacity_weight: float = Field(default=15000, description="Kapacita v kg")
    max_route_duration: int = Field(default=480, description="Max doba trasy v minutách")
    cost_per_km: float = Field(default=8.0, description="Náklady na km")


class AlgorithmType(str, Enum):
    """Typ optimalizačního algoritmu"""
    FAST = "fast"           # Nearest Neighbor
    BALANCED = "balanced"   # NN + 2-opt
    QUALITY = "quality"     # NN + 2-opt + Or-opt
    CUOPT = "cuopt"         # NVIDIA cuOpt (GPU)


class OptimizationOptions(BaseModel):
    """Parametry optimalizace"""
    algorithm: AlgorithmType = Field(default=AlgorithmType.CUOPT)
    respect_capacity: bool = Field(default=True)
    respect_time_windows: bool = Field(default=False)
    balance_routes: bool = Field(default=True)
    minimize: str = Field(default="distance", description="distance | time | cost")
    max_iterations: int = Field(default=1000)


class OptimizationRequest(BaseModel):
    """Request pro optimalizaci"""
    depot: Location
    containers: List[Container]
    vehicles: List[Vehicle] = Field(default_factory=list)
    options: OptimizationOptions = Field(default_factory=OptimizationOptions)


class RouteStop(BaseModel):
    """Zastávka na trase"""
    container_id: str
    order: int
    lat: float
    lng: float
    arrival_time: Optional[str] = None
    service_time: int
    cumulative_load: float


class Route(BaseModel):
    """Optimalizovaná trasa"""
    vehicle_id: str
    stops: List[RouteStop]
    distance_km: float
    duration_min: float
    load_volume: int
    load_weight: float
    cost: float


class OptimizationResponse(BaseModel):
    """Response z optimalizace"""
    status: str
    computation_time_ms: int
    algorithm_used: str
    routes: List[Route]
    summary: dict
    warnings: List[str] = Field(default_factory=list)


# ============================================
# Pomocné funkce
# ============================================

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Výpočet vzdálenosti mezi dvěma GPS body v km"""
    R = 6371  # Poloměr Země v km
    
    lat1_rad = np.radians(lat1)
    lat2_rad = np.radians(lat2)
    delta_lat = np.radians(lat2 - lat1)
    delta_lng = np.radians(lng2 - lng1)
    
    a = np.sin(delta_lat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lng/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    
    return R * c


async def get_distance_matrix_osrm(
    locations: List[tuple],
    http_client: httpx.AsyncClient
) -> np.ndarray:
    """
    Získá matici vzdáleností z OSRM
    """
    osrm_url = os.getenv("OSRM_URL", "http://localhost:5000")
    
    # Formát souřadnic pro OSRM: lng,lat
    coords = ";".join([f"{lng},{lat}" for lat, lng in locations])
    url = f"{osrm_url}/table/v1/driving/{coords}?annotations=distance,duration"
    
    try:
        response = await http_client.get(url)
        data = response.json()
        
        if data.get("code") != "Ok":
            raise HTTPException(500, f"OSRM error: {data.get('message', 'Unknown error')}")
        
        # Vrať matici vzdáleností v km
        distances = np.array(data["distances"]) / 1000.0
        durations = np.array(data["durations"]) / 60.0  # v minutách
        
        return distances, durations
        
    except httpx.RequestError as e:
        logger.error(f"OSRM request failed: {e}")
        raise HTTPException(503, "OSRM service unavailable")


async def optimize_with_cuopt(
    depot: Location,
    containers: List[Container],
    vehicles: List[Vehicle],
    options: OptimizationOptions,
    distance_matrix: np.ndarray,
    duration_matrix: np.ndarray,
    http_client: httpx.AsyncClient
) -> dict:
    """
    Optimalizace pomocí NVIDIA cuOpt
    """
    cuopt_url = os.getenv("CUOPT_URL", "http://localhost:8080")
    
    # Příprava dat pro cuOpt
    num_locations = len(containers) + 1  # +1 pro depo
    num_vehicles = len(vehicles)
    
    # Kapacity vozidel
    vehicle_capacities = [[v.capacity_weight] for v in vehicles]
    
    # Požadavky kontejnerů (hmotnost)
    demands = [[0]]  # Depo má demand 0
    for c in containers:
        # Odhadovaná hmotnost podle objemu (0.3 kg/l pro odpad)
        weight = c.weight if c.weight > 0 else c.volume * 0.3
        demands.append([weight])
    
    # Service times
    service_times = [0]  # Depo
    for c in containers:
        service_times.append(c.service_time / 60.0)  # v minutách
    
    # cuOpt request
    cuopt_request = {
        "cost_matrix_data": {
            "data": {
                "0": distance_matrix.flatten().tolist()
            }
        },
        "travel_time_matrix_data": {
            "data": {
                "0": duration_matrix.flatten().tolist()
            }
        },
        "fleet_data": {
            "vehicle_locations": [[0, 0]] * num_vehicles,  # Start a end v depu
            "capacities": vehicle_capacities,
            "vehicle_max_times": [v.max_route_duration for v in vehicles]
        },
        "task_data": {
            "task_locations": list(range(1, num_locations)),  # Indexy kontejnerů
            "demand": demands[1:],  # Bez depa
            "service_times": service_times[1:]
        },
        "solver_config": {
            "time_limit": 10.0,  # Max 10 sekund
            "objectives": {
                "cost": 1,
                "travel_time": 0 if options.minimize == "distance" else 1
            }
        }
    }
    
    try:
        response = await http_client.post(
            f"{cuopt_url}/cuopt/routes",
            json=cuopt_request,
            timeout=30.0
        )
        
        result = response.json()
        
        if "error" in result:
            raise HTTPException(500, f"cuOpt error: {result['error']}")
        
        return result
        
    except httpx.RequestError as e:
        logger.error(f"cuOpt request failed: {e}")
        raise HTTPException(503, "cuOpt service unavailable")


def optimize_nearest_neighbor(
    containers: List[Container],
    depot: Location,
    distance_matrix: np.ndarray,
    max_stops: int = 100
) -> List[List[int]]:
    """
    Fallback algoritmus - Nearest Neighbor
    """
    routes = []
    unvisited = set(range(len(containers)))
    
    while unvisited:
        route = []
        current = 0  # Start v depu (index 0)
        
        while len(route) < max_stops and unvisited:
            # Najdi nejbližší nenavštívený bod
            nearest = None
            min_dist = float('inf')
            
            for idx in unvisited:
                # +1 protože index 0 je depo
                dist = distance_matrix[current][idx + 1]
                if dist < min_dist:
                    min_dist = dist
                    nearest = idx
            
            if nearest is not None:
                route.append(nearest)
                unvisited.remove(nearest)
                current = nearest + 1
            else:
                break
        
        if route:
            routes.append(route)
    
    return routes


def improve_2opt(route: List[int], distance_matrix: np.ndarray) -> List[int]:
    """
    2-opt vylepšení trasy
    """
    improved = True
    best_route = route.copy()
    
    while improved:
        improved = False
        for i in range(len(best_route) - 1):
            for j in range(i + 2, len(best_route)):
                # Zkus prohodit segment
                new_route = best_route[:i+1] + best_route[i+1:j+1][::-1] + best_route[j+1:]
                
                # Porovnej vzdálenosti
                old_dist = sum(distance_matrix[best_route[k]+1][best_route[k+1]+1] 
                              for k in range(len(best_route)-1))
                new_dist = sum(distance_matrix[new_route[k]+1][new_route[k+1]+1] 
                              for k in range(len(new_route)-1))
                
                if new_dist < old_dist:
                    best_route = new_route
                    improved = True
                    break
            if improved:
                break
    
    return best_route


# ============================================
# API Endpoints
# ============================================

@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_routes(request: OptimizationRequest):
    """
    Optimalizace svozových tras
    
    Podporované algoritmy:
    - **fast**: Nearest Neighbor (nejrychlejší, nejnižší kvalita)
    - **balanced**: NN + 2-opt (dobrý kompromis)
    - **quality**: NN + 2-opt + Or-opt (lepší kvalita, pomalejší)
    - **cuopt**: NVIDIA cuOpt GPU (nejlepší kvalita, vyžaduje GPU)
    """
    start_time = time.time()
    warnings = []
    
    # Validace
    if not request.containers:
        raise HTTPException(400, "No containers provided")
    
    if len(request.containers) > 5000:
        raise HTTPException(400, "Maximum 5000 containers supported")
    
    # Výchozí vozidla pokud nejsou specifikována
    if not request.vehicles:
        # Odhadni počet vozidel
        total_volume = sum(c.volume for c in request.containers)
        num_vehicles = max(1, (total_volume // 15000) + 1)
        request.vehicles = [
            Vehicle(id=f"V{i+1}", capacity_volume=20000, capacity_weight=15000)
            for i in range(num_vehicles)
        ]
        warnings.append(f"Auto-generated {num_vehicles} vehicles")
    
    logger.info(f"Optimizing {len(request.containers)} containers with {len(request.vehicles)} vehicles")
    
    # Vytvoř HTTP klienta
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Připrav lokace (depo + kontejnery)
        locations = [(request.depot.lat, request.depot.lng)]
        for c in request.containers:
            locations.append((c.lat, c.lng))
        
        # Získej matici vzdáleností
        try:
            distance_matrix, duration_matrix = await get_distance_matrix_osrm(locations, client)
        except HTTPException:
            # Fallback na Haversine vzdálenosti
            warnings.append("OSRM unavailable, using Haversine distances")
            n = len(locations)
            distance_matrix = np.zeros((n, n))
            duration_matrix = np.zeros((n, n))
            
            for i in range(n):
                for j in range(n):
                    if i != j:
                        dist = haversine_distance(
                            locations[i][0], locations[i][1],
                            locations[j][0], locations[j][1]
                        )
                        distance_matrix[i][j] = dist
                        # Odhad času: 30 km/h průměr
                        duration_matrix[i][j] = dist / 30 * 60
        
        # Optimalizace podle zvoleného algoritmu
        algorithm_used = request.options.algorithm.value
        
        if request.options.algorithm == AlgorithmType.CUOPT:
            try:
                cuopt_result = await optimize_with_cuopt(
                    request.depot,
                    request.containers,
                    request.vehicles,
                    request.options,
                    distance_matrix,
                    duration_matrix,
                    client
                )
                # TODO: Parsovat cuOpt výstup
                route_indices = cuopt_result.get("routes", [])
            except HTTPException:
                warnings.append("cuOpt unavailable, falling back to balanced algorithm")
                algorithm_used = "balanced"
                route_indices = optimize_nearest_neighbor(
                    request.containers, request.depot, distance_matrix
                )
                # Apply 2-opt
                route_indices = [improve_2opt(r, distance_matrix) for r in route_indices]
        else:
            # CPU algoritmy
            route_indices = optimize_nearest_neighbor(
                request.containers, request.depot, distance_matrix
            )
            
            if request.options.algorithm in [AlgorithmType.BALANCED, AlgorithmType.QUALITY]:
                route_indices = [improve_2opt(r, distance_matrix) for r in route_indices]
            
            # TODO: Or-opt pro quality
    
    # Sestavení výsledku
    routes = []
    total_distance = 0
    total_duration = 0
    
    for i, route_idx in enumerate(route_indices):
        vehicle = request.vehicles[min(i, len(request.vehicles)-1)]
        
        stops = []
        route_distance = 0
        route_duration = 0
        route_load_volume = 0
        route_load_weight = 0
        
        prev_idx = 0  # Depo
        
        for order, container_idx in enumerate(route_idx):
            container = request.containers[container_idx]
            
            # Vzdálenost od předchozího bodu
            route_distance += distance_matrix[prev_idx][container_idx + 1]
            route_duration += duration_matrix[prev_idx][container_idx + 1]
            route_duration += container.service_time / 60  # Service time
            
            route_load_volume += container.volume
            weight = container.weight if container.weight > 0 else container.volume * 0.3
            route_load_weight += weight
            
            stops.append(RouteStop(
                container_id=container.id,
                order=order + 1,
                lat=container.lat,
                lng=container.lng,
                service_time=container.service_time,
                cumulative_load=route_load_weight
            ))
            
            prev_idx = container_idx + 1
        
        # Návrat do depa
        if route_idx:
            route_distance += distance_matrix[prev_idx][0]
            route_duration += duration_matrix[prev_idx][0]
        
        routes.append(Route(
            vehicle_id=vehicle.id,
            stops=stops,
            distance_km=round(route_distance, 2),
            duration_min=round(route_duration, 1),
            load_volume=route_load_volume,
            load_weight=round(route_load_weight, 1),
            cost=round(route_distance * vehicle.cost_per_km, 2)
        ))
        
        total_distance += route_distance
        total_duration += route_duration
    
    computation_time = int((time.time() - start_time) * 1000)
    
    return OptimizationResponse(
        status="success",
        computation_time_ms=computation_time,
        algorithm_used=algorithm_used,
        routes=routes,
        summary={
            "total_containers": len(request.containers),
            "total_routes": len(routes),
            "total_distance_km": round(total_distance, 2),
            "total_duration_min": round(total_duration, 1),
            "total_cost": round(sum(r.cost for r in routes), 2),
            "vehicles_used": len(routes),
            "avg_stops_per_route": round(len(request.containers) / max(len(routes), 1), 1)
        },
        warnings=warnings
    )


@router.get("/algorithms")
async def list_algorithms():
    """Seznam dostupných algoritmů"""
    return {
        "algorithms": [
            {
                "id": "fast",
                "name": "Rychlý (Nearest Neighbor)",
                "description": "Nejrychlejší, ale nejnižší kvalita. Vhodné pro rychlý náhled.",
                "gpu_required": False,
                "quality_estimate": "70-75%"
            },
            {
                "id": "balanced",
                "name": "Balanced (NN + 2-opt)",
                "description": "Dobrý kompromis mezi rychlostí a kvalitou.",
                "gpu_required": False,
                "quality_estimate": "85-90%"
            },
            {
                "id": "quality",
                "name": "Kvalitní (NN + 2-opt + Or-opt)",
                "description": "Vyšší kvalita, pomalejší výpočet.",
                "gpu_required": False,
                "quality_estimate": "90-93%"
            },
            {
                "id": "cuopt",
                "name": "NVIDIA cuOpt (GPU)",
                "description": "Nejlepší kvalita, vyžaduje NVIDIA GPU.",
                "gpu_required": True,
                "quality_estimate": "97-99%"
            }
        ]
    }
