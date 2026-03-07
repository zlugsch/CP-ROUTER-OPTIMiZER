# 🏗️ Architektura CP Router Optimizer

## Přehled

CP Router Optimizer je GPU-akcelerovaný systém pro optimalizaci svozových tras. Využívá NVIDIA cuOpt pro řešení Vehicle Routing Problem (VRP) a lokální OSRM server pro výpočet reálných vzdáleností.

## Komponenty

```
┌─────────────────────────────────────────────────────────────────┐
│                         UBUNTU SERVER                           │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │             │  │             │  │                         │  │
│  │    OSRM     │  │   cuOpt     │  │      FastAPI            │  │
│  │   Server    │◀─│   (GPU)     │◀─│      Backend            │  │
│  │             │  │             │  │                         │  │
│  │  Port 5050  │  │  Port 9080  │  │      Port 8888          │  │
│  │             │  │             │  │                         │  │
│  └─────────────┘  └──────┬──────┘  └────────────┬────────────┘  │
│         │                │                      │               │
│         │          ┌─────┴─────┐                │               │
│         │          │           │                │               │
│         │          │  NVIDIA   │                │               │
│         │          │   GPU     │                │               │
│         │          │  2×24GB   │                │               │
│         │          │           │                │               │
│         │          └───────────┘                │               │
│         │                                       │               │
│  ┌──────┴───────────────────────────────────────┴────────────┐  │
│  │                                                           │  │
│  │                    Nginx (Port 8880)                      │  │
│  │                                                           │  │
│  │              ┌─────────────────────────┐                  │  │
│  │              │    Route Optimizer      │                  │  │
│  │              │     Web Application     │                  │  │
│  │              └─────────────────────────┘                  │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/HTTPS
                              ▼
                    ┌─────────────────┐
                    │     Klient      │
                    │   (Prohlížeč)   │
                    └─────────────────┘
```

## Služby

### 1. OSRM Server

**Účel:** Výpočet reálných silničních vzdáleností a časů.

**Technologie:**
- OSRM (Open Source Routing Machine)
- Data: OpenStreetMap pro ČR
- Profil: Truck (nákladní vozidla)

**Endpointy:**
- `/route/v1/driving/{coords}` - Výpočet trasy
- `/table/v1/driving/{coords}` - Matice vzdáleností
- `/nearest/v1/driving/{coord}` - Nejbližší bod na silnici

**Výhody vlastního serveru:**
- Bez rate limitů
- Nízká latence (10-50ms vs 200-500ms)
- Truck profil (respektuje omezení pro nákladní vozy)
- 100% dostupnost

### 2. NVIDIA cuOpt

**Účel:** GPU-akcelerovaná optimalizace tras (VRP solver).

**Technologie:**
- NVIDIA cuOpt
- CUDA
- Využívá obě RTX 4000 GPU

**Funkce:**
- Řešení Vehicle Routing Problem
- Kapacitní omezení
- Časová okna
- Vyvažování tras
- Minimalizace vzdálenosti/času/nákladů

**Výkon:**
- 3000 bodů za 2-5 sekund
- Kvalita ~98% optima (vs. 75% Nearest Neighbor)

### 3. FastAPI Backend

**Účel:** Orchestrace služeb, business logika, REST API.

**Technologie:**
- Python 3.11
- FastAPI
- Pydantic validace
- Async HTTP (httpx)

**Funkce:**
- Validace vstupních dat
- Volání OSRM pro matici vzdáleností
- Volání cuOpt pro optimalizaci
- Fallback algoritmy (NN, 2-opt)
- API dokumentace (Swagger)

### 4. Nginx + Web Application

**Účel:** Statický web server + reverse proxy.

**Funkce:**
- Servírování webové aplikace
- Proxy na API (`/api/` → FastAPI)
- Proxy na OSRM (`/osrm/` → OSRM)
- Gzip komprese
- Cachování statických souborů

## Datový tok

### Optimalizace tras

```
1. Uživatel nahraje Excel s nádobami
2. Webapp parsuje data a zobrazí na mapě
3. Uživatel klikne "Optimalizovat"
4. Webapp → POST /api/v1/optimize
5. FastAPI validuje request
6. FastAPI → OSRM: Matice vzdáleností
7. FastAPI → cuOpt: VRP optimalizace
8. cuOpt vrátí optimální trasy
9. FastAPI sestaví response
10. Webapp zobrazí trasy na mapě
```

### Sequence diagram

```
┌──────┐     ┌───────┐     ┌──────┐     ┌───────┐
│Webapp│     │FastAPI│     │ OSRM │     │ cuOpt │
└──┬───┘     └───┬───┘     └──┬───┘     └───┬───┘
   │             │            │             │
   │ POST /optimize           │             │
   │────────────>│            │             │
   │             │            │             │
   │             │ GET /table │             │
   │             │───────────>│             │
   │             │            │             │
   │             │  Distance  │             │
   │             │   Matrix   │             │
   │             │<───────────│             │
   │             │            │             │
   │             │ POST /routes             │
   │             │─────────────────────────>│
   │             │            │             │
   │             │         Optimized Routes │
   │             │<─────────────────────────│
   │             │            │             │
   │  Response   │            │             │
   │<────────────│            │             │
   │             │            │             │
```

## Algoritmy

### Hierarchie algoritmů

```
┌─────────────────────────────────────────────────────────┐
│                     cuOpt (GPU)                        │
│                    Kvalita: 98%                        │
│                    Čas: 2-5s                           │
└───────────────────────┬─────────────────────────────────┘
                        │ fallback
┌───────────────────────▼─────────────────────────────────┐
│               Quality (NN + 2-opt + Or-opt)            │
│                    Kvalita: 92%                        │
│                    Čas: 30-60s                         │
└───────────────────────┬─────────────────────────────────┘
                        │ fallback
┌───────────────────────▼─────────────────────────────────┐
│                 Balanced (NN + 2-opt)                  │
│                    Kvalita: 88%                        │
│                    Čas: 10-30s                         │
└───────────────────────┬─────────────────────────────────┘
                        │ fallback
┌───────────────────────▼─────────────────────────────────┐
│                  Fast (Nearest Neighbor)               │
│                    Kvalita: 75%                        │
│                    Čas: 1-3s                           │
└─────────────────────────────────────────────────────────┘
```

## Škálování

### Vertikální
- Více GPU paměti → Větší problémy
- Rychlejší GPU → Rychlejší výpočet
- Více CPU jader → Paralelní OSRM požadavky

### Horizontální
- Load balancer před Nginx
- Více API instancí
- Redis pro sdílení stavu

## Bezpečnost

### Aktuální stav (interní síť)
- Bez autentizace
- HTTP (ne HTTPS)
- CORS: *

### Produkční doporučení
- API klíče nebo OAuth
- HTTPS (Let's Encrypt)
- CORS: konkrétní domény
- Rate limiting
- WAF

## Monitoring

### Dostupné metriky
- `/health` - Stav služeb
- `/metrics` - Prometheus metriky (plánováno)
- Docker logs

### Doporučené nástroje
- Prometheus + Grafana
- Sentry pro error tracking
- Uptime monitoring
