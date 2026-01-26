# VM Automation Tool - Documentation Principale

## Description du Projet

Outil interne d'automatisation complète du déploiement de machines virtuelles. L'objectif est de supprimer toute intervention humaine lors de la création, de l'installation et de la configuration des serveurs ou postes virtuels, afin qu'une machine soit 100% prête à l'usage dès le premier démarrage.

**Infrastructure cible** : Hyper-V (initial), VMware (futur)

---

## Fonctionnalités

### Module 1 : Gestion des Hyperviseurs
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Connexion Hyper-V | TERMINÉ | Client PowerShell/WinRM pour Hyper-V |
| Liste des VMs | TERMINÉ | Récupération des VMs existantes |
| Gestion Virtual Switches | TERMINÉ | CRUD switches réseau |
| Monitoring VM | TERMINÉ | Heartbeat, Integration Services, PowerShell Direct |
| Support VMware | À FAIRE | Client pyVmomi (futur) |

### Module 2 : Création de VMs
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Création VM basique | TERMINÉ | Nom, génération, emplacement |
| Configuration CPU/RAM | TERMINÉ | Allocation ressources dynamique |
| Création disque VHDX | TERMINÉ | Taille, format dynamique |
| Configuration réseau | TERMINÉ | Virtual Switch, MAC auto |
| Montage ISO | TERMINÉ | Attachement ISO + OEMDRV |

### Module 3 : Installation OS Automatique
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Template Windows unattend | TERMINÉ | Windows Server 2022 |
| Template Linux preseed | TERMINÉ | Debian 12 |
| Template Linux autoinstall | TERMINÉ | Ubuntu 24.04 |
| Template Cloud-init | TERMINÉ | Générique Linux |
| Génération dynamique | TERMINÉ | Jinja2 avec injection paramètres |
| Détection fin install | TERMINÉ | Heartbeat + PowerShell Direct |

### Module 4 : Post-Installation
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Configuration réseau | TERMINÉ | DHCP/statique, DNS, gateway |
| Jointure domaine AD | TERMINÉ | Windows (unattend.xml) |
| Activation services | TERMINÉ | SSH, WinRM, RDP |
| Mises à jour système | EN COURS | apt update dans templates Linux |
| Configuration sécurité | EN COURS | Firewall Windows configuré |

### Module 5 : Installation Logiciels
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Catalogue logiciels | À FAIRE | Base de données apps |
| Installation Windows | À FAIRE | Chocolatey |
| Installation Linux | À FAIRE | apt/yum |
| Profils prédéfinis | À FAIRE | Templates par rôle |

### Module 6 : Interface Web (Frontend React)
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Structure projet | TERMINÉ | Vite + React 19 + TypeScript 5.9 |
| Design system | TERMINÉ | TailwindCSS 4, thème dark |
| Layout application | TERMINÉ | Sidebar, Header, MainLayout |
| Composants UI base | TERMINÉ | StatCard, StatusBadge |
| Service API | TERMINÉ | Axios avec retry backoff |
| Types TypeScript | TERMINÉ | Interfaces complètes |
| Dashboard principal | TERMINÉ | Stats, déploiements récents |
| React Router | TERMINÉ | BrowserRouter + Routes configurées |
| Page Hyperviseurs | À FAIRE | CRUD hyperviseurs |
| Page VMs | À FAIRE | Liste, actions, détails |
| Page Templates | À FAIRE | CRUD templates OS |
| Page Déploiements | À FAIRE | Suivi temps réel |
| Wizard création VM | À FAIRE | Multi-étapes, validation |
| Temps réel (WebSocket) | À FAIRE | Progression live |

### Module 7 : API REST (Backend FastAPI)
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Endpoints VMs | TERMINÉ | CRUD + start/stop/restart |
| Endpoints Templates | TERMINÉ | CRUD templates OS |
| Endpoints Deployments | TERMINÉ | Création, logs, cancel |
| Endpoints Hypervisors | TERMINÉ | CRUD + test connexion |
| Documentation OpenAPI | TERMINÉ | Swagger UI sur /docs |
| Authentification | À FAIRE | JWT/OAuth |
| WebSocket | À FAIRE | Événements temps réel |

---

## Architecture Technique

### Stack Technologique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| Backend API | Python + FastAPI | 3.11+ |
| Frontend | React + TypeScript | 18.x |
| Base de données | PostgreSQL | 15+ |
| Queue de tâches | Celery + Redis | 5.x |
| Hyperviseur Hyper-V | PowerShell Direct / WMI | - |
| Hyperviseur VMware | pyVmomi | (futur) |

### Structure du Projet

```
vm-automation/
├── src/                        # Backend Python
│   ├── api/                    # FastAPI endpoints
│   │   ├── routers/
│   │   │   ├── vms.py          ✅ CRUD + actions VM
│   │   │   ├── templates.py    ✅ CRUD templates OS
│   │   │   ├── deployments.py  ✅ Orchestration déploiements
│   │   │   ├── hypervisors.py  ✅ CRUD hyperviseurs
│   │   │   └── health.py       ✅ Health check
│   │   ├── dependencies.py
│   │   └── main.py             ✅ App FastAPI avec CORS
│   │
│   ├── domain/                 # Logique métier
│   │   ├── models.py           ✅ 7 modèles SQLAlchemy
│   │   ├── vm_service.py       ✅ Service VM complet
│   │   ├── deployment_service.py ✅ Orchestration déploiement
│   │   └── template_engine.py  ✅ Génération Jinja2
│   │
│   ├── integrations/           # Clients externes
│   │   └── hypervisors/
│   │       ├── base.py         ✅ Interface abstraite
│   │       └── hyperv_client.py ✅ Client Hyper-V WinRM
│   │
│   ├── common/                 # Utilitaires
│   │   ├── powershell.py       ✅ Wrapper PowerShell/WinRM
│   │   ├── config.py           ✅ Configuration Pydantic
│   │   ├── database.py         ✅ Session async SQLAlchemy
│   │   ├── logging.py          ✅ Configuration logs
│   │   └── exceptions.py       ✅ Exceptions custom
│   │
│   └── types/                  # Types/interfaces
│       └── schemas.py          ✅ Pydantic schemas
│
├── frontend/                   # React app
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/         ✅ MainLayout, Sidebar, Header
│   │   │   └── ui/             ✅ StatCard, StatusBadge
│   │   ├── pages/              ✅ 7 pages (Dashboard fonctionnel)
│   │   │   ├── Dashboard.tsx   ✅ Stats + déploiements récents
│   │   │   ├── Hypervisors.tsx 🔄 Placeholder
│   │   │   ├── VirtualMachines.tsx 🔄 Placeholder
│   │   │   ├── Templates.tsx   🔄 Placeholder
│   │   │   ├── Deployments.tsx 🔄 Placeholder
│   │   │   ├── Settings.tsx    🔄 Placeholder
│   │   │   └── Help.tsx        🔄 Placeholder
│   │   ├── services/
│   │   │   └── api.ts          ✅ Client Axios complet
│   │   └── types/
│   │       └── index.ts        ✅ Types TypeScript
│   ├── package.json            ✅ Deps React 19, Vite 7
│   ├── tailwind.config.js      ✅ Thème dark custom
│   └── vite.config.ts          ✅ Config Vite
│
├── templates/                  # Templates d'installation
│   ├── unattend/
│   │   └── windows_server_2022.xml ✅
│   ├── preseed/
│   │   └── debian_12.cfg       ✅
│   ├── cloud-init/
│   │   ├── ubuntu_autoinstall.yaml ✅
│   │   └── debian_cloud_init.yaml ✅
│   └── kickstart/              ⬜ À faire
│
├── scripts/                    # Scripts utilitaires
│   ├── check_vm_status.py      ✅ Test monitoring VM
│   ├── test_monitoring.py      ✅ Test heartbeat/health
│   └── test_powershell_direct.py ✅ Test PowerShell Direct
│
├── tests/                      # Tests
│   ├── unit/                   ⬜ À faire
│   ├── integration/            ⬜ À faire
│   └── e2e/                    ⬜ À faire
│
├── docs/                       # Documentation
│   ├── ARCHITECTURE.md
│   ├── GETTING_STARTED.md
│   ├── PREREQUISITES.md
│   ├── TASKS.md                ✅ Suivi détaillé
│   └── UNATTENDED_INSTALL.md   ✅ Guide installation auto
│
├── alembic/                    # Migrations DB
├── config/                     # Configuration
├── requirements.txt
├── docker-compose.yml          ✅ PostgreSQL + Redis
└── README.md
```

**Légende:** ✅ Implémenté | 🔄 En cours | ⬜ À faire

---

## Variables d'Environnement

| Variable | Description | Obligatoire |
|----------|-------------|-------------|
| `DB_HOST` | Hôte PostgreSQL | Oui |
| `DB_PORT` | Port PostgreSQL | Oui (défaut: 5432) |
| `DB_NAME` | Nom de la base | Oui |
| `DB_USER` | Utilisateur DB | Oui |
| `DB_PASSWORD` | Mot de passe DB | Oui |
| `REDIS_URL` | URL Redis | Oui |
| `API_SECRET_KEY` | Clé secrète JWT | Oui |
| `HYPERV_HOST` | Hôte Hyper-V | Oui |
| `HYPERV_USER` | Utilisateur Hyper-V | Oui |
| `HYPERV_PASSWORD` | Mot de passe Hyper-V | Oui |
| `AD_DOMAIN` | Domaine Active Directory | Non |
| `AD_USER` | Utilisateur AD pour jointure | Non |
| `AD_PASSWORD` | Mot de passe AD | Non |
| `ISO_BASE_PATH` | Chemin vers les ISOs | Oui |
| `VHDX_BASE_PATH` | Chemin stockage disques | Oui |

---

## Instructions de Déploiement

### Développement Local

```bash
# 1. Cloner le repository
git clone https://github.com/votre-org/vm-automation.git
cd vm-automation

# 2. Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\Activate   # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos valeurs

# 5. Lancer les services
docker-compose up -d  # PostgreSQL + Redis

# 6. Initialiser la base de données
python -m src.api.main migrate

# 7. Lancer l'API
uvicorn src.api.main:app --reload

# 8. Lancer le worker Celery
celery -A src.workers worker --loglevel=info
```

### Production

```bash
# Via Docker Compose
docker-compose -f docker-compose.prod.yml up -d
```

---

## Changelog

### v0.2.0 (En cours)
- **Phase 1 - Fondations** : 93% complète
- **Frontend Skeleton** : 100% complète
  - Vite 5 + React 19 + TypeScript 5.9
  - TailwindCSS 3 avec thème dark
  - React Router v6
  - Service API Axios + React Query
  - Dashboard avec stats et déploiements récents
  - Composants UI: StatCard, StatusBadge
  - Layout: Sidebar + Header
  - Structure projet complète (26 fichiers Python)
  - Configuration centralisée (Pydantic Settings)
  - Base de données PostgreSQL (SQLAlchemy async)
  - API FastAPI avec CORS, exception handlers
  - 5 routers : health, hypervisors, vms, templates, deployments
  - 7 modèles SQLAlchemy : Hypervisor, VirtualMachine, OSTemplate, Deployment, DeploymentLog, SoftwarePackage, VMSoftware
  - Client Hyper-V complet (PowerShell/WinRM)
  - Wrapper PowerShell avec support mock pour dev

- **Phase 3 - Templates OS & Monitoring** : 81% complète
  - Moteur de templates Jinja2
  - Template Windows Server 2022 (unattend.xml)
  - Template Ubuntu 24.04 (autoinstall)
  - Template Debian 12 (preseed)
  - Template Cloud-init générique
  - Injection dynamique : hostname, réseau, password, locale, timezone
  - **Monitoring VM** : get_vm_health(), get_vm_heartbeat(), get_vm_integration_services()
  - **PowerShell Direct** : execute_in_vm(), wait_for_vm_ready()
  - VM WinSrv2022-Test validée avec installation 100% automatique

### v0.1.0 (2026-01-26)
- Initialisation du projet
- Structure de base
- Documentation initiale

---

## Contacts

- **Équipe** : Infrastructure IT
- **Repository** : https://github.com/votre-org/vm-automation
