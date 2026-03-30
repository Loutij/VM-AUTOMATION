# VM Automation - Documentation

> La documentation complete du projet se trouve dans le dossier [`docs/`](docs/README.md).

## Index rapide

| Document | Description |
|----------|-------------|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Installation et premier lancement |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture technique et structure du code |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Reference API REST et WebSocket |
| [docs/DEPLOYMENT_WORKFLOW.md](docs/DEPLOYMENT_WORKFLOW.md) | Flux de deploiement VM |
| [docs/TEMPLATES.md](docs/TEMPLATES.md) | Templates d'installation (unattend, preseed, cloud-init) |
| [docs/UNATTENDED_INSTALL.md](docs/UNATTENDED_INSTALL.md) | Guide technique installation automatique Windows |
| [docs/POST_INSTALL.md](docs/POST_INSTALL.md) | Post-installation (RDP, WinRM, SSH, logiciels) |
| [docs/FRONTEND.md](docs/FRONTEND.md) | Application frontend React |
| [docs/ENV_REFERENCE.md](docs/ENV_REFERENCE.md) | Variables d'environnement |
| [docs/PREREQUISITES.md](docs/PREREQUISITES.md) | Prerequis infrastructure |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Guide de depannage |
| [docs/HANDOFF.md](docs/HANDOFF.md) | Etat du projet et transfert de session |

## Identifiants par defaut des VMs

| OS | Utilisateur | Mot de passe |
|----|-------------|-------------|
| Windows Server 2019/2022 | `.\Administrateur` | `TempP@ss123!` |
| Windows 10/11 | `.\Admin` (+ `.\Administrateur` active) | `TempP@ss123!` |
| Debian/Ubuntu | `admin` | `TempP@ss123!` |
| RHEL/Rocky | `root` | `TempP@ss123!` |

## Commandes rapides

```bash
# Backend
source .venv/bin/activate
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Celery
celery -A src.workers.celery_app worker --loglevel=info

# Frontend
cd frontend && npm run dev

# Docker (PostgreSQL + Redis)
docker compose up -d

# Migrations DB
alembic upgrade head
```

## Stack technique

- **Backend** : Python 3.11+ / FastAPI / SQLAlchemy / Celery
- **Frontend** : React 19 / TypeScript 5.9 / Vite / TailwindCSS
- **Infrastructure** : PostgreSQL / Redis / Docker Compose
- **Hyperviseur** : Hyper-V via WinRM/PowerShell + DISM
