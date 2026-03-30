# VM Automation - Reference API

Base URL : `http://localhost:8000/api/v1`

Documentation interactive : `http://localhost:8000/docs` (Swagger UI)

## Authentification

Toutes les routes (sauf `/auth/*` et `/health`) necessitent un header `Authorization: Bearer <token>`.

### POST /auth/login
Connexion et obtention du token JWT.

```json
// Request
{ "username": "admin", "password": "..." }

// Response 200
{ "access_token": "eyJ...", "token_type": "bearer" }
```

### POST /auth/register
Creation d'un nouvel utilisateur.

---

## VMs (`/api/v1/vms`)

### GET /vms
Liste les VMs avec pagination et filtres.

Query params : `page`, `page_size`, `status`, `hypervisor_id`, `search`

### GET /vms/{vm_id}
Details d'une VM.

### POST /vms
Cree une VM vide (sans OS).

```json
{
  "name": "SRV-WEB-01",
  "hypervisor_id": "uuid",
  "cpu_count": 4,
  "ram_gb": 8,
  "disk_gb": 100,
  "network_switch": "External-Switch"
}
```

### POST /vms/{vm_id}/start
Demarre une VM.

### POST /vms/{vm_id}/stop
Arrete une VM (force: bool optionnel).

### POST /vms/{vm_id}/restart
Redemarre une VM.

### DELETE /vms/{vm_id}
Supprime une VM.

### GET /vms/{vm_id}/details
Details complets (CPU, RAM, disques, reseau, services integration).

### POST /vms/{vm_id}/post-install
Execute le post-install sur une VM existante.

```json
{
  "admin_username": "Administrateur",
  "admin_password": "...",
  "enable_rdp": true,
  "enable_winrm": true,
  "enable_ssh": false,
  "software_profile": "tools",
  "packages": ["notepadplusplus", "7zip"]
}
```

### GET /vms/{vm_id}/rdp
Telecharge un fichier `.rdp` pour se connecter a la VM.

### POST /vms/{vm_id}/execute
Execute un script PowerShell sur la VM (via PowerShell Direct).

```json
{ "script": "Get-Process | Select-Object -First 5" }
```

### GET /vms/{vm_id}/screenshot
Capture d'ecran de la VM (image PNG via WMI).

---

## Deploiements (`/api/v1/deployments`)

### GET /deployments
Liste les deploiements avec pagination.

### POST /deployments
Lance un nouveau deploiement complet.

```json
{
  "vm_name": "SRV-WEB-01",
  "hypervisor_id": "uuid",
  "os_template_id": "uuid",
  "cpu_count": 4,
  "ram_gb": 8,
  "disk_gb": 100,
  "network_switch": "External-Switch",
  "hostname": "SRV-WEB-01",
  "admin_password": "MyP@ss123!",
  "ip_config": {
    "static_ip": true,
    "ip_address": "192.168.1.100",
    "gateway": "192.168.1.1",
    "dns_server_1": "8.8.8.8"
  },
  "services": {
    "enable_rdp": true,
    "enable_winrm": true,
    "enable_ssh": false
  },
  "software_profile": "tools",
  "packages": ["notepadplusplus"],
  "auto_start": true
}
```

### GET /deployments/{id}
Details d'un deploiement (statut, progression, etape courante).

### GET /deployments/{id}/logs
Logs du deploiement.

### DELETE /deployments/{id}
Annule un deploiement en cours ou supprime un deploiement termine/echoue.

### POST /deployments/{id}/resume
Reprend un deploiement interrompu.

### GET /deployments/progress-mapping
Retourne le mapping etape → pourcentage de progression.

---

## Templates (`/api/v1/templates`)

### GET /templates
Liste les templates OS disponibles.

### POST /templates
Cree un nouveau template.

### PUT /templates/{id}
Met a jour un template.

### DELETE /templates/{id}
Supprime un template.

### POST /templates/{id}/validate
Valide le template Jinja2 (syntaxe).

---

## Hyperviseurs (`/api/v1/hypervisors`)

### GET /hypervisors
Liste les hyperviseurs configures.

### POST /hypervisors
Ajoute un hyperviseur.

```json
{
  "name": "Hyper-V Production",
  "type": "hyperv",
  "host": "hyperv01.domain.local",
  "port": 5986,
  "use_ssl": true,
  "username": "admin",
  "password": "..."
}
```

### PUT /hypervisors/{id}
Met a jour un hyperviseur.

### DELETE /hypervisors/{id}
Supprime un hyperviseur.

### POST /hypervisors/{id}/test
Teste la connexion a l'hyperviseur.

### POST /hypervisors/{id}/sync
Synchronise les VMs de l'hyperviseur avec la DB.

### GET /hypervisors/{id}/switches
Liste les virtual switches disponibles.

### GET /hypervisors/{id}/vms
Liste les VMs de l'hyperviseur.

### POST /hypervisors/{id}/switches
Cree un virtual switch.

### DELETE /hypervisors/{id}/switches/{switch_name}
Supprime un virtual switch.

### GET /hypervisors/{id}/physical-adapters
Liste les adaptateurs reseau physiques (pour creation de switch externe).

### GET /hypervisors/{id}/isos
Liste les fichiers ISO disponibles sur l'hyperviseur.

### GET /hypervisors/{id}/storage-locations
Liste les emplacements de stockage avec espace libre.

### GET /hypervisors/{id}/disk-space
Verifie l'espace disque disponible.

### GET /hypervisors/{id}/orphan-vhdx
Liste les fichiers VHDX orphelins (sans VM associee).

### DELETE /hypervisors/{id}/orphan-vhdx
Supprime les fichiers VHDX orphelins.

---

## Parametres (`/api/v1/settings`)

### GET /settings
Retourne la configuration de l'application.

### GET /settings/smtp
Retourne la configuration SMTP.

### PUT /settings/smtp
Met a jour la configuration SMTP.

### POST /settings/smtp/test
Envoie un email de test pour verifier la configuration SMTP.

---

## Catalogue Logiciels (`/api/v1/software-catalog`)

### GET /software-catalog
Retourne le catalogue complet (150+ packages Windows).

### GET /software-catalog/profiles
Retourne les profils logiciels predefinisq (minimal, tools, development, webserver, database, monitoring).

---

## Sante (`/health`)

### GET /health
Statut de sante basique.

### GET /health/detailed
Statut detaille (DB, Redis, Celery workers).

---

## WebSocket

### /ws/realtime
Evenements temps reel (deploiements, VMs).

```json
// Messages recus
{ "type": "deployment_progress", "deployment_id": "...", "progress": 45, "step": "installing_software" }
{ "type": "vm_state_changed", "vm_id": "...", "state": "running" }
```

### /console/ws/{vm_id}
Console graphique VM. Envoie des frames PNG (screenshots WMI), recoit des events clavier.

```json
// Messages envoyes par le client
{ "type": "key", "key": "enter" }
{ "type": "text", "text": "Hello" }
{ "type": "special", "key": "ctrl+alt+del" }
```

### /terminal/ws/{vm_id}
Terminal PowerShell Direct. Envoie/recoit du texte.

```json
// Message envoye
{ "type": "input", "data": "Get-Process\n" }

// Message recu
{ "type": "output", "data": "Handles  NPM(K)..." }
```

---

## Callbacks (`/api/v1/callbacks`)

### POST /callbacks/deployment/{deployment_id}
Callback appele par la VM apres installation (via unattend FirstLogonCommands).

```json
{ "hostname": "SRV-WEB-01", "status": "completed" }
```
