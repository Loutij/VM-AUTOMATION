# VM Automation Tool

[![CI](https://github.com/Loutij/VM-AUTOMATION/actions/workflows/ci.yml/badge.svg)](https://github.com/Loutij/VM-AUTOMATION/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)
[![License: Proprietary](https://img.shields.io/badge/license-proprietary-red.svg)]()

Outil d'automatisation complète du déploiement de machines virtuelles pour **Hyper-V** (et VMware à terme).

## Objectif

Supprimer **100% de l'intervention humaine** lors de la création, de l'installation et de la configuration des serveurs virtuels. Une machine est prête à l'usage dès le premier démarrage.

---

## Avancement Global : **~79%**

| Phase | Description | Avancement |
|-------|-------------|------------|
| Phase 1 | Fondations (API, DB, Hyper-V) | ✅ **100%** |
| Phase 2 | Création VMs (CPU, RAM, réseau, wizard) | ✅ **100%** |
| Phase 3 | Installation OS automatique | ✅ **85%** |
| Phase 4 | Post-installation (AD, services) | ✅ **87%** |
| Phase 5 | Installation logiciels | 🔄 **65%** |
| Phase 6 | Orchestration & monitoring | 🔄 **75%** |
| Phase 7 | Interface web React | ✅ **76%** |
| Phase 8 | Industrialisation | ⬜ **8%** |
| Phase 9 | Support VMware | ⬜ **0%** |

---

## Fonctionnalités Implémentées

### Backend (Python/FastAPI)

| Module | Fonctionnalités | Statut |
|--------|-----------------|--------|
| **Client Hyper-V** | Connexion WinRM, CRUD VMs, start/stop/restart | ✅ |
| **Gestion Réseau** | Switches, VLAN, multi-NIC, infos réseau complètes (IP, MAC, gateway, DNS) | ✅ |
| **Gestion Switches** | CRUD switches virtuels (Internal/External/Private), adaptateurs physiques | ✅ |
| **Gestion Stockage** | VHDX dynamique/fixe, multi-disques, resize | ✅ |
| **Installation OS** | Templates Windows Server 2022, Ubuntu, Debian | ✅ |
| **Génération Templates** | Moteur Jinja2, injection hostname/réseau/password | ✅ |
| **Post-Installation** | Windows Update, services, firewall, password policies | ✅ |
| **Installation Logiciels** | Chocolatey, 6 profils (minimal, tools, dev, web, monitoring, db) | ✅ |
| **Monitoring** | Heartbeat, PowerShell Direct, Integration Services | ✅ |
| **WebSocket** | Temps réel, SSE, notifications push | ✅ |
| **Auth JWT** | bcrypt + jose, tokens sécurisés | ✅ |

### Frontend (React 19 / TypeScript)

| Page | Fonctionnalités | Statut |
|------|-----------------|--------|
| **Dashboard** | Stats temps réel, déploiements récents, actions rapides | ✅ |
| **Hyperviseurs** | CRUD complet, test connexion, DataTable | ✅ |
| **VMs** | Liste, filtres, actions (start/stop/restart/delete) | ✅ |
| **Templates** | CRUD, grille, filtres par OS, duplication | ✅ |
| **Déploiements** | Timeline, logs modal, cancel/retry, auto-refresh | ✅ |
| **Nouveau Déploiement** | Wizard 5 étapes (infra, ressources, réseau, options, résumé) | ✅ |
| **Paramètres** | Configuration multi-sections complète | ✅ |
| **Aide** | Documentation, FAQ, raccourcis, dépannage | ✅ |

### Composants UI

- Button (variants, sizes, loading, icons)
- Modal + ConfirmModal
- Toast + ToastProvider + useToast
- DataTable (tri, search, pagination, actions)
- Input, Textarea, Select, Switch
- EmptyState, StatusBadge, StatCard
- StepIndicator (wizard navigation)
- FAQAccordion (aide interactive)

---

## Stack Technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| Backend API | Python + FastAPI | 3.11+ |
| Frontend | React + TypeScript | 19.2 / 5.9 |
| Build Tool | Vite | 7.2 |
| Styling | TailwindCSS | 4.1 |
| State Management | React Query | 5.90 |
| Routing | React Router | 7.13 |
| Database | PostgreSQL | 15+ |
| Cache/Queue | Redis | 7+ |
| Hyperviseur | Hyper-V (PowerShell/WinRM) | - |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Frontend (React)                          │
│  Dashboard │ Hypervisors │ VMs │ Templates │ Deployments │ Settings │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ REST API + WebSocket
┌──────────────────────────────▼──────────────────────────────────────┐
│                         Backend (FastAPI)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│  │   Routers   │  │  Services   │  │   Models    │  │    Auth     ││
│  │ /api/v1/*   │  │ VMService   │  │ SQLAlchemy  │  │ JWT/bcrypt  ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘│
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                        Integrations                                  │
│  ┌─────────────────────┐  ┌─────────────────────┐                   │
│  │   Hyper-V Client    │  │   Template Engine   │                   │
│  │   (PowerShell/WinRM)│  │   (Jinja2)          │                   │
│  └─────────────────────┘  └─────────────────────┘                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    Infrastructure                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │  PostgreSQL  │  │    Redis     │  │   Hyper-V    │               │
│  │  (Database)  │  │  (Cache/Queue)│ │   (Host)     │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Workflow de Déploiement

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  1. Créer   │───▶│ 2. Install  │───▶│ 3. Config   │───▶│ 4. Software │
│     VM      │    │     OS      │    │  Post-inst  │    │   Install   │
│ (2-5 min)   │    │ (15-30 min) │    │ (5-10 min)  │    │ (5-15 min)  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │
       │   ISO Windows    │   unattend.xml   │   AD Join        │   Chocolatey
       │   + ISO OEMDRV   │   (Jinja2)       │   WinRM/RDP      │   Profils
       │                  │                  │   Updates        │
       ▼                  ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      VM 100% PRÊTE (~30-60 min)                     │
│   ✅ OS installé   ✅ Réseau configuré   ✅ Logiciels installés     │
│   ✅ Domain joint  ✅ Services actifs    ✅ Sécurité appliquée      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Installation

### Prérequis

- Windows Server 2019+ avec rôle Hyper-V
- Python 3.11+
- Node.js 20+
- PostgreSQL 15+
- Redis 7+

### Backend

```bash
# Cloner
git clone https://github.com/Loutij/VM-AUTOMATION.git
cd VM-AUTOMATION

# Environment virtuel
python -m venv venv
source venv/bin/activate  # Linux
.\venv\Scripts\Activate   # Windows

# Dépendances
pip install -r requirements.txt

# Configuration
cp config/env.example .env
# Éditer .env avec vos valeurs

# Services (Docker)
docker-compose up -d

# Migrations DB
alembic upgrade head

# Lancer l'API
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend

# Dépendances
npm install

# Lancer en dev
npm run dev
```

### Accès

- **API**: http://localhost:8000
- **Swagger**: http://localhost:8000/docs
- **Frontend**: http://localhost:5173

---

## Configuration

### Variables d'environnement (.env)

```env
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=vm_automation
DB_USER=postgres
DB_PASSWORD=your_password

# Redis
REDIS_URL=redis://localhost:6379

# Security
API_SECRET_KEY=your_secret_key_here

# Hyper-V
HYPERV_HOST=10.250.0.20
HYPERV_USER=administrator
HYPERV_PASSWORD=your_password
HYPERV_USE_SSL=false

# Paths
HYPERV_VM_PATH=C:\HyperV\VirtualMachines
HYPERV_VHDX_PATH=C:\HyperV\VirtualHardDisks
HYPERV_ISO_PATH=C:\HyperV\ISOs
```

---

## Structure du Projet

```
VM-AUTOMATION/
├── src/                        # Backend Python
│   ├── api/                    # FastAPI endpoints
│   │   ├── routers/            # vms, templates, deployments, hypervisors, auth
│   │   ├── websocket.py        # WebSocket manager
│   │   └── main.py             # App FastAPI
│   ├── domain/                 # Logique métier
│   │   ├── models.py           # 8 modèles SQLAlchemy
│   │   ├── vm_service.py       # Service VM complet
│   │   ├── deployment_service.py
│   │   ├── post_install_service.py
│   │   ├── software_install_service.py
│   │   └── template_engine.py  # Jinja2
│   ├── integrations/           # Clients externes
│   │   └── hypervisors/
│   │       ├── base.py         # Interface abstraite
│   │       └── hyperv_client.py # Client Hyper-V (60+ méthodes)
│   └── common/                 # Utilitaires
│       ├── config.py           # Pydantic Settings
│       ├── database.py         # SQLAlchemy async
│       ├── auth.py             # JWT
│       └── powershell.py       # WinRM wrapper
│
├── frontend/                   # React app
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/         # MainLayout, Sidebar, Header
│   │   │   └── ui/             # 10+ composants réutilisables
│   │   ├── pages/              # 7 pages
│   │   ├── services/           # api.ts (Axios)
│   │   └── types/              # Types TypeScript
│   ├── package.json
│   └── vite.config.ts
│
├── templates/                  # Templates installation OS
│   ├── unattend/               # Windows (autounattend.xml)
│   ├── preseed/                # Debian
│   ├── cloud-init/             # Ubuntu
│   └── kickstart/              # RHEL/Rocky
│
├── alembic/                    # Migrations DB
├── scripts/                    # Scripts utilitaires & tests
├── docs/                       # Documentation
├── tests/                      # Tests
├── docker-compose.yml          # PostgreSQL + Redis
└── requirements.txt            # Dépendances Python
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [TASKS.md](./docs/TASKS.md) | Suivi détaillé des 189 tâches |
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Architecture technique |
| [PREREQUISITES.md](./docs/PREREQUISITES.md) | Prérequis d'installation |
| [GETTING_STARTED.md](./docs/GETTING_STARTED.md) | Guide de démarrage |
| [UNATTENDED_INSTALL.md](./docs/UNATTENDED_INSTALL.md) | Installation automatique OS |

---

## VM de Test Validée

**WinSrv2022-Test** sur Hyper-V 10.250.0.20

| Propriété | Valeur |
|-----------|--------|
| OS | Windows Server 2022 Standard |
| Config | 2 vCPU, 4 GB RAM, 60 GB Disk |
| IP | 10.250.0.83 |
| Gateway | 10.250.0.254 |
| DNS | 1.1.1.1, 8.8.8.8 |
| Heartbeat | OkApplicationsUnknown ✅ |
| PowerShell Direct | Fonctionnel ✅ |
| RDP/WinRM/SSH | Activés ✅ |
| Chocolatey | v2.6.0 ✅ |
| Logiciels | 7zip, Notepad++ ✅ |

---

## Contribution

1. Créer une branche feature (`git checkout -b feat/ma-feature`)
2. Commiter (`git commit -m "feat(module): description"`)
3. Pusher (`git push origin feat/ma-feature`)
4. Créer une Pull Request

### Convention de commits

```
type(scope): description

Types: feat, fix, refactor, docs, test, chore
```

---

## Prochaines Étapes

1. 🚀 **Wizard de création VM** - Interface multi-étapes
2. 🐧 **Support Linux apt/yum** - Installation packages
3. 🔌 **WebSocket frontend** - Temps réel complet
4. 🔒 **RBAC** - Gestion des rôles utilisateurs
5. 📊 **Monitoring Prometheus** - Métriques application

---

## Licence

Propriétaire - Usage interne uniquement

## Contact

**Équipe Infrastructure IT**  
Repository: https://github.com/Loutij/VM-AUTOMATION  
ClickUp: Tâche VM-AUTOMATION (869bxaf8k)

---

*Dernière mise à jour : 2026-01-26 18:00*
