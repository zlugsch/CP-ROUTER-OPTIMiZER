# 📚 API Reference

## Base URL

```
http://localhost:8888/api/v1
```

## Autentizace

Aktuálně bez autentizace (interní síť). Pro produkční nasazení doporučujeme přidat API klíče.

---

## Endpoints

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "services": {
    "api": "up",
    "osrm": "up",
    "cuopt": "up"
  }
}
```

---

### Optimalizace tras

```http
POST /api/v1/optimize
```

Hlavní endpoint pro optimalizaci svozových tras.

**Request Body:**

```json
{
  "depot": {
    "lat": 49.725588,
    "lng": 13.378361
  },
  "containers": [
    {
      "id": "C001",
      "lat": 49.7292,
      "lng": 13.4067,
      "volume": 1100,
      "weight": 350,
      "service_time": 120,
      "waste_type": "paper",
      "priority": 1,
      "time_window_start": "08:00",
      "time_window_end": "12:00"
    }
  ],
  "vehicles": [
    {
      "id": "V1",
      "capacity_volume": 20000,
      "capacity_weight": 15000,
      "max_route_duration": 480,
      "cost_per_km": 8.0
    }
  ],
  "options": {
    "algorithm": "cuopt",
    "respect_capacity": true,
    "respect_time_windows": false,
    "balance_routes": true,
    "minimize": "distance"
  }
}
```

**Parametry:**

| Pole | Typ | Povinné | Popis |
|------|-----|---------|-------|
| `depot` | object | Ano | GPS souřadnice depa |
| `containers` | array | Ano | Seznam nádob k obsluze |
| `vehicles` | array | Ne | Seznam vozidel (auto-generuje se) |
| `options` | object | Ne | Parametry optimalizace |

**Container:**

| Pole | Typ | Výchozí | Popis |
|------|-----|---------|-------|
| `id` | string | - | Unikátní ID nádoby |
| `lat`, `lng` | float | - | GPS souřadnice |
| `volume` | int | 1100 | Objem v litrech |
| `weight` | float | 0 | Hmotnost v kg |
| `service_time` | int | 120 | Čas obsluhy v sekundách |
| `priority` | int | 1 | Priorita 1-10 |

**Options:**

| Pole | Hodnoty | Výchozí | Popis |
|------|---------|---------|-------|
| `algorithm` | fast, balanced, quality, cuopt | cuopt | Algoritmus |
| `respect_capacity` | bool | true | Respektovat kapacity |
| `minimize` | distance, time, cost | distance | Co minimalizovat |

**Response:**

```json
{
  "status": "success",
  "computation_time_ms": 2340,
  "algorithm_used": "cuopt",
  "routes": [
    {
      "vehicle_id": "V1",
      "stops": [
        {
          "container_id": "C001",
          "order": 1,
          "lat": 49.7292,
          "lng": 13.4067,
          "arrival_time": "08:15",
          "service_time": 120,
          "cumulative_load": 350
        }
      ],
      "distance_km": 45.2,
      "duration_min": 180,
      "load_volume": 12500,
      "load_weight": 4200,
      "cost": 361.6
    }
  ],
  "summary": {
    "total_containers": 150,
    "total_routes": 3,
    "total_distance_km": 145.8,
    "total_duration_min": 520,
    "total_cost": 1166.4,
    "vehicles_used": 3,
    "avg_stops_per_route": 50
  },
  "warnings": []
}
```

---

### Výpočet trasy

```http
POST /api/v1/route
```

Výpočet trasy mezi body pomocí OSRM.

**Request:**
```json
{
  "waypoints": [
    {"lat": 49.725, "lng": 13.378},
    {"lat": 49.729, "lng": 13.406}
  ],
  "profile": "driving",
  "overview": "simplified"
}
```

**Response:**
```json
{
  "distance_m": 4523,
  "distance_km": 4.52,
  "duration_s": 485,
  "duration_min": 8.1,
  "geometry": "encoded_polyline...",
  "legs": [
    {
      "distance": 4523,
      "duration": 485,
      "summary": "Klatovská třída"
    }
  ]
}
```

---

### Matice vzdáleností

```http
POST /api/v1/matrix
```

Výpočet matice vzdáleností mezi všemi body.

**Request:**
```json
{
  "locations": [
    {"lat": 49.725, "lng": 13.378},
    {"lat": 49.729, "lng": 13.406},
    {"lat": 49.731, "lng": 13.412}
  ],
  "profile": "driving"
}
```

**Response:**
```json
{
  "distances": [
    [0, 4.52, 5.81],
    [4.48, 0, 1.35],
    [5.72, 1.29, 0]
  ],
  "durations": [
    [0, 8.1, 10.2],
    [7.9, 0, 2.4],
    [9.8, 2.2, 0]
  ],
  "sources": 3,
  "destinations": 3
}
```

---

### Nejbližší bod na silnici

```http
GET /api/v1/nearest?lat=49.725&lng=13.378
```

**Response:**
```json
{
  "waypoints": [
    {
      "lat": 49.72501,
      "lng": 13.37812,
      "distance": 5.2,
      "name": "Klatovská třída"
    }
  ]
}
```

---

### Seznam algoritmů

```http
GET /api/v1/algorithms
```

**Response:**
```json
{
  "algorithms": [
    {
      "id": "fast",
      "name": "Rychlý (Nearest Neighbor)",
      "description": "Nejrychlejší, nejnižší kvalita",
      "gpu_required": false,
      "quality_estimate": "70-75%"
    },
    {
      "id": "cuopt",
      "name": "NVIDIA cuOpt (GPU)",
      "description": "Nejlepší kvalita, vyžaduje GPU",
      "gpu_required": true,
      "quality_estimate": "97-99%"
    }
  ]
}
```

---

## Chybové odpovědi

```json
{
  "error": true,
  "message": "Popis chyby",
  "status_code": 400
}
```

| Kód | Popis |
|-----|-------|
| 400 | Chybný požadavek |
| 404 | Nenalezeno |
| 500 | Interní chyba |
| 503 | Služba nedostupná |

---

## Příklady

### cURL

```bash
# Health check
curl http://localhost:8888/health

# Optimalizace
curl -X POST http://localhost:8888/api/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "depot": {"lat": 49.725588, "lng": 13.378361},
    "containers": [
      {"id": "C1", "lat": 49.729, "lng": 13.406, "volume": 1100}
    ]
  }'
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8888/api/v1/optimize",
    json={
        "depot": {"lat": 49.725588, "lng": 13.378361},
        "containers": [
            {"id": "C1", "lat": 49.729, "lng": 13.406, "volume": 1100}
        ],
        "options": {"algorithm": "cuopt"}
    }
)

result = response.json()
print(f"Trasy: {len(result['routes'])}")
print(f"Vzdálenost: {result['summary']['total_distance_km']} km")
```

### JavaScript

```javascript
const response = await fetch('http://localhost:8888/api/v1/optimize', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        depot: {lat: 49.725588, lng: 13.378361},
        containers: [
            {id: 'C1', lat: 49.729, lng: 13.406, volume: 1100}
        ]
    })
});

const result = await response.json();
console.log(`Trasy: ${result.routes.length}`);
```
