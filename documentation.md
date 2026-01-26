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
| Infos réseau complètes | TERMINÉ | get_vm_network_info(), get_vm_network_summary() |
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
| Activation services | TERMINÉ | SSH, WinRM, RDP + configure_service() |
| Windows Update | TERMINÉ | install_windows_updates() via PowerShell Direct |
| Configuration sécurité | TERMINÉ | configure_firewall_rule(), password policies |
| PostInstallService | TERMINÉ | Service complet pour config Windows |

### Module 5 : Installation Logiciels
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Chocolatey | TERMINÉ | ensure_chocolatey_installed() |
| Installation Windows | TERMINÉ | install_package_chocolatey(), install_packages() |
| Désinstallation | TERMINÉ | uninstall_package() |
| Mise à jour | TERMINÉ | upgrade_all_packages() |
| Liste packages | TERMINÉ | list_installed_packages() |
| Profil minimal | TERMINÉ | 7zip, notepadplusplus |
| Profil tools | TERMINÉ | + sysinternals |
| Profil development | TERMINÉ | git, vscode, nodejs, python |
| Profil webserver | TERMINÉ | iis-webserver, urlrewrite |
| Profil monitoring | TERMINÉ | zabbix-agent |
| Profil database | TERMINÉ | sql-server-express, ssms |
| Installation Linux apt | À FAIRE | Debian/Ubuntu |
| Installation Linux yum | À FAIRE | RHEL/Rocky |

### Module 6 : Interface Web (Frontend React)
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Structure projet | TERMINÉ | Vite + React 19 + TypeScript 5.9 |
| Design system | TERMINÉ | TailwindCSS 4, thème dark |
| Layout application | TERMINÉ | Sidebar, Header, MainLayout |
| Composants UI avancés | TERMINÉ | Button, Modal, Toast, DataTable, Input, Select, EmptyState |
| Service API | TERMINÉ | Axios avec retry backoff |
| Types TypeScript | TERMINÉ | Interfaces complètes |
| React Router | TERMINÉ | 7 routes configurées dans App.tsx |
| Dashboard principal | TERMINÉ | Stats, déploiements récents |
| Page Hyperviseurs | TERMINÉ | CRUD complet + test connexion |
| Page VMs | TERMINÉ | Liste avec stats, filtres, actions (start/stop/restart/delete) |
| Page Templates | TERMINÉ | CRUD grille avec filtres OS, duplicate |
| Page Déploiements | TERMINÉ | Timeline, logs modal, cancel/retry, auto-refresh |
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
| Authentification JWT | TERMINÉ | src/common/auth.py (bcrypt + jose) |
| Migration Alembic | TERMINÉ | 001_initial_schema.py (8 tables) |
| CI/CD Pipeline | TERMINÉ | GitHub Actions (lint, test, build) |
| Pre-commit hooks | TERMINÉ | Black, isort, ruff, mypy, bandit |
| WebSocket Backend | TERMINÉ | WebSocketManager + rooms + subscriptions |
| SSE Endpoint | TERMINÉ | /api/v1/realtime/sse avec heartbeat |
| Notifications push | TERMINÉ | emit_deployment_event(), emit_vm_event() |

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
│   │   │   ├── Hypervisors.tsx ✅ CRUD + test connexion
│   │   │   ├── VirtualMachines.tsx ✅ Liste, filtres, actions
│   │   │   ├── Templates.tsx   ✅ CRUD, grille, filtres
│   │   │   ├── Deployments.tsx ✅ Timeline, logs, actions
│   │   │   ├── Settings.tsx    ✅ Config complète multi-sections
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

### v0.5.0 (2026-01-26) - En cours
- **Avancement global** : ~70% (132/189 tâches)
- **Récupération infos réseau complètes** :
  - get_vm_network_info() - IP, MAC, gateway, DNS, hostname
  - get_vm_network_summary() - résumé simplifié
  - execute_in_vm() avec encodage Base64 pour scripts longs

### v0.4.0 (2026-01-26)
- **Phase 7 - Interface Web** : 53% complète
  - Dashboard avec stats temps réel
  - Page Hyperviseurs CRUD complète + test connexion
  - Page VMs avec actions (start/stop/restart/delete)
  - Page Templates avec grille, filtres OS, duplication
  - Page Déploiements avec timeline, logs, cancel/retry
  - 10+ composants UI réutilisables

- **Phase 5 - Installation Logiciels** : 65% complète
  - Chocolatey intégré (ensure, install, uninstall, upgrade)
  - 6 profils logiciels Windows (minimal, tools, dev, web, monitoring, db)
  - SoftwareInstallService complet

- **Phase 6 - Orchestration** : 75% complète
  - WebSocket Server avec rooms et subscriptions
  - SSE endpoint avec heartbeat
  - Notifications push temps réel

### v0.3.0 (2026-01-26)
- **Phase 1 - Fondations** : 100% complète
- **Phase 2 - Création VMs** : 71% complète
- **Phase 3 - Installation OS** : 85% complète
- **Phase 4 - Post-Installation** : 87% complète

### v0.1.0 (2026-01-26)
- Initialisation du projet
- Structure de base
- Documentation initiale

---

## Roadmap Frontend

### Terminé ✅
| Tâche | Description | Statut |
|-------|-------------|--------|
| React Router | 8 routes configurées | ✅ |
| Page Dashboard | Stats, déploiements récents | ✅ |
| Page Hyperviseurs | CRUD complet + test connexion | ✅ |
| Page VMs | Liste, filtres, actions | ✅ |
| Page Templates | CRUD, grille, filtres, duplicate | ✅ |
| Page Déploiements | Timeline, logs, cancel/retry | ✅ |
| Wizard Création VM | 5 étapes avec validation | ✅ |
| Page Paramètres | Config multi-sections complète | ✅ |
| Page Aide | FAQ, raccourcis, dépannage, guide | ✅ |
| DataTable | Tri, search, pagination, actions | ✅ |
| Modal/Dialog | Modal + ConfirmModal | ✅ |
| Toast | ToastProvider + useToast | ✅ |
| Form components | Input, Textarea, Select, Switch | ✅ |
| Progress components | ProgressBar, ProgressTimeline, ProgressCircle | ✅ |
| Skeleton loaders | Skeleton, SkeletonCard, SkeletonTable, SkeletonStats | ✅ |
| Hook useWebSocket | Connexion persistante avec reconnexion | ✅ |
| Hook useDeploymentEvents | Suivi progression temps réel | ✅ |
| Hook useVMEvents | État VM temps réel | ✅ |
| Hook useNotifications | Notifications temps réel | ✅ |
| Keyboard shortcuts | Ctrl+K, Ctrl+N, ?, Esc | ✅ |

### À faire ⬜
| Tâche | Description | Priorité |
|-------|-------------|----------|
| Logs streaming | Console déploiement live | Moyenne |
| Dark/Light toggle | Préférence utilisateur | Basse |
| Tests Frontend | Vitest + Testing Library | Basse |

---

## Contacts

- **Équipe** : Infrastructure IT
- **Repository** : https://github.com/votre-org/vm-automation
- **ClickUp** : Tâche VM-AUTOMATION (869bxaf8k)
