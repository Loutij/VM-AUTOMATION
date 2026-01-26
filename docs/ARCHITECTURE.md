# VM Automation - Architecture Technique

## 1. Vue d'Ensemble

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              UTILISATEURS                                    │
│                         (Équipe IT / Infra)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INTERFACE WEB (React)                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │Dashboard │ │ Création │ │Templates │ │  Logs    │ │ Settings │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ REST API / WebSocket
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          API BACKEND (FastAPI)                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         API Gateway                                   │   │
│  │  • Authentication (JWT)  • Rate Limiting  • Request Validation       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │    VMs     │ │  Templates │ │Deployments │ │Hypervisors │               │
│  │   Router   │ │   Router   │ │   Router   │ │   Router   │               │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘               │
│                                    │                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      DOMAIN LAYER                                     │   │
│  │  • VM Management  • Deployment Workflow  • Configuration Logic       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │                    │                         │
          │                    │                         │
          ▼                    ▼                         ▼
┌─────────────────┐  ┌─────────────────┐     ┌─────────────────────────────┐
│   PostgreSQL    │  │     Redis       │     │      CELERY WORKERS         │
│   (Database)    │  │  (Cache/Queue)  │     │                             │
│                 │  │                 │     │  ┌─────────────────────┐    │
│ • VMs           │  │ • Sessions      │     │  │   VM Creation       │    │
│ • Templates     │  │ • Task Queue    │     │  │   Worker            │    │
│ • Deployments   │  │ • Real-time     │     │  └─────────────────────┘    │
│ • Logs          │  │                 │     │  ┌─────────────────────┐    │
│ • Users         │  │                 │     │  │   OS Install        │    │
└─────────────────┘  └─────────────────┘     │  │   Worker            │    │
                                             │  └─────────────────────┘    │
                                             │  ┌─────────────────────┐    │
                                             │  │   Post-Install      │    │
                                             │  │   Worker            │    │
                                             │  └─────────────────────┘    │
                                             │  ┌─────────────────────┐    │
                                             │  │   Software Install  │    │
                                             │  │   Worker            │    │
                                             │  └─────────────────────┘    │
                                             └─────────────────────────────┘
                                                          │
                                                          │
                    ┌─────────────────────────────────────┴─────────────────┐
                    │                                                       │
                    ▼                                                       ▼
        ┌───────────────────────┐                           ┌───────────────────────┐
        │   HYPER-V HOST        │                           │   VMWARE vCENTER      │
        │   (PowerShell/WMI)    │                           │   (pyVmomi) [FUTUR]   │
        │                       │                           │                       │
        │  ┌─────────────────┐  │                           │  ┌─────────────────┐  │
        │  │ Virtual Switch  │  │                           │  │   vSwitch       │  │
        │  └─────────────────┘  │                           │  └─────────────────┘  │
        │  ┌─────────────────┐  │                           │  ┌─────────────────┐  │
        │  │    VM 1         │  │                           │  │    VM 1         │  │
        │  │    VM 2         │  │                           │  │    VM 2         │  │
        │  │    VM n         │  │                           │  │    VM n         │  │
        │  └─────────────────┘  │                           │  └─────────────────┘  │
        │  ┌─────────────────┐  │                           │  ┌─────────────────┐  │
        │  │   Storage       │  │                           │  │   Datastore     │  │
        │  │   (VHDX/ISO)    │  │                           │  │   (VMDK/ISO)    │  │
        │  └─────────────────┘  │                           │  └─────────────────┘  │
        └───────────────────────┘                           └───────────────────────┘
```

---

## 2. Composants Détaillés

### 2.1 Frontend (React + TypeScript)

```
frontend/
├── src/
│   ├── components/           # Composants réutilisables
│   │   ├── common/          # Buttons, Inputs, Modals
│   │   ├── layout/          # Header, Sidebar, Footer
│   │   ├── vm/              # Composants VM
│   │   └── deployment/      # Composants déploiement
│   │
│   ├── pages/               # Pages principales
│   │   ├── Dashboard.tsx
│   │   ├── VMs/
│   │   │   ├── List.tsx
│   │   │   ├── Create.tsx
│   │   │   └── Details.tsx
│   │   ├── Deployments/
│   │   ├── Templates/
│   │   └── Settings/
│   │
│   ├── services/            # Appels API
│   │   ├── api.ts           # Client Axios configuré
│   │   ├── vms.ts
│   │   ├── deployments.ts
│   │   └── templates.ts
│   │
│   ├── stores/              # State management (Zustand)
│   │   ├── authStore.ts
│   │   ├── vmStore.ts
│   │   └── deploymentStore.ts
│   │
│   ├── hooks/               # Custom hooks
│   │   ├── useWebSocket.ts
│   │   └── useDeployment.ts
│   │
│   └── types/               # Types TypeScript
│       ├── vm.ts
│       ├── deployment.ts
│       └── api.ts
```

### 2.2 Backend (FastAPI)

```
src/
├── api/
│   ├── main.py              # Point d'entrée FastAPI
│   ├── dependencies.py      # Dépendances injectables
│   ├── middleware/
│   │   ├── auth.py
│   │   ├── logging.py
│   │   └── cors.py
│   └── routers/
│       ├── vms.py           # /api/v1/vms
│       ├── deployments.py   # /api/v1/deployments
│       ├── templates.py     # /api/v1/templates
│       ├── hypervisors.py   # /api/v1/hypervisors
│       └── auth.py          # /api/v1/auth
│
├── domain/
│   ├── vm/
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── schemas.py       # Pydantic schemas
│   │   ├── service.py       # Business logic
│   │   └── repository.py    # Data access
│   │
│   ├── deployment/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── workflow.py      # State machine
│   │   └── steps/
│   │       ├── create_vm.py
│   │       ├── install_os.py
│   │       ├── configure.py
│   │       └── install_software.py
│   │
│   └── provisioning/
│       ├── unattend.py      # Windows unattend generator
│       ├── preseed.py       # Debian/Ubuntu preseed
│       └── kickstart.py     # RHEL/CentOS kickstart
│
├── integrations/
│   ├── hypervisors/
│   │   ├── base.py          # Abstract interface
│   │   ├── hyperv_client.py
│   │   └── vmware_client.py
│   │
│   ├── active_directory/
│   │   └── ad_client.py
│   │
│   └── dns/
│       └── dns_client.py
│
├── workers/
│   ├── celery_app.py        # Configuration Celery
│   ├── tasks/
│   │   ├── vm_creation.py
│   │   ├── os_installation.py
│   │   ├── post_install.py
│   │   └── software_install.py
│   └── callbacks.py         # Callbacks de tâches
│
└── common/
    ├── config.py            # Settings Pydantic
    ├── database.py          # Session SQLAlchemy
    ├── logging.py           # Configuration logging
    ├── exceptions.py        # Exceptions custom
    └── powershell.py        # Wrapper PowerShell
```

---

## 3. Flux de Données

### 3.1 Création d'une VM

```
┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐
│  User   │─────▶│ Frontend│─────▶│   API   │─────▶│ Celery  │─────▶│ Hyper-V │
│         │      │         │      │         │      │ Worker  │      │         │
└─────────┘      └─────────┘      └─────────┘      └─────────┘      └─────────┘
     │                │                │                │                │
     │   1. Remplit   │                │                │                │
     │   formulaire   │                │                │                │
     │ ──────────────▶│                │                │                │
     │                │   2. POST      │                │                │
     │                │   /deployments │                │                │
     │                │ ──────────────▶│                │                │
     │                │                │   3. Enqueue   │                │
     │                │                │   task         │                │
     │                │                │ ──────────────▶│                │
     │                │                │                │   4. Create    │
     │                │                │                │   VM via PS    │
     │                │                │                │ ──────────────▶│
     │                │                │                │                │
     │                │   5. WebSocket │                │                │
     │                │◀──────────────────────────────────────────────────
     │   6. Progress  │                │                │                │
     │◀───────────────│                │                │                │
```

### 3.2 Workflow de Déploiement Complet

```
                    ┌─────────────────────────────────────────────┐
                    │            DEPLOYMENT WORKFLOW               │
                    │                (State Machine)               │
                    └─────────────────────────────────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────────┐
                    │              PENDING                         │
                    │         (Déploiement créé)                  │
                    └─────────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  STEP 1: VM_CREATING                                                          │
│  ├── Créer VM (nom, génération)                                              │
│  ├── Configurer CPU/RAM                                                       │
│  ├── Créer disque VHDX                                                        │
│  ├── Configurer réseau                                                        │
│  └── Monter ISO                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  STEP 2: OS_INSTALLING                                                        │
│  ├── Générer fichier unattend/preseed                                        │
│  ├── Injecter dans ISO ou floppy virtuel                                     │
│  ├── Démarrer VM                                                              │
│  ├── Attendre fin installation (heartbeat/polling)                           │
│  └── Timeout: 60 minutes                                                      │
└───────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  STEP 3: POST_CONFIGURING                                                     │
│  ├── Configurer réseau définitif                                             │
│  ├── Joindre au domaine AD (optionnel)                                       │
│  ├── Activer services (SSH, WinRM, RDP)                                      │
│  ├── Appliquer mises à jour système                                          │
│  ├── Configurer sécurité de base                                             │
│  └── Gérer redémarrages                                                       │
└───────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  STEP 4: SOFTWARE_INSTALLING                                                  │
│  ├── Installer gestionnaire de paquets (Chocolatey)                          │
│  ├── Installer logiciels sélectionnés                                        │
│  ├── Gérer dépendances                                                        │
│  └── Configuration post-installation logiciels                               │
└───────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────────┐
                    │              COMPLETED                       │
                    │         (VM prête à l'usage)                │
                    └─────────────────────────────────────────────┘
```

---

## 4. Modèle de Données

### 4.1 Schéma ERD

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HYPERVISOR                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ PK │ id              │ UUID           │                                      │
│    │ name            │ VARCHAR(100)   │ "Hyper-V Production"                │
│    │ type            │ ENUM           │ hyperv, vmware                       │
│    │ host            │ VARCHAR(255)   │ "hyperv01.domain.local"             │
│    │ port            │ INTEGER        │ 5986                                 │
│    │ use_ssl         │ BOOLEAN        │ true                                 │
│    │ username        │ VARCHAR(100)   │ (chiffré)                           │
│    │ password        │ VARCHAR(255)   │ (chiffré)                           │
│    │ is_active       │ BOOLEAN        │ true                                 │
│    │ created_at      │ TIMESTAMP      │                                      │
│    │ updated_at      │ TIMESTAMP      │                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1:N
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VIRTUAL_MACHINE                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ PK │ id              │ UUID           │                                      │
│ FK │ hypervisor_id   │ UUID           │ → HYPERVISOR.id                     │
│ FK │ os_template_id  │ UUID           │ → OS_TEMPLATE.id                    │
│    │ name            │ VARCHAR(100)   │ "SRV-WEB-001"                       │
│    │ generation      │ INTEGER        │ 1, 2                                 │
│    │ cpu_count       │ INTEGER        │ 4                                    │
│    │ ram_gb          │ INTEGER        │ 8                                    │
│    │ disk_gb         │ INTEGER        │ 100                                  │
│    │ disk_path       │ VARCHAR(500)   │ "D:\VHDs\srv-web-001.vhdx"          │
│    │ network_switch  │ VARCHAR(100)   │ "External-Switch"                   │
│    │ vlan_id         │ INTEGER        │ 100                                  │
│    │ mac_address     │ VARCHAR(17)    │ "00:15:5D:xx:xx:xx"                 │
│    │ ip_config       │ JSONB          │ {type, ip, mask, gateway, dns}      │
│    │ domain_config   │ JSONB          │ {domain, ou, join}                  │
│    │ status          │ ENUM           │ created, running, stopped, error    │
│    │ hyperv_id       │ VARCHAR(100)   │ GUID Hyper-V                        │
│    │ created_at      │ TIMESTAMP      │                                      │
│    │ updated_at      │ TIMESTAMP      │                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1:N
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEPLOYMENT                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ PK │ id              │ UUID           │                                      │
│ FK │ vm_id           │ UUID           │ → VIRTUAL_MACHINE.id                │
│ FK │ created_by      │ UUID           │ → USER.id                           │
│    │ status          │ ENUM           │ pending, vm_creating, os_installing,│
│    │                 │                │ post_configuring, software_install, │
│    │                 │                │ completed, failed, cancelled        │
│    │ current_step    │ VARCHAR(50)    │                                      │
│    │ progress        │ INTEGER        │ 0-100                               │
│    │ error_message   │ TEXT           │                                      │
│    │ started_at      │ TIMESTAMP      │                                      │
│    │ completed_at    │ TIMESTAMP      │                                      │
│    │ created_at      │ TIMESTAMP      │                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 1:N
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEPLOYMENT_LOG                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ PK │ id              │ UUID           │                                      │
│ FK │ deployment_id   │ UUID           │ → DEPLOYMENT.id                     │
│    │ level           │ ENUM           │ info, warning, error, debug         │
│    │ step            │ VARCHAR(50)    │ "vm_creating"                       │
│    │ message         │ TEXT           │                                      │
│    │ details         │ JSONB          │ Contexte supplémentaire             │
│    │ created_at      │ TIMESTAMP      │                                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           OS_TEMPLATE                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ PK │ id              │ UUID           │                                      │
│    │ name            │ VARCHAR(100)   │ "Windows Server 2022 Standard"      │
│    │ os_family       │ ENUM           │ windows, linux                       │
│    │ os_type         │ VARCHAR(50)    │ "windows_server_2022"               │
│    │ architecture    │ ENUM           │ x64, x86, arm64                      │
│    │ iso_path        │ VARCHAR(500)   │ "D:\ISOs\WinServer2022.iso"         │
│    │ unattend_tpl    │ TEXT           │ Template Jinja2                     │
│    │ min_cpu         │ INTEGER        │ 2                                    │
│    │ min_ram_gb      │ INTEGER        │ 4                                    │
│    │ min_disk_gb     │ INTEGER        │ 60                                   │
│    │ is_active       │ BOOLEAN        │                                      │
│    │ created_at      │ TIMESTAMP      │                                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           SOFTWARE_PACKAGE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ PK │ id              │ UUID           │                                      │
│    │ name            │ VARCHAR(100)   │ "Visual Studio Code"                │
│    │ version         │ VARCHAR(50)    │ "latest"                            │
│    │ os_family       │ ENUM           │ windows, linux, both                 │
│    │ install_win     │ TEXT           │ "choco install vscode -y"           │
│    │ install_linux   │ TEXT           │ "apt install code -y"               │
│    │ category        │ VARCHAR(50)    │ "development"                       │
│    │ is_active       │ BOOLEAN        │                                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           VM_SOFTWARE (N:N)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ PK │ vm_id           │ UUID           │ → VIRTUAL_MACHINE.id                │
│ PK │ software_id     │ UUID           │ → SOFTWARE_PACKAGE.id               │
│    │ installed_at    │ TIMESTAMP      │                                      │
│    │ status          │ ENUM           │ pending, installed, failed          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Sécurité

### 5.1 Authentification

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLUX AUTHENTIFICATION                                │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────┐                    ┌──────────┐                ┌──────────┐
    │  Client  │                    │   API    │                │    DB    │
    └──────────┘                    └──────────┘                └──────────┘
         │                               │                           │
         │  1. POST /auth/login          │                           │
         │  {username, password}         │                           │
         │ ─────────────────────────────▶│                           │
         │                               │  2. Verify credentials    │
         │                               │ ─────────────────────────▶│
         │                               │                           │
         │                               │  3. User data             │
         │                               │◀───────────────────────── │
         │                               │                           │
         │  4. {access_token, refresh}   │                           │
         │◀───────────────────────────── │                           │
         │                               │                           │
         │  5. GET /api/vms              │                           │
         │  Authorization: Bearer xxx    │                           │
         │ ─────────────────────────────▶│                           │
         │                               │  6. Validate JWT          │
         │                               │  (in middleware)          │
         │                               │                           │
         │  7. Response                  │                           │
         │◀───────────────────────────── │                           │
```

### 5.2 Gestion des Secrets

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SECRETS MANAGEMENT                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   .env file     │     │   Environment   │     │  Vault/KeyVault │
│   (dev only)    │     │   Variables     │     │  (production)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                      │                       │
         └──────────────────────┼───────────────────────┘
                                │
                                ▼
                    ┌─────────────────────┐
                    │   Pydantic Settings │
                    │   (src/common/      │
                    │    config.py)       │
                    └─────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
        ┌─────────────────┐     ┌─────────────────┐
        │   Application   │     │   Encrypted     │
        │   Runtime       │     │   in Database   │
        └─────────────────┘     │   (credentials) │
                                └─────────────────┘

RÈGLES:
• Jamais de secrets en clair dans le code
• .env JAMAIS commité (dans .gitignore)
• Credentials hyperviseurs chiffrés en DB
• Rotation régulière des secrets
```

---

## 6. Communication avec Hyper-V

### 6.1 Architecture PowerShell

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     POWERSHELL WRAPPER ARCHITECTURE                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│  Python Code    │
│  (hyperv_client)│
└────────┬────────┘
         │
         │ 1. Build PS command
         ▼
┌─────────────────┐
│  PowerShell     │
│  Wrapper        │
│  (common/       │
│   powershell.py)│
└────────┬────────┘
         │
         │ 2. Execute via pywinrm
         ▼
┌─────────────────┐                    ┌─────────────────┐
│  WinRM Client   │ ──────────────────▶│  Hyper-V Host   │
│  (pywinrm)      │   HTTPS:5986       │  (WinRM Server) │
└─────────────────┘                    └────────┬────────┘
                                                │
                                                │ 3. Execute PS
                                                ▼
                                       ┌─────────────────┐
                                       │  PowerShell     │
                                       │  on Hyper-V     │
                                       └────────┬────────┘
                                                │
                                                │ 4. Hyper-V cmdlets
                                                ▼
                                       ┌─────────────────┐
                                       │  Hyper-V WMI    │
                                       │  (New-VM, etc.) │
                                       └─────────────────┘
```

### 6.2 Exemple de Code

```python
# src/integrations/hypervisors/hyperv_client.py

class HyperVClient(BaseHypervisor):
    async def create_vm(self, config: VMConfig) -> VMResult:
        script = f"""
        $vm = New-VM -Name "{config.name}" `
            -Generation {config.generation} `
            -MemoryStartupBytes {config.ram_gb}GB `
            -Path "{self.vm_path}" `
            -NewVHDPath "{config.disk_path}" `
            -NewVHDSizeBytes {config.disk_gb}GB `
            -SwitchName "{config.network_switch}"
        
        Set-VMProcessor -VM $vm -Count {config.cpu_count}
        
        Add-VMDvdDrive -VM $vm -Path "{config.iso_path}"
        
        $vm | Select-Object VMId, Name, State | ConvertTo-Json
        """
        
        result = await self.ps.execute(script)
        return VMResult.from_json(result)
```

---

## 7. Scalabilité

### 7.1 Scaling Horizontal

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCALED ARCHITECTURE                                  │
└─────────────────────────────────────────────────────────────────────────────┘

                            ┌─────────────────┐
                            │  Load Balancer  │
                            │  (nginx/HAProxy)│
                            └────────┬────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
            ┌───────────┐    ┌───────────┐    ┌───────────┐
            │  API #1   │    │  API #2   │    │  API #3   │
            └───────────┘    └───────────┘    └───────────┘
                    │                │                │
                    └────────────────┼────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
            ┌───────────────┐                ┌───────────────┐
            │  PostgreSQL   │                │    Redis      │
            │  (Primary)    │                │   Cluster     │
            │       │       │                └───────────────┘
            │       ▼       │                        │
            │  (Replica)    │                        │
            └───────────────┘                        │
                                                     │
                    ┌────────────────────────────────┘
                    │
        ┌───────────┼───────────┬───────────┐
        │           │           │           │
        ▼           ▼           ▼           ▼
┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│ Worker #1 │ │ Worker #2 │ │ Worker #3 │ │ Worker #4 │
└───────────┘ └───────────┘ └───────────┘ └───────────┘
        │           │           │           │
        └───────────┴───────────┴───────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
            ▼                           ▼
    ┌───────────────┐           ┌───────────────┐
    │  Hyper-V #1   │           │  Hyper-V #2   │
    └───────────────┘           └───────────────┘
```

---

*Document créé le 2026-01-26*
