# VM Automation - Services Post-Installation

## Vue d'ensemble

Apres l'installation de l'OS, le systeme configure automatiquement les services demandes via PowerShell Direct (Windows) ou SSH (Linux).

## Services Windows

### RDP (Remote Desktop)

Active par defaut sur tous les deploiements Windows.

**Ce qui est fait :**
1. Registre : `fDenyTSConnections = 0` (active RDP)
2. Registre : `UserAuthentication = 0` (desactive NLA pour compatibilite)
3. Firewall : `Enable-NetFirewallRule -DisplayGroup "Remote Desktop"` (EN)
4. Firewall : `Enable-NetFirewallRule -DisplayGroup "Bureau à distance"` (FR)

**Pourquoi FR + EN ?** Windows localise les noms de groupes de regles firewall. Une installation FR utilise "Bureau a distance", une EN utilise "Remote Desktop".

### WinRM (Windows Remote Management)

Active par defaut. Permet l'execution de scripts a distance.

**Ce qui est fait :**
- `Enable-PSRemoting -Force -SkipNetworkProfileCheck`
- `Set-Item WSMan:\localhost\Client\TrustedHosts -Value '*'`
- `winrm quickconfig -quiet`

### SSH (OpenSSH Server)

Desactive par defaut, activable via config.

**Ce qui est fait :**
- Installation du feature Windows OpenSSH Server
- Demarrage du service `sshd`
- Configuration du service en demarrage automatique

### Profil reseau

- Profil reseau configure en **Prive** (necessaire pour WinRM et decouverte reseau)
- Decouverte reseau activee (FR + EN)
- Partage de fichiers et imprimantes active (FR + EN)

## Installation de logiciels

### Chocolatey

Le gestionnaire de paquets Chocolatey est installe automatiquement si des packages sont demandes.

### Profils logiciels predefinisq

| Profil | Packages inclus |
|--------|----------------|
| `minimal` | 7zip, notepadplusplus |
| `tools` | 7zip, notepadplusplus, vlc, firefox, vscode |
| `development` | git, nodejs, python, vscode, docker-desktop |
| `webserver` | iis (feature Windows) |
| `database` | sql-server-express |
| `monitoring` | zabbix-agent2, grafana |

### Catalogue logiciels

Plus de 150 packages disponibles dans le catalogue (`src/domain/software_catalog.py`), organises par categories :
- Navigateurs, Outils systeme, Developpement, Bases de donnees
- Securite, Monitoring, Multimedia, Communication, etc.

### Configuration de packages

Certains packages acceptent des configurations personnalisees :

```json
{
  "package_configs": {
    "zabbix-agent2": {
      "server": "192.168.1.126",
      "hostname": "SRV-WEB-01"
    }
  }
}
```

## Post-install Linux

Via SSH, le systeme peut :
- Installer des paquets APT/DNF
- Configurer les cles SSH
- Executer des commandes personnalisees
- Configurer le hostname et le reseau

## Politiques de securite (Windows)

Configurables via le deploiement :
- Longueur minimale mot de passe (4-20)
- Complexite requise (bool)
- Age maximum mot de passe (0-365 jours)

## Post-install manuel

L'endpoint `POST /api/v1/vms/{vm_id}/post-install` permet de relancer le post-install sur une VM existante sans recreer un deploiement complet.

```json
{
  "admin_username": "Administrateur",
  "admin_password": "...",
  "enable_rdp": true,
  "enable_winrm": true,
  "software_profile": "tools",
  "packages": ["notepadplusplus"],
  "install_updates": false
}
```
