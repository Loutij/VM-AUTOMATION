# HANDOFF - Transfert de Session

**Date**: 2026-03-05
**Branch**: `fix/869bxxy54-bug-fixes`

---

## Identifiants par defaut des VMs

| OS | Utilisateur | Mot de passe |
|----|-------------|-------------|
| Windows Server 2019/2022 | `.\Administrateur` | `TempP@ss123!` |
| Windows 10/11 | `.\Admin` (+ `.\Administrateur` active) | `TempP@ss123!` |
| Debian/Ubuntu | `admin` | `TempP@ss123!` |
| RHEL/Rocky | `root` | `TempP@ss123!` |

> Le prefixe `.\` indique un compte local (pas domaine).

---

## Etat actuel du projet

### Fonctionnel

1. **Deploiement complet Windows** (DISM) - Server 2019/2022, Win10, Win11
2. **Deploiement complet Linux** (ISO + preseed/cloud-init) - Debian 12/13, Ubuntu, RHEL/Rocky
3. **Post-installation automatique** - RDP, WinRM, SSH, logiciels Chocolatey
4. **Frontend complet** - Dashboard, VMs, Deploiements, Templates, Hyperviseurs, Marketplace
5. **Console VM** - Screenshots WMI + clavier via WebSocket
6. **Terminal PowerShell** - PowerShell Direct via WebSocket
7. **Selection automatique du template unattend** selon l'OS (Win10/11 vs Server)
8. **Support localisation FR/EN** - Firewall, comptes admin, groupes
9. **Catalogue logiciels** - 150+ packages Windows
10. **Notifications email** - Deploiement termine

### Corrections recentes (2026-03-05)

1. **Bug RDP** : Firewall FR ("Bureau a distance") non gere + NLA bloquante
2. **Bug compte desactive Win10/11** : Template Server utilise pour toutes les editions
3. **Selection template unattend** : Automatique selon l'OS (Win10/11/Server 2019/2022)
4. **admin_username** dans config deploiement : `Admin` pour Win10/11, `Administrateur` pour Server
5. **Documentation** : Reecrite completement dans `/docs/`

### A faire

- Support VMware vCenter (pyVmomi)
- Tests unitaires et d'integration
- CI/CD GitHub Actions
- Monitoring avance (Prometheus/Grafana)
- Backup/restore des VMs
- Multi-tenancy

---

## Architecture rapide

```
Frontend (React/Vite:5173) → API (FastAPI:8000) → Celery (Redis:6379) → Hyper-V (WinRM:5986)
                                    ↓
                              PostgreSQL:5432
```

## Fichiers cles

| Fichier | Description |
|---------|-------------|
| `src/api/main.py` | Point d'entree API |
| `src/domain/deployment_service.py` | Logique deploiement (163K, fichier principal) |
| `src/domain/template_engine.py` | Rendu templates Jinja2 |
| `src/integrations/hypervisors/hyperv_client.py` | Client Hyper-V (PowerShell/WinRM) |
| `src/workers/tasks.py` | Taches Celery |
| `templates/unattend/*.xml` | Templates Windows |
| `templates/preseed/*.cfg` | Templates Debian |
| `frontend/src/pages/NewDeployment.tsx` | Formulaire deploiement (88K) |

## Commandes utiles

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

## Documentation

Voir [docs/README.md](README.md) pour l'index complet de la documentation.
