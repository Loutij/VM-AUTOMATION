# VM Automation - Architecture Technique

## 1. Vue d'ensemble

```
Utilisateurs (Equipe IT)
        |
        v
+------------------+       REST/WS        +------------------+
|  Frontend React  | <------------------> |  Backend FastAPI  |
|  (Vite + TS)     |                      |  Port 8000       |
|  Port 5173 (dev) |                      +--------+---------+
+------------------+                               |
                                          +--------+---------+
                                          |                  |
                                   +------+------+    +------+------+
                                   | PostgreSQL  |    |    Redis    |
                                   | Port 5432   |    |  Port 6379  |
                                   +-------------+    +------+------+
                                                             |
                                                      +------+------+
                                                      |   Celery    |
                                                      |   Workers   |
                                                      +------+------+
                                                             |
                                                      +------+------+
                                                      |  Hyper-V    |
                                                      | WinRM:5986  |
                                                      +-------------+
```

## 2. Structure du Code

### 2.1 Backend (Python)

```
src/
├── api/
│   ├── main.py                    # Point d'entree FastAPI, CORS, montage routers
│   ├── websocket.py               # Gestionnaire WebSocket (connexions, broadcast)
│   └── routers/
│       ├── __init__.py            # Enregistrement des routers
│       ├── auth.py                # POST /auth/login, /auth/register
│       ├── vms.py                 # CRUD VMs, actions (start/stop/restart), post-install, RDP
│       ├── deployments.py         # CRUD deploiements, logs, progression WebSocket
│       ├── templates.py           # CRUD templates OS, validation Jinja2
│       ├── hypervisors.py         # CRUD hyperviseurs, test connexion, sync VMs
│       ├── health.py              # GET /health, /health/detailed
│       ├── realtime.py            # WebSocket /ws/realtime (events temps reel)
│       ├── callbacks.py           # POST /callbacks (callbacks VM post-install)
│       ├── console.py             # WebSocket /console/ws/{vm_id} (console graphique VM)
│       ├── terminal.py            # WebSocket /terminal/ws/{vm_id} (terminal PowerShell)
│       ├── settings.py            # GET/PUT /settings (configuration app)
│       └── software_catalog.py    # GET /software-catalog (catalogue logiciels)
│
├── domain/
│   ├── models.py                  # Modeles SQLAlchemy (Hypervisor, VM, Deployment, etc.)
│   ├── vm_service.py              # Service VMs (CRUD, actions, sync)
│   ├── deployment_service.py      # Service deploiement (workflow complet, DISM, post-config)
│   ├── template_engine.py         # Moteur Jinja2 (unattend, preseed, cloud-init, kickstart)
│   ├── post_install_service.py    # Services post-install (SSH, WinRM, firewall, updates)
│   ├── software_install_service.py # Installation logiciels (Chocolatey, profils)
│   ├── software_catalog.py        # Catalogue logiciels (150+ packages Windows)
│   └── user_model.py              # Modele utilisateur (auth)
│
├── integrations/
│   └── hypervisors/
│       ├── base.py                # Interface abstraite BaseHypervisor
│       └── hyperv_client.py       # Client Hyper-V (PowerShell/WinRM, DISM, PowerShell Direct)
│
├── workers/
│   ├── celery_app.py              # Configuration Celery (broker Redis)
│   └── tasks.py                   # Taches async (process_deployment, monitor, etc.)
│
└── common/
    ├── config.py                  # Settings Pydantic (env vars)
    ├── database.py                # Session SQLAlchemy async (PostgreSQL)
    ├── auth.py                    # JWT + bcrypt
    ├── crypto.py                  # Chiffrement Fernet (credentials hyperviseurs)
    ├── constants.py               # Constantes (etapes deploiement, progression)
    ├── email.py                   # Notifications email (deploiement termine)
    ├── exceptions.py              # Exceptions metier
    ├── logging.py                 # Logging structure (structlog)
    ├── powershell.py              # Wrapper PowerShell/WinRM
    └── timeout.py                 # Gestion timeouts async
```

### 2.2 Frontend (React + TypeScript)

```
frontend/src/
├── App.tsx                        # Routes principales
├── pages/
│   ├── Dashboard.tsx              # Tableau de bord (stats, VMs recentes, activite)
│   ├── VirtualMachines.tsx        # Liste VMs, actions, details, filtres
│   ├── NewDeployment.tsx          # Formulaire deploiement (wizard multi-etapes)
│   ├── Deployments.tsx            # Liste deploiements, progression temps reel
│   ├── Templates.tsx              # Gestion templates OS
│   ├── Hypervisors.tsx            # Gestion hyperviseurs, test connexion
│   ├── Marketplace.tsx            # Catalogue logiciels (150+ packages)
│   ├── Settings.tsx               # Configuration application
│   ├── Help.tsx                   # Aide et documentation integree
│   ├── Login.tsx                  # Page de connexion
│   └── VMConsole.tsx              # Console graphique VM (screenshots WMI)
│
├── components/
│   ├── auth/
│   │   └── ProtectedRoute.tsx     # Route protegee (JWT)
│   ├── layout/
│   │   ├── MainLayout.tsx         # Layout principal (sidebar + header + content)
│   │   ├── Sidebar.tsx            # Barre laterale navigation
│   │   └── Header.tsx             # En-tete (user, theme, notifications)
│   ├── ui/                        # Composants UI reutilisables
│   │   ├── Button.tsx, Input.tsx, Select.tsx, Switch.tsx
│   │   ├── Modal.tsx, Toast.tsx, Tooltip.tsx, Dropdown.tsx
│   │   ├── DataTable.tsx          # Tableau de donnees avec tri/pagination
│   │   ├── StatCard.tsx           # Carte statistique
│   │   ├── StatusBadge.tsx        # Badge statut (couleur selon etat)
│   │   ├── Progress.tsx           # Barre de progression
│   │   ├── Skeleton.tsx           # Placeholder chargement
│   │   ├── EmptyState.tsx         # Etat vide
│   │   ├── CommandPalette.tsx     # Palette commandes (Ctrl+K)
│   │   ├── CopyButton.tsx        # Bouton copier dans le presse-papier
│   │   └── ThemeToggle.tsx        # Bascule dark/light mode
│   └── vm/
│       ├── VMConsole.tsx          # Composant console graphique
│       └── VMTerminal.tsx         # Composant terminal PowerShell
│
├── hooks/
│   ├── useWebSocket.ts            # Hook WebSocket (connexion, reconnexion, events)
│   ├── useKeyboardShortcuts.ts    # Raccourcis clavier globaux
│   ├── useVMConsole.ts            # Hook console VM (screenshots, clavier)
│   └── useVMTerminal.ts           # Hook terminal VM (PowerShell Direct)
│
├── contexts/
│   ├── AuthContext.tsx             # Contexte authentification (JWT, user)
│   └── ThemeContext.tsx            # Contexte theme (dark/light)
│
├── services/
│   └── api.ts                     # Client API (axios, intercepteurs JWT)
│
├── types/
│   └── index.ts                   # Types TypeScript (VM, Deployment, Template, etc.)
│
└── utils/
    └── (utilitaires divers)
```

## 3. Modele de Donnees

### Tables principales

```
HYPERVISOR                      OS_TEMPLATE
+------------------+            +------------------+
| id (UUID, PK)    |            | id (UUID, PK)    |
| name             |            | name             |
| type (hyperv)    |            | os_family        |
| host             |            | os_type          |
| port (5986)      |            | architecture     |
| use_ssl          |            | iso_path         |
| username (crypt) |            | unattend_template|
| password (crypt) |            | min_cpu/ram/disk |
| is_active        |            | install_locale   |
| max_vms          |            | is_active        |
+--------+---------+            +--------+---------+
         |                               |
         | 1:N                           | 1:N
         v                               v
VIRTUAL_MACHINE                 DEPLOYMENT
+------------------+            +------------------+
| id (UUID, PK)    |            | id (UUID, PK)    |
| hypervisor_id FK |            | vm_name          |
| os_template_id FK|            | hypervisor_id FK |
| name             |            | os_template_id FK|
| hypervisor_vm_id |            | vm_id FK (after) |
| generation (1/2) |            | status (enum)    |
| cpu_count        |            | current_step     |
| ram_gb           |            | progress (0-100) |
| disk_gb          |            | config (JSONB)   |
| disk_path        |            | error_message    |
| network_switch   |            | started_at       |
| vlan_id          |            | completed_at     |
| mac_address      |            +--------+---------+
| ip_address       |                     |
| ip_config (JSONB)|                     | 1:N
| domain_config    |                     v
| status (enum)    |            DEPLOYMENT_LOG
| state (enum)     |            +------------------+
+------------------+            | id (UUID, PK)    |
                                | deployment_id FK |
                                | level            |
                                | step             |
                                | message          |
                                | details (JSONB)  |
                                +------------------+
```

### Enums

- **VMStatus** : `creating`, `created`, `running`, `stopped`, `error`, `deleted`
- **VMState** : `running`, `stopped`, `paused`, `saved`, `off`, `unknown`
- **DeploymentStatus** : `pending`, `in_progress`, `completed`, `failed`, `cancelled`
- **DeploymentStep** : `validating`, `creating_vm`, `mounting_iso`, `generating_unattend`, `configuring_network`, `starting_installation`, `waiting_vm_ready`, `post_configuration`, `installing_software`, `finalizing`, `linux_post_install`

## 4. Communication avec Hyper-V

```
Python (hyperv_client.py)
    |
    | Construit script PowerShell
    v
PowerShell Wrapper (common/powershell.py)
    |
    | Execute via pywinrm
    v
WinRM (HTTPS:5986)  -->  Hyper-V Host  -->  PowerShell  -->  Hyper-V WMI/cmdlets
```

### Methodes principales du HyperVClient

| Methode | Description |
|---------|-------------|
| `create_vm()` | Cree une VM (Gen1/Gen2, CPU, RAM, VHDX, switch) |
| `deploy_with_dism()` | Deploiement DISM (monte ISO, applique image, injecte unattend) |
| `start_vm()` / `stop_vm()` | Demarrer/arreter une VM |
| `execute_in_vm()` | Execute un script via PowerShell Direct |
| `execute_via_winrm_direct()` | Execute via WinRM direct (plus rapide) |
| `wait_for_vm_ready()` | Attend que la VM soit accessible |
| `inject_unattend()` | Injecte un unattend.xml via ISO OEMDRV |
| `get_vm_info()` | Recupere les infos detaillees d'une VM |
| `get_all_vms()` | Liste toutes les VMs de l'hyperviseur |
| `get_vm_screenshot()` | Capture d'ecran WMI (pour console) |
| `send_key_to_vm()` | Envoie des touches clavier (Msvm_Keyboard) |

## 5. Securite

### Authentification
- JWT (JSON Web Tokens) via `python-jose`
- Mots de passe hashes avec `bcrypt`
- Tokens d'acces + refresh tokens

### Chiffrement
- Credentials hyperviseurs chiffres en DB avec Fernet (`src/common/crypto.py`)
- Variables sensibles dans `.env` (jamais committees)
- Mots de passe admin VM dans config JSONB (non chiffres en DB actuellement)

### Reseau
- CORS configure pour le frontend
- WinRM en HTTPS (port 5986) recommande
- API accessible sur port 8000

## 6. Infrastructure Docker

```yaml
# docker-compose.yml
services:
  postgres:   # PostgreSQL 16, port 5432
  redis:      # Redis 7, port 6379
  flower:     # Monitoring Celery, port 5555
```

L'API backend et les workers Celery tournent en natif (pas containerises) pour avoir acces au reseau WinRM.
