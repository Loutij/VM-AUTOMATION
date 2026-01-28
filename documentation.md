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
| Synchronisation VMs | TERMINÉ | sync_all_vms() - Sync bidirectionnelle Hyper-V ↔ DB (état, IP, MAC, switch, VLAN) |
| Détails VM complets | TERMINÉ | get_vm_full_details() - CPU, RAM, disques, réseau, services intégration |
| Support VMware | À FAIRE | Client pyVmomi (futur) |

### Module 2 : Création de VMs
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Création VM basique | TERMINÉ | Nom, génération, emplacement |
| Configuration CPU/RAM | TERMINÉ | Allocation ressources dynamique |
| Création disque VHDX | TERMINÉ | Taille, format dynamique, emplacement personnalisé |
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
| Déploiement DISM | TERMINÉ | deploy_with_dism() - Déploie Windows directement sur VHD (~90s, évite "Press any key") |
| Injection unattend | TERMINÉ | inject_unattend() - Injecte autounattend.xml via VHDX dédié |
| Création ISO custom | TERMINÉ | create_custom_iso() - oscdimg.exe + efisys_noprompt.bin |
| OOBE automatique | TERMINÉ | RunOnce + setup.ps1 configure mot de passe et services au premier boot |

### Module 4 : Post-Installation
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Configuration réseau | TERMINÉ | DHCP/statique, DNS, gateway |
| Jointure domaine AD | TERMINÉ | Windows (unattend.xml) + join_domain() |
| Activation services | TERMINÉ | SSH, WinRM, RDP + configure_service() |
| Windows Update | TERMINÉ | install_windows_updates() via PowerShell Direct |
| Configuration sécurité | TERMINÉ | configure_firewall_rule(), password policies |
| PostInstallService | TERMINÉ | Service complet pour config Windows |
| Configuration Zabbix | TERMINÉ | configure_zabbix_agent() - server, hostname, port |
| Configuration SQL Server | TERMINÉ | configure_sql_server() - mixed mode, TCP/IP |
| Configuration IIS | TERMINÉ | configure_iis() - site, binding, port |
| **Workflow intégré** | **TERMINÉ** | Post-install automatique dans DeploymentService |

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
| Page VMs | TERMINÉ | Liste avec stats, filtres, actions, sync Hyper-V, détails complets, colonne VLAN |
| Page Templates | TERMINÉ | CRUD grille avec filtres OS, duplicate, sélecteur langue |
| Page Déploiements | TERMINÉ | Timeline, logs modal, cancel/retry, indicateur temps réel |
| Page Paramètres | TERMINÉ | Config multi-sections + notifications email |
| Wizard création VM | TERMINÉ | Multi-étapes avec sélecteur espace disque visuel |
| Temps réel (WebSocket) | TERMINÉ | Progression live + indicateur connexion

### Module 7 : API REST (Backend FastAPI)
| Fonctionnalité | Statut | Description |
|----------------|--------|-------------|
| Endpoints VMs | TERMINÉ | CRUD + start/stop/restart + VLAN/switch réseau |
| Endpoints Templates | TERMINÉ | CRUD templates OS + langue d'installation |
| Endpoints Deployments | TERMINÉ | Création, logs, cancel |
| Endpoints Hypervisors | TERMINÉ | CRUD + test connexion + storage-locations |
| Endpoints Settings | TERMINÉ | Configuration SMTP + test email |
| Documentation OpenAPI | TERMINÉ | Swagger UI sur /docs |
| Authentification JWT | TERMINÉ | src/common/auth.py (bcrypt + jose) |
| Migration Alembic | TERMINÉ | 5 migrations (8 tables + install_locale) |
| CI/CD Pipeline | TERMINÉ | GitHub Actions (lint, test, build) |
| Pre-commit hooks | TERMINÉ | Black, isort, ruff, mypy, bandit |
| WebSocket Backend | TERMINÉ | WebSocketManager + rooms + subscriptions |
| SSE Endpoint | TERMINÉ | /api/v1/realtime/sse avec heartbeat |
| Notifications push | TERMINÉ | emit_deployment_event(), emit_vm_event(), emit_notification() |
| Notifications Email | TERMINÉ | Service SMTP pour fin de déploiement |
| Sync auto Hyper-V | TERMINÉ | Tâche Celery toutes les 5 minutes |

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
| `SMTP_HOST` | Serveur SMTP | Non |
| `SMTP_PORT` | Port SMTP (défaut: 465) | Non |
| `SMTP_SSL` | Utiliser SSL (défaut: true) | Non |
| `SMTP_USER` | Utilisateur SMTP | Non |
| `SMTP_PASSWORD` | Mot de passe SMTP | Non |
| `SMTP_FROM` | Adresse d'expédition | Non |
| `SMTP_ENABLED` | Activer les notifications email | Non |

---

## ⚠️ Identifiants par Défaut des VMs

> **IMPORTANT** : Ces identifiants sont utilisés pour se connecter aux VMs Windows déployées.

| Champ | Valeur |
|-------|--------|
| **Utilisateur** | `.\Administrateur` |
| **Mot de passe** | `TempP@ss123!` |

### Notes
- Le préfixe `.\` indique un compte local (pas un compte domaine)
- Sur un Windows en français, le compte s'appelle `Administrateur` (pas `Administrator`)
- Le mot de passe peut être personnalisé lors du déploiement via le champ "Mot de passe admin"
- Pour changer le mot de passe par défaut globalement, modifier la variable `DEFAULT_ADMIN_PASSWORD` dans `.env`

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

### v0.9.0 (2026-01-28) - Améliorations UX et Notifications

#### Nouvelles fonctionnalités

- **Colonne VLAN dans la liste des VMs** :
  - Nouvelle colonne dédiée affichant le VLAN ID configuré
  - Récupération dynamique depuis Hyper-V via `Get-VMNetworkAdapterVlan`
  - Inclus dans le schéma VMResponse backend

- **Sélecteur d'espace disque visuel** :
  - Nouveau composant dans le wizard de déploiement (étape Ressources)
  - Affichage visuel des disques disponibles avec barre de progression
  - Badge "Recommandé" pour le disque avec le plus d'espace libre
  - Badge "Défaut" pour le disque C:
  - Option de chemin personnalisé conservée
  - Sélection automatique du disque par défaut (C:)

- **Synchronisation automatique Hyper-V** :
  - Nouvelle tâche Celery `sync_all_hypervisors()` exécutée toutes les 5 minutes
  - Synchronisation de tous les hyperviseurs actifs
  - Notification WebSocket quand des changements sont détectés
  - Ajout au `beat_schedule` de Celery

- **Choix de la langue d'installation** :
  - Nouveau champ `install_locale` dans les templates OS (défaut: `fr-FR`)
  - Migration Alembic `005_add_template_locale.py`
  - 12 langues disponibles (fr-FR, en-US, en-GB, de-DE, es-ES, etc.)
  - Sélecteur dans le formulaire de création/édition de template
  - Affichage de la langue dans les cartes de templates

- **Notifications Email SMTP** :
  - Service `EmailService` dans `src/common/email.py`
  - Emails HTML riches pour fin de déploiement (succès/échec)
  - Contenu détaillé : IP, credentials, config, lien RDP
  - Configuration via variables d'environnement SMTP_*
  - Nouvel endpoint `POST /settings/smtp/test` pour tester l'envoi
  - Section "Notifications Email" dans la page Paramètres
  - Bouton "Envoyer email de test"

- **Mise à jour temps réel des déploiements** :
  - Intégration du hook `useDeploymentEvents` dans la page Deployments
  - Rafraîchissement instantané via WebSocket
  - Indicateur visuel de connexion (Live/Polling)
  - Nouvelle fonction `emit_notification()` pour notifications génériques

#### Fichiers modifiés

- Backend :
  - `src/api/routers/vms.py` : ajout `network_switch` et `vlan_id` dans VMResponse
  - `src/api/routers/templates.py` : ajout `install_locale` dans les schémas
  - `src/api/routers/settings.py` : nouveau router pour paramètres + test SMTP
  - `src/domain/models.py` : ajout `install_locale` à OSTemplate
  - `src/common/config.py` : ajout paramètres SMTP
  - `src/common/email.py` : nouveau service d'envoi d'emails
  - `src/workers/tasks.py` : tâche `sync_all_hypervisors()`
  - `src/workers/celery_app.py` : ajout au beat_schedule
  - `src/api/websocket.py` : fonction `emit_notification()`
  - `src/api/main.py` : enregistrement router settings

- Frontend :
  - `src/types/index.ts` : ajout `vlan_id`, `network_switch`, `install_locale`, `StorageLocation`
  - `src/services/api.ts` : ajout `getStorageLocations`, màj mappers
  - `src/pages/VirtualMachines.tsx` : nouvelle colonne VLAN
  - `src/pages/NewDeployment.tsx` : sélecteur d'espace disque visuel
  - `src/pages/Templates.tsx` : sélecteur de langue d'installation
  - `src/pages/Settings.tsx` : section notifications email
  - `src/pages/Deployments.tsx` : indicateur temps réel WebSocket

- Configuration :
  - `alembic/versions/005_add_template_locale.py` : migration
  - `config/env.example` : variables SMTP ajoutées

### v0.8.3 (2026-01-28) - Post-Installation Automatique DISM
- **Correction majeure du workflow DISM** :
  - Le mot de passe Administrateur est maintenant configuré automatiquement
  - Utilisation de **RunOnce** dans le registre offline pour exécuter le setup au premier boot
  - Script `C:\VM-Automation\setup.ps1` configure : mot de passe, WinRM, RDP, firewall
  - Fichier flag `C:\VM-Automation\ready.flag` signale la fin du setup
- **Windows FR** :
  - Credentials corrigés : `Administrateur` au lieu de `Administrator`
  - Templates unattend.xml mis à jour pour Windows français
  - Commandes `net user Administrateur` dans tous les scripts
- **Workflow amélioré** :
  - `_wait_for_vm_ready()` vérifie le fichier flag en 3 phases (heartbeat, flag, PowerShell Direct)
  - `_execute_fallback_setup()` : nouveau mécanisme de fallback si RunOnce échoue
  - Retry automatique avec backoff exponentiel
- **Fichiers modifiés** :
  - `src/integrations/hypervisors/hyperv_client.py` : deploy_with_dism() avec RunOnce
  - `src/domain/deployment_service.py` : wait logic améliorée + fallback
  - `templates/unattend/windows_server_*.xml` : Username=Administrateur

### v0.8.2 (2026-01-27) - Catalogue Services d'Entreprise Enrichi
- **Services Active Directory enrichis** :
  - AD DS avec configuration complète (mode forêt/domaine, niveau fonctionnel, DSRM, réplication)
  - DNS Server avec zones, transfert, DNSSEC
  - DHCP Server avec scopes, options, failover
- **Nouveaux services d'entreprise Windows** :
  - AD CS (Certificate Authority) : PKI, hiérarchie CA, modèles certificats
  - AD FS (Federation Services) : SSO, SAML, OAuth/OIDC
  - NPS (Network Policy Server) : RADIUS, 802.1X, VPN auth
  - RRAS (Routing and Remote Access) : VPN IKEv2/SSTP, NAT, routage
  - WDS (Windows Deployment Services) : déploiement PXE
  - Web Application Proxy : reverse proxy avec AD FS
  - Windows Admin Center : console d'admin web
- **SQL Server configurations avancées** :
  - SQL Server Express 2022 avec collation, chemins personnalisés, FILESTREAM
  - SQL Server Standard 2022 avec features, TempDB, compte de service
  - Azure Data Studio pour l'édition moderne
- **SSH enrichi** :
  - Configuration complète : authentification, shell par défaut, forwarding, bannière
  - Scripts post-installation automatiques
- **Services Linux ajoutés** :
  - Samba AD DC : contrôleur de domaine AD compatible
  - FreeIPA Server : gestion d'identité Linux (LDAP, Kerberos, PKI)
  - BIND9 DNS, ISC DHCP Server
  - MariaDB, PostgreSQL avec configuration avancée
  - nginx, Apache avec SSL/TLS
  - Fail2ban, Docker CE, Prometheus, Grafana
- **Nouvelles catégories** :
  - `enterprise_services` : services d'infrastructure d'entreprise
  - `messaging` : messagerie et collaboration
- **Nouveaux profils pré-configurés** :
  - `serveur_web_linux` : Stack LEMP
  - `controleur_domaine_linux` : FreeIPA
  - `base_donnees_linux` : PostgreSQL + MariaDB
  - `monitoring_linux` : Prometheus + Grafana
  - `infrastructure_vpn` : RRAS + NPS + PKI
  - `pki_entreprise` : CA d'entreprise
  - `federation_identite` : AD FS + WAP
  - `deploiement_reseau` : WDS + WSUS
- **Migration Alembic** : ajout catégories `enterprise_services` et `messaging`

### v0.8.1 (2026-01-27) - Correction de Bugs et Cohérence Types
- **Corrections Critiques (Migrations Alembic)** :
  - VMState enum : valeurs minuscules (`running`, `stopped`, `paused`, `saved`, `unknown`)
  - DeploymentStatus enum : valeurs alignées avec modèle Python (`creating_vm`, `installing_os`, `post_install`, `in_progress`)
  - SoftwareCategory enum : `networking` → `network`, toutes les catégories incluses
  - Correction chaîne down_revision dans migrations
  - Uniformisation `hypervisor_vm_id` (remplace `hyperv_id`)
- **Alignement Types Frontend/Backend** :
  - `memory_mb` → `ram_gb` (backend utilise GB)
  - `disk_size_gb` → `disk_gb`
  - `os_version` → `os_type`
  - `template_id` → `os_template_id`
  - `default_cpu/memory/disk` → `min_cpu/ram_gb/disk_gb`
  - `DeploymentLog.status` → `DeploymentLog.level`
- **Corrections Code** :
  - `DeploymentLogEntry.level` : type `Literal["debug", "info", "warning", "error"]`
  - `CATEGORY_INFO` : ajout catégorie `other`
  - `OSTemplateResponse` : `created_at`/`updated_at` en `datetime`
  - Suppression import `Depends` inutilisé dans `vms.py`
  - React useEffect : ajout commentaire eslint-disable pour dépendance intentionnellement exclue
- **Nettoyage Système Hyper-V** :
  - Suppression de 25 dossiers VM orphelins
  - Suppression VM "A" fantôme de la base de données
  - Correction des statuts VM incohérents (creating → running/stopped)
- **Données Initialisées** :
  - Catalogue software seedé : 100 packages disponibles
  - 6 templates OS ajoutés : Windows Server 2019, Windows 10/11, Ubuntu 24.04, Debian 12, Rocky Linux 9
- **Nouveaux Scripts** :
  - `scripts/validate_enums.py` : vérifie la cohérence des enums entre migrations, modèles et frontend
  - `scripts/cleanup_hyperv.py` : nettoyage des ressources Hyper-V orphelines (VHD, dossiers VM)

### v0.8.0 (2026-01-27) - Marketplace Logiciels
- **Catalogue de logiciels complet** :
  - Plus de 100 packages organisés par catégorie
  - 14 catégories : Rôles Windows, Accès distant, Bases de données, Serveurs web, Développement, Runtimes, Monitoring, Sécurité, Utilitaires, Navigateurs, Containers, Transfert fichiers, Réseau, Backup
  - Support des différents gestionnaires : Chocolatey, Windows Feature, Windows Capability
- **Profils pré-configurés** :
  - `minimal` : 7-Zip, Notepad++, Chrome
  - `serveur_web` : IIS, URL Rewrite, PHP, MySQL
  - `controleur_domaine` : AD DS, DNS, DHCP, Windows Backup
  - `developpement` : Git, VS Code, Node.js, Python, Docker
  - `base_donnees` : SQL Server Express, SSMS
  - `monitoring` : Zabbix Agent, Prometheus Exporter, Sysinternals
  - `securite` : Sysinternals, Nmap, Wireshark, Malwarebytes
  - `complet` : Combinaison des outils essentiels
- **API Marketplace** :
  - `GET /software-catalog` : liste paginée avec filtres (catégorie, recherche, featured)
  - `GET /software-catalog/categories` : catégories avec compteurs
  - `GET /software-catalog/profiles` : profils pré-configurés
  - `POST /software-catalog/seed` : initialisation du catalogue par défaut
- **Frontend Marketplace** :
  - Page dédiée avec vue grille/liste
  - Recherche et filtres par catégorie
  - Sélection de profils pré-configurés
  - Sélection "à la carte" intégrée au wizard de déploiement

### v0.7.0 (2026-01-27) - Intégration Post-Install Complète
- **Workflow de déploiement complet** :
  - Nouvelles étapes : `WAITING_VM_READY` → `POST_CONFIGURATION` → `INSTALLING_SOFTWARE` → `FINALIZING`
  - Attente automatique que la VM soit prête (heartbeat + PowerShell Direct accessible)
  - Installation automatique des logiciels selon le profil choisi
  - Configuration automatique des services (RDP, WinRM, SSH)
- **Endpoint post-install manuel** :
  - `POST /vms/{id}/post-install` : exécute les configurations sur une VM existante
  - Permet d'ajouter des logiciels ou configurer des services après le déploiement initial
- **Configuration logiciels spécifiques** :
  - `configure_zabbix_agent()` : configurer server, hostname, port, remote commands
  - `configure_sql_server()` : mode mixte, TCP/IP, port, firewall
  - `configure_iis()` : création site, binding, port
  - `join_domain()` : joindre un domaine AD via PowerShell Direct
- **Frontend amélioré** :
  - Transmission complète des options (services, software_profile, packages) au backend
  - Types TypeScript pour services et sécurité
- **API étendue** :
  - Nouveaux paramètres `services`, `security`, `software_profile`, `packages` dans DeploymentCreate
  - Configuration par défaut des services (RDP + WinRM activés)

### v0.6.0 (2026-01-27)
- **Synchronisation VMs Hyper-V ↔ DB** :
  - Nouvel endpoint `POST /hypervisors/{id}/sync`
  - Méthode `sync_all_vms()` : importe les VMs manquantes, met à jour l'état, marque les VMs supprimées
  - Synchronisation IP, MAC, switch réseau, VLAN
  - Bouton "Synchroniser avec Hyper-V" dans l'interface web
- **Détails VM améliorés** :
  - Fix script PowerShell trop long pour WinRM
  - Panel détails complet : CPU, RAM, disques (taille/utilisé), réseau (IP/MAC/switch), services intégration
- **Déploiement Windows** :
  - Amélioration DISM avec bypass OOBE
  - Configuration réseau automatique (Network Discovery, File Sharing)
- **Fix transmission paramètres frontend → backend** :
  - Correction `api.ts` : le payload envoyait uniquement les champs de base, omettant `vhdx_path`, `ip_config`, `domain_join`, `post_install_commands`
  - Ajout types TypeScript pour `ip_config` et `post_install_commands` dans `DeploymentConfig`
  - L'emplacement VHDX personnalisé fonctionne maintenant (permet de créer les VMs sur D:, G:, etc.)
- **Endpoint stockage disponible** :
  - `GET /hypervisors/{id}/storage-locations` : liste les disques disponibles avec espace libre
  - Permet à l'utilisateur de choisir un disque alternatif quand C: est plein
- **Fix double déploiement** :
  - Statut `IN_PROGRESS` défini immédiatement dans l'API (avant commit DB)
  - Évite que Celery Beat relance un déploiement déjà en cours
- **Robustesse parsing JSON PowerShell** :
  - `_parse_json_output()` utilise regex pour extraire le JSON même avec messages parasites
  - Ajout `$ProgressPreference = 'SilentlyContinue'` dans les scripts DISM

### v0.5.0 (2026-01-26)
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
