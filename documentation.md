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
| Création VM basique | À FAIRE | Nom, génération, emplacement |
| Configuration CPU/RAM | À FAIRE | Allocation ressources |
| Création disque VHDX | À FAIRE | Taille, format, emplacement |
| Configuration réseau | À FAIRE | Switch, VLAN, MAC |
| Montage ISO | À FAIRE | Attachement ISO automatique |

### Module 3 : Installation OS Automatique
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Template Windows unattend | À FAIRE | Win10, Win11, Server |
| Template Linux preseed | À FAIRE | Ubuntu, Debian |
| Template Linux kickstart | À FAIRE | RHEL, CentOS |
| Génération dynamique | À FAIRE | Injection paramètres |
| Injection drivers | À FAIRE | Hyper-V Integration Services |
| Détection fin install | À FAIRE | Monitoring état VM |

### Module 4 : Post-Installationsetting
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Configuration réseau | À FAIRE | DHCP/statique, DNS |
| Jointure domaine AD | À FAIRE | Windows et Linux |
| Activation services | À FAIRE | SSH, WinRM |
| Mises à jour système | À FAIRE | Windows Update, apt/yum |
| Configuration sécurité | À FAIRE | Firewall, comptes |

### Module 5 : Installation Logiciels
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Catalogue logiciels | À FAIRE | Base de données apps |
| Installation Windows | À FAIRE | Chocolatey |
| Installation Linux | À FAIRE | apt/yum |
| Profils prédéfinis | À FAIRE | Templates par rôle |

### Module 6 : Interface Web
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Dashboard principal | À FAIRE | Vue d'ensemble |
| Formulaire création VM | À FAIRE | Wizard multi-étapes |
| Monitoring déploiements | À FAIRE | Progression temps réel |
| Gestion templates | À FAIRE | CRUD templates |
| Historique/Logs | À FAIRE | Audit trail |

### Module 7 : API REST
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Endpoints VMs | À FAIRE | CRUD machines virtuelles |
| Endpoints Templates | À FAIRE | Gestion templates |
| Endpoints Deployments | À FAIRE | Orchestration |
| Authentification | À FAIRE | JWT/OAuth |
| Documentation OpenAPI | À FAIRE | Swagger UI |

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
├── src/
│   ├── api/                    # FastAPI endpoints
│   │   ├── routers/
│   │   │   ├── vms.py
│   │   │   ├── templates.py
│   │   │   ├── deployments.py
│   │   │   └── hypervisors.py
│   │   ├── dependencies.py
│   │   └── main.py
│   │
│   ├── domain/                 # Logique métier
│   │   ├── vm/
│   │   ├── deployment/
│   │   ├── provisioning/
│   │   └── configuration/
│   │
│   ├── integrations/           # Clients externes
│   │   ├── hypervisors/
│   │   │   ├── base.py
│   │   │   ├── hyperv_client.py
│   │   │   └── vmware_client.py
│   │   ├── active_directory/
│   │   └── dns/
│   │
│   ├── workers/                # Tâches Celery
│   │   ├── vm_creation.py
│   │   ├── os_installation.py
│   │   ├── post_install.py
│   │   └── software_install.py
│   │
│   ├── common/                 # Utilitaires
│   │   ├── powershell.py
│   │   ├── logging.py
│   │   └── exceptions.py
│   │
│   └── types/                  # Types/interfaces
│       ├── vm.py
│       ├── deployment.py
│       └── config.py
│
├── frontend/                   # React app
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── types/
│   ├── package.json
│   └── tsconfig.json
│
├── templates/                  # Templates d'installation
│   ├── unattend/
│   │   ├── win10.xml
│   │   ├── win11.xml
│   │   └── winserver.xml
│   ├── preseed/
│   ├── kickstart/
│   └── cloud-init/
│
├── scripts/                    # Scripts utilitaires
│   ├── powershell/
│   └── ansible/
│
├── config/                     # Configuration
│   └── settings.py
│
├── tests/                      # Tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/                       # Documentation
│
├── requirements.txt
├── docker-compose.yml
└── README.md
```

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
- **Phase 1 - Fondations** : 73% complète
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
