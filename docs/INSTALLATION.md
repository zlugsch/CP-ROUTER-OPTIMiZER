# 🛠️ Instalace CP Router Optimizer

## Požadavky

### Hardware
- **CPU**: Min. 4 jádra
- **RAM**: Min. 16 GB (doporučeno 32 GB)
- **Disk**: Min. 20 GB volného místa
- **GPU**: NVIDIA s min. 8 GB VRAM (doporučeno 24 GB+)

### Software
- Ubuntu 22.04 LTS nebo novější
- Docker 24.0+
- Docker Compose 2.0+
- NVIDIA Driver 525+
- NVIDIA Container Toolkit

## Krok 1: Instalace Docker

```bash
# Aktualizace systému
sudo apt update && sudo apt upgrade -y

# Instalace Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Přidání uživatele do skupiny docker
sudo usermod -aG docker $USER

# Odhlášení a přihlášení (nebo reboot)
newgrp docker

# Ověření
docker --version
docker compose version
```

## Krok 2: NVIDIA Container Toolkit

```bash
# Přidání repozitáře
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Instalace
sudo apt update
sudo apt install -y nvidia-container-toolkit

# Konfigurace Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Ověření
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

## Krok 3: Klonování projektu

```bash
# Klonování
git clone https://github.com/YOUR_USERNAME/CP-ROUTER-OPTIMIZER.git
cd CP-ROUTER-OPTIMIZER

# Nastavení práv
chmod +x scripts/*.sh
```

## Krok 4: Stažení OSM dat

```bash
# Spuštění setup skriptu
./scripts/setup.sh

# Tento skript:
# 1. Stáhne OSM data pro ČR (~700 MB)
# 2. Zpracuje data pro OSRM (trvá 10-30 minut)
# 3. Připraví truck profil
```

## Krok 5: Spuštění

```bash
# Spuštění všech služeb
./scripts/start.sh

# Nebo manuálně
docker-compose up -d
```

## Krok 6: Ověření

```bash
# Health check
curl http://localhost:8888/health

# API dokumentace
xdg-open http://localhost:8888/docs

# Webová aplikace
xdg-open http://localhost:8880
```

## Řešení problémů

### OSRM nespouští

```bash
# Kontrola logů
docker-compose logs osrm

# Ověření dat
ls -la osrm/data/*.osrm*

# Přegenerování dat
rm -rf osrm/data/*.osrm*
./scripts/setup.sh
```

### cuOpt nespouští

```bash
# Kontrola GPU
nvidia-smi

# Kontrola logů
docker-compose logs cuopt

# Test GPU v Dockeru
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### API chyby

```bash
# Kontrola logů
docker-compose logs api

# Restart
docker-compose restart api
```

## Aktualizace

```bash
# Stažení nové verze
git pull

# Rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Zálohování

```bash
# Záloha konfigurace
tar -czvf backup-config.tar.gz .env docker-compose.yml

# Záloha OSRM dat (volitelné - lze regenerovat)
tar -czvf backup-osrm.tar.gz osrm/data/
```

## Odinstalace

```bash
# Zastavení služeb
docker-compose down

# Odstranění obrazů
docker-compose down --rmi all

# Odstranění dat
rm -rf osrm/data/
rm -rf logs/
```
