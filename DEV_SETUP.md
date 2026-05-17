# DZFoot — Development Setup Guide

## Architecture Dev

```
┌──────────────────────────────────────────────────────────────┐
│                    MACHINE DEV (Linux / WSL2)               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Docker Compose Dev (all-in-one)                     │  │
│  │                                                      │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐ │  │
│  │  │ Account │  │ Session │  │ Match.  │  │ Stats   │ │  │
│  │  │ :8001   │  │ :8002   │  │ :8003   │  │ :8004   │ │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘ │  │
│  │       ┌─────────┐  ┌─────────┐  ┌─────────┐       │  │
│  │       │ Catalog │  │  Nginx  │  │  Redis  │       │  │
│  │       │ :8005   │  │ :8080   │  │ :6379   │       │  │
│  │       └─────────┘  └─────────┘  └─────────┘       │  │
│  │                          ┌─────────┐                 │  │
│  │                          │PostgreSQL│                 │  │
│  │                          │ :5432   │                 │  │
│  │                          └─────────┘                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  GF Server (natif, pas Docker)                        │  │
│  │  ./gf_server --room-id=test --redis-url=redis://...  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP 8080 / Redis 6379
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                    PC WINDOWS (Émulateur Android)               │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Android Emulator (Android Studio)                     │  │
│  │                                                        │  │
│  │  App DZFoot → LiveKit room + data channels            │  │
│  │           → HTTP calls to backend :8080               │  │
│  │                                                        │  │
│  │  ADB reverse tcp:8080 tcp:8080  (port forwarding)    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Prérequis

### Machine Dev (Linux ou WSL2 Windows)

| Outil | Version | Install |
|---|---|---|
| Docker + Docker Compose | 24.x+ | `sudo apt install docker.io docker-compose-plugin` |
| Git | 2.40+ | `sudo apt install git` |
| Python | 3.12 | (dans les containers) |
| C++ build tools | g++ 11+, cmake 3.22+ | `sudo apt install build-essential cmake` |
| Redis CLI | 7.x | `sudo apt install redis-tools` |

### PC Windows (Émulateur)

| Outil | Version | Install |
|---|---|---|
| Android Studio | Hedgehog+ | [developer.android.com/studio](https://developer.android.com/studio) |
| Android Emulator | API 34 | Via SDK Manager |
| Git for Windows | 2.40+ | [git-scm.com](https://git-scm.com) |
| ADB | platform-tools | Via SDK Manager |

---

## Setup Machine Dev (Linux/WSL2)

### 1. Cloner les repos

```bash
cd ~/projects

git clone https://github.com/YOUR_ORG/dzfoot-backend.git
git clone https://github.com/YOUR_ORG/dzfoot-gf-server.git
# dzfoot-android reste sur PC Windows
```

### 2. Configurer environnement

```bash
cd dzfoot-backend
cp .env.example .env
# Éditer .env avec tes credentials LiveKit
```

### 3. Démarrer le backend

```bash
docker-compose -f docker-compose.dev.yml up --build -d
```

Attendre 10s, puis vérifier :
```bash
# Healthcheck
curl http://localhost:8080/health
# → 200 OK

# Services individuels
curl http://localhost:8001/health
curl http://localhost:8002/health
# etc.
```

### 4. Compiler GF Server (natif, pas Docker)

```bash
cd ../dzfoot-gf-server

# Build
cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)

# Tester en mode local (sans LiveKit)
./gf_server \
  --room-id=dev-test \
  --team-a=algeria \
  --team-b=morocco \
  --duration=60 \
  --redis-url=redis://localhost:6379
```

### 5. Vérifier Redis

```bash
# Lister les workers actifs
redis-cli HGETALL gf.workers

# Lister les matchs actifs
redis-cli HGETALL gf.active

# Taille de la queue
redis-cli LLEN gf.spawn
```

---

## Setup PC Windows (Émulateur Android)

### 1. Cloner dzfoot-android

```powershell
cd C:\Users\%USERNAME%\projects
git clone https://github.com/YOUR_ORG/dzfoot-android.git
```

### 2. Ouvrir dans Android Studio

```
File → Open → C:\Users\%USERNAME%\projects\dzfoot-android
```

### 3. Configurer l'émulateur

```
Device Manager → Create Device
→ Pixel 7 → API 34 → Download system image
→ Finish → Launch
```

### 4. Port forwarding ADB

Dans un terminal Windows (PowerShell ou CMD) :

```powershell
# Forwarder le port 8080 de la machine dev vers l'émulateur
adb reverse tcp:8080 tcp:8080

# Vérifier que l'émulateur voit le backend
adb shell curl http://localhost:8080/health
```

**Si la machine dev est sur le réseau local** (pas WSL2) :
```powershell
# Remplacer localhost par l'IP de la machine dev
# Ex: http://192.168.1.42:8080
```

**Si WSL2** (Windows 10/11) :
```powershell
# Obtenir l'IP WSL2
wsl hostname -I
# → 172.23.xxx.xxx

# Utiliser cette IP dans le code client Android
# ou configurer adb reverse
```

### 5. Configurer l'IP backend dans le client

Modifier `MainActivity.kt` ou un fichier config :
```kotlin
val BACKEND_URL = "http://localhost:8080"  // adb reverse
// ou
val BACKEND_URL = "http://192.168.1.42:8080"  // IP réseau local
```

### 6. Builder et installer l'APK

Dans Android Studio :
```
Build → Build Bundle(s) / APK(s) → Build APK(s)
Run → Run 'app'
```

Ou en ligne de commande :
```powershell
cd dzfoot-android\app
.\gradlew assembleDebug
adb install .\build\outputs\apk\debug\app-debug.apk
```

---

## Workflow développement quotidien

### Jour type

```bash
# 1. Machine Dev — Démarrer le stack
cd ~/projects/dzfoot-backend
docker-compose -f docker-compose.dev.yml up -d

# 2. Vérifier que tout est OK
./scripts/healthcheck.sh

# 3. Modifier du code backend → hot reload automatique (uvicorn --reload)
# Les containers rechargent le code sans restart

# 4. Modifier du code C++ GF → recompiler
cd ~/projects/dzfoot-gf-server/build && make -j$(nproc)

# 5. PC Windows — Lancer émulateur + adb reverse
adb reverse tcp:8080 tcp:8080

# 6. Modifier code Android → Run dans Android Studio (Shift+F10)

# 7. À la fin de la journée
cd ~/projects/dzfoot-backend
docker-compose -f docker-compose.dev.yml down
```

---

## Différences dev vs prod

| Aspect | Dev | Prod |
|---|---|---|
| **Hot reload** | ✅ `uvicorn --reload` | ❌ (start normal) |
| **Code bind mount** | ✅ Volume `./service:/app` | ❌ Copié dans image |
| **Logs** | DEBUG verbeux | INFO/ERROR |
| **GF spawn** | Local subprocess | Redis queue + VM pool |
| **PostgreSQL** | Volume `pgdata_dev` | Volume `pgdata` |
| **Ports exposés** | Tous (8001-8005, 5432, 6379) | Seulement 8080, 5432, 6379 |
| **Nginx** | Basique | `nginx.prod.conf` avec least_conn |

**Compatibilité** : Les images Docker sont identiques. Seuls les mounts et les commandes diffèrent.

---

## Dépannage

### Problème : `docker-compose.dev.yml: service "session" depends on undefined service "postgres"`

```bash
# Utiliser le bon fichier
docker-compose -f docker-compose.dev.yml up -d
# PAS juste docker-compose up
```

### Problème : Émulateur ne voit pas le backend

```powershell
# Vérifier adb reverse
adb reverse --list

# Si vide, recréer
adb reverse tcp:8080 tcp:8080
adb reverse tcp:5432 tcp:5432  # optionnel, pour debug DB

# Tester depuis l'émulateur
adb shell curl http://localhost:8080/health
```

### Problème : WSL2 IP change à chaque reboot

```bash
# Créer un script .bashrc
alias wslip="ip addr show eth0 | grep 'inet ' | cut -d' ' -f6 | cut -d/ -f1"
# Utiliser $(wslip) dans les configs
```

### Problème : GF binary non trouvé par Session Service

```bash
# Le binary doit être monté en volume
# Vérifier que GF_BINARY_PATH pointe vers le fichier compilé
ls -la $(echo $GF_BINARY_PATH)
# → doit afficher gf_server exécutable
```

---

## Ports utilisés en dev

| Port | Service | Usage |
|---|---|---|
| 8080 | Nginx gateway | Tout le backend (auth, session, etc.) |
| 8001 | Account (direct) | Debug direct |
| 8002 | Session (direct) | Debug direct |
| 8003 | Matchmaking (direct) | Debug direct |
| 8004 | Stats (direct) | Debug direct |
| 8005 | Catalog (direct) | Debug direct |
| 5432 | PostgreSQL | pgAdmin, DBeaver, psql |
| 6379 | Redis | redis-cli, RedisInsight |

**Attention** : Sur Windows, vérifiez que ces ports ne sont pas utilisés par d'autres services (WAMP, XAMPP, etc.).
