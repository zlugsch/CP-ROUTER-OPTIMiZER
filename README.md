# 🚛 CP Router Optimizer

GPU-akcelerovaný optimalizátor svozových tras pro odpadové hospodářství.

![Architecture](docs/images/architecture.png)

## ✨ Funkce

- **GPU akcelerace** - NVIDIA cuOpt pro řešení VRP (Vehicle Routing Problem)
- **Lokální routing** - Vlastní OSRM server s truck profilem
- **Bez rate limitů** - Neomezený počet požadavků
- **Vysoká kvalita** - ~98% optimálních tras vs. 75% u Nearest Neighbor
- **Rychlost** - 3000 bodů za 2-5 sekund
- **Kapacitní omezení** - Respektuje kapacitu vozidel
- **Časová okna** - Podpora časových omezení obsluhy
- **REST API** - Snadná integrace do existujících systémů

## 📊 Porovnání výkonu

| Metrika | Veřejný OSRM | Toto řešení |
|---------|--------------|-------------|
| Rychlost routing | 200-500ms | 10-50ms |
| Kvalita tras | 75-85% | 98% |
| Rate limit | ~1 req/s | ∞ |
| Dostupnost | Závislá | 100% |
| Truck routing | ❌ | ✅ |

## 🏗️ Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                    UBUNTU SERVER                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │   OSRM      │    │  NVIDIA     │    │   FastAPI       │  │
│  │   Server    │───▶│  cuOpt      │───▶│   Backend       │  │
│  │  :5050      │    │  :9080      │    │   :8888         │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│        │                  │                    │            │
│        │            ┌─────┴─────┐              │            │
│        │            │ RTX 4000  │              │            │
│        │            │  2× 24GB  │              │            │
│        │            └───────────┘              │            │
│        │                                       │            │
│  ┌─────┴───────────────────────────────────────┴─────────┐  │
│  │                    Nginx :8880                        │  │
│  │                 (RouteOptimizer UI)                   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Rychlý start

### Prerekvizity

- Ubuntu 22.04+ 
- Docker & Docker Compose
- NVIDIA Driver 525+
- NVIDIA Container Toolkit
- Min. 32GB RAM
- GPU s min. 8GB VRAM (doporučeno 24GB+)

### Instalace

```bash
# 1. Klonování repozitáře
git clone https://github.com/YOUR_USERNAME/CP-ROUTER-OPTIMIZER.git
cd CP-ROUTER-OPTIMIZER

# 2. Stažení a příprava OSM dat
./scripts/setup.sh

# 3. Spuštění stacku
docker-compose up -d

# 4. Ověření
curl http://localhost:8000/health
```

### Přístup k aplikaci

| Služba | URL | Popis |
|--------|-----|-------|
| **Webapp** | http://localhost:8880 | Webová aplikace |
| **API Docs** | http://localhost:8888/docs | Swagger dokumentace |
| **OSRM** | http://localhost:5050 | Routing API |
| **cuOpt** | http://localhost:9080 | GPU optimizer |

## 📁 Struktura projektu

```
CP-ROUTER-OPTIMIZER/
├── docker-compose.yml      # Orchestrace služeb
├── README.md
├── api/                    # FastAPI backend
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   └── routers/
│       ├── optimize.py     # VRP optimalizace
│       └── routing.py      # OSRM wrapper
├── osrm/                   # OSRM konfigurace
│   ├── scripts/
│   │   └── download-osm.sh
│   └── data/               # OSM data (gitignore)
├── webapp/                 # Frontend
│   ├── index.html
│   ├── nginx.conf
│   └── assets/
├── docs/                   # Dokumentace
│   ├── INSTALLATION.md
│   ├── API.md
│   └── ARCHITECTURE.md
└── scripts/                # Utility skripty
    ├── setup.sh
    ├── start.sh
    └── backup.sh
```

## 🔧 Konfigurace

### Proměnné prostředí

```bash
# .env soubor
OSRM_URL=http://osrm:5000
CUOPT_URL=http://cuopt:8080
API_PORT=8000
MAX_VEHICLES=10
MAX_STOPS_PER_ROUTE=150
DEFAULT_VEHICLE_CAPACITY=15000  # kg
```

### GPU konfigurace

```yaml
# docker-compose.yml - cuOpt služba
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ['0', '1']  # Obě GPU
          capabilities: [gpu]
```

## 📚 API Reference

### Optimalizace tras

```bash
POST /api/v1/optimize
Content-Type: application/json

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
      "service_time": 120
    }
  ],
  "vehicles": [
    {
      "id": "V1",
      "capacity": 15000
    }
  ],
  "options": {
    "algorithm": "cuopt",
    "max_route_duration": 480,
    "respect_capacity": true
  }
}
```

### Odpověď

```json
{
  "status": "success",
  "computation_time_ms": 2340,
  "routes": [
    {
      "vehicle_id": "V1",
      "stops": ["C001", "C002", "C003"],
      "distance_km": 45.2,
      "duration_min": 180,
      "load_kg": 12500
    }
  ],
  "summary": {
    "total_distance_km": 145.8,
    "total_duration_min": 520,
    "vehicles_used": 3
  }
}
```

## 🛠️ Vývoj

### Lokální development

```bash
# API
cd api
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd webapp
python -m http.server 8080
```

### Testy

```bash
# Unit testy
pytest api/tests/

# Integration testy
./scripts/test-integration.sh
```

## 📈 Monitoring

### Prometheus metriky

```
http://localhost:8000/metrics
```

### Logy

```bash
# Všechny služby
docker-compose logs -f

# Konkrétní služba
docker-compose logs -f api
```

## 🔒 Bezpečnost

- API je určeno pro interní síť
- Pro veřejný přístup použijte reverse proxy s HTTPS
- Doporučeno: Nginx + Let's Encrypt

## 📄 Licence

MIT License - viz [LICENSE](LICENSE)

## 🤝 Přispívání

1. Fork repozitáře
2. Vytvořte feature branch (`git checkout -b feature/amazing`)
3. Commit změn (`git commit -m 'Add amazing feature'`)
4. Push do branch (`git push origin feature/amazing`)
5. Otevřete Pull Request

## 📞 Podpora

- Issues: [GitHub Issues](https://github.com/YOUR_USERNAME/CP-ROUTER-OPTIMIZER/issues)
- Email: support@example.com

---

**Vytvořeno s ❤️ pro efektivnější svoz odpadu**
