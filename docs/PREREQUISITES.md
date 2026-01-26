# VM Automation - Prérequis Techniques

## 1. Infrastructure Serveur

### 1.1 Serveur Hyper-V (Hôte)

| Composant | Exigence | Notes |
|-----------|----------|-------|
| **OS** | Windows Server 2019/2022 | Datacenter ou Standard |
| **Rôle** | Hyper-V activé | `Install-WindowsFeature -Name Hyper-V -IncludeManagementTools` |
| **CPU** | Support virtualisation | VT-x/AMD-V activé dans BIOS |
| **RAM** | Minimum 32 Go | Selon nombre VMs simultanées |
| **Stockage** | SSD recommandé | Minimum 500 Go pour VHDx |
| **Réseau** | Minimum 1 Gbps | Dédié aux VMs |

### 1.2 Serveur Application (Backend)

| Composant | Exigence | Notes |
|-----------|----------|-------|
| **OS** | Windows Server 2019+ ou Linux | Ubuntu 22.04 LTS recommandé |
| **CPU** | 4 vCPU minimum | 8 vCPU recommandé |
| **RAM** | 8 Go minimum | 16 Go recommandé |
| **Stockage** | 100 Go SSD | Pour app + logs |

### 1.3 Base de Données

| Composant | Exigence | Notes |
|-----------|----------|-------|
| **PostgreSQL** | Version 15+ | Peut être conteneurisé |
| **RAM** | 4 Go minimum | Selon charge |
| **Stockage** | 50 Go SSD | Pour data + WAL |

### 1.4 Cache / Queue

| Composant | Exigence | Notes |
|-----------|----------|-------|
| **Redis** | Version 7+ | Peut être conteneurisé |
| **RAM** | 2 Go minimum | - |

---

## 2. Logiciels Requis

### 2.1 Serveur Backend

```bash
# Python
Python 3.11+

# Node.js (pour frontend)
Node.js 18 LTS+
npm 9+

# PowerShell (si backend Windows)
PowerShell 7+

# Docker (optionnel mais recommandé)
Docker 24+
Docker Compose 2.20+
```

### 2.2 Serveur Hyper-V

```powershell
# PowerShell Modules
Install-Module -Name Hyper-V -Force
Install-Module -Name PSRemoting -Force

# Activer PowerShell Remoting
Enable-PSRemoting -Force

# Configurer WinRM
winrm quickconfig -q
Set-Item WSMan:\localhost\Client\TrustedHosts -Value "*" -Force
```

### 2.3 Dépendances Python

```txt
# requirements.txt
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
sqlalchemy>=2.0.0
alembic>=1.13.0
asyncpg>=0.29.0
celery>=5.3.0
redis>=5.0.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.0
jinja2>=3.1.0
pywinrm>=0.4.3
httpx>=0.26.0
python-multipart>=0.0.6
pydantic-settings>=2.1.0
```

### 2.4 Dépendances Frontend

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.21.0",
    "axios": "^1.6.0",
    "@tanstack/react-query": "^5.17.0",
    "zustand": "^4.4.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "@types/react": "^18.2.0"
  }
}
```

---

## 3. Configuration Réseau

### 3.1 Ports à Ouvrir

| Service | Port | Direction | Notes |
|---------|------|-----------|-------|
| API Backend | 8000 | Inbound | FastAPI |
| Frontend | 3000 | Inbound | Dev uniquement |
| Frontend | 80/443 | Inbound | Production |
| PostgreSQL | 5432 | Backend → DB | Peut être local |
| Redis | 6379 | Backend → Redis | Peut être local |
| WinRM HTTP | 5985 | Backend → Hyper-V | HTTP |
| WinRM HTTPS | 5986 | Backend → Hyper-V | HTTPS (recommandé) |
| PowerShell Remoting | 5985/5986 | Backend → Hyper-V | - |

### 3.2 Configuration WinRM (Hyper-V Host)

```powershell
# Sur le serveur Hyper-V

# Activer WinRM
Enable-PSRemoting -Force

# Configurer pour HTTPS (recommandé)
$cert = New-SelfSignedCertificate -DnsName $env:COMPUTERNAME -CertStoreLocation Cert:\LocalMachine\My

New-Item -Path WSMan:\localhost\Listener -Transport HTTPS -Address * -CertificateThumbPrint $cert.Thumbprint -Force

# Ou pour HTTP (dev uniquement)
Set-Item WSMan:\localhost\Client\TrustedHosts -Value "backend-server-ip" -Force

# Ouvrir firewall
New-NetFirewallRule -Name "WinRM-HTTPS" -DisplayName "WinRM HTTPS" -Enabled True -Direction Inbound -Protocol TCP -LocalPort 5986 -Action Allow

# Vérifier
Test-WSMan -ComputerName localhost
```

### 3.3 Virtual Switch Hyper-V

```powershell
# Créer un switch externe pour les VMs
$adapter = Get-NetAdapter | Where-Object {$_.Status -eq 'Up' -and $_.InterfaceDescription -notlike '*Virtual*'} | Select-Object -First 1

New-VMSwitch -Name "External-Switch" -NetAdapterName $adapter.Name -AllowManagementOS $true

# Ou switch interne pour réseau isolé
New-VMSwitch -Name "Internal-Switch" -SwitchType Internal
```

---

## 4. Stockage

### 4.1 Structure des Répertoires (Hyper-V Host)

```
D:\HyperV\                      # Racine Hyper-V (SSD recommandé)
├── VirtualMachines\            # Configurations VMs
├── VirtualHardDisks\           # Fichiers VHDX
└── ISOs\                       # Images ISO
    ├── Windows\
    │   ├── Win10_22H2.iso
    │   ├── Win11_23H2.iso
    │   ├── WinServer2019.iso
    │   └── WinServer2022.iso
    └── Linux\
        ├── ubuntu-22.04-server.iso
        ├── debian-12.iso
        └── rocky-9.iso
```

### 4.2 Permissions

```powershell
# Donner accès au compte de service
$servicePath = "D:\HyperV"
$serviceAccount = "DOMAIN\svc-vmautomation"

$acl = Get-Acl $servicePath
$permission = "$serviceAccount","FullControl","ContainerInherit,ObjectInherit","None","Allow"
$accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule $permission
$acl.SetAccessRule($accessRule)
Set-Acl $servicePath $acl
```

---

## 5. Active Directory (Optionnel)

### 5.1 Compte de Service

```powershell
# Créer un compte de service pour la jointure domaine
New-ADUser -Name "svc-vmautomation" `
    -SamAccountName "svc-vmautomation" `
    -UserPrincipalName "svc-vmautomation@domain.local" `
    -AccountPassword (ConvertTo-SecureString "P@ssw0rd!" -AsPlainText -Force) `
    -Enabled $true `
    -PasswordNeverExpires $true `
    -CannotChangePassword $true

# Déléguer le droit de joindre des machines au domaine
# Dans ADUC : Délégation de contrôle sur l'OU cible
```

### 5.2 OU pour les VMs

```powershell
# Créer une OU dédiée
New-ADOrganizationalUnit -Name "VMs-Automatisees" -Path "DC=domain,DC=local"
New-ADOrganizationalUnit -Name "Serveurs" -Path "OU=VMs-Automatisees,DC=domain,DC=local"
New-ADOrganizationalUnit -Name "Postes" -Path "OU=VMs-Automatisees,DC=domain,DC=local"
```

---

## 6. ISOs et Licences

### 6.1 Images ISO Requises

| OS | Version | Source |
|----|---------|--------|
| Windows 10 | 22H2 | Volume Licensing / VLSC |
| Windows 11 | 23H2 | Volume Licensing / VLSC |
| Windows Server | 2019/2022 | Volume Licensing / VLSC |
| Ubuntu Server | 22.04 LTS | ubuntu.com |
| Debian | 12 | debian.org |
| Rocky Linux | 9 | rockylinux.org |

### 6.2 Clés de Licence

- **Windows** : Utiliser des clés KMS ou MAK selon l'environnement
- **KMS** : Configurer un serveur KMS interne
- **Linux** : Pas de licence requise (open source)

---

## 7. Checklist de Validation

### 7.1 Avant Installation

- [ ] Serveur Hyper-V accessible en réseau
- [ ] Rôle Hyper-V installé et fonctionnel
- [ ] WinRM configuré et testé
- [ ] Virtual Switch créé
- [ ] ISOs copiés sur le serveur
- [ ] Python 3.11+ installé
- [ ] Node.js 18+ installé
- [ ] PostgreSQL accessible
- [ ] Redis accessible
- [ ] Compte de service AD créé (si AD)

### 7.2 Tests de Connectivité

```powershell
# Depuis le serveur backend

# Test WinRM
Test-WSMan -ComputerName hyperv-host.domain.local

# Test PowerShell Remoting
Enter-PSSession -ComputerName hyperv-host.domain.local -Credential (Get-Credential)

# Test Hyper-V
Invoke-Command -ComputerName hyperv-host.domain.local -ScriptBlock { Get-VM } -Credential (Get-Credential)
```

```bash
# Test PostgreSQL
psql -h db-host -U vmautomation -d vmautomation -c "SELECT 1"

# Test Redis
redis-cli -h redis-host ping
```

---

## 8. Dimensionnement

### 8.1 Estimation Ressources par VM

| Type VM | CPU | RAM | Disque |
|---------|-----|-----|--------|
| Poste Windows 10/11 | 2-4 | 4-8 Go | 60-100 Go |
| Serveur Windows | 2-8 | 4-32 Go | 80-200 Go |
| Serveur Linux | 1-4 | 1-16 Go | 20-100 Go |

### 8.2 Capacité Hôte Hyper-V

```
Exemple : Serveur 128 Go RAM, 2 To SSD

VMs possibles (estimation) :
- 20 postes Windows (4 Go RAM chacun)
- ou 8 serveurs Windows (16 Go RAM chacun)
- ou 30 serveurs Linux légers (4 Go RAM chacun)
- ou mix selon besoins
```

---

*Document créé le 2026-01-26*
