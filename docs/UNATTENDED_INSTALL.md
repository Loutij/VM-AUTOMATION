# Installation Automatique Windows - Guide Technique

## Methode de deploiement : DISM

Le systeme utilise **DISM** (Deployment Image Servicing and Management) comme methode principale de deploiement Windows. L'image WIM est appliquee directement sur le VHDX offline, evitant le boot ISO et le prompt "Press any key".

```
1. Creer VHDX vide (dynamique)
2. Monter VHDX sur l'hote Hyper-V
3. Partitionner (GPT: EFI + MSR + Windows)
4. Appliquer image WIM via DISM (~90 secondes)
5. Injecter autounattend.xml + setup.ps1 via RunOnce
6. Demonter VHDX
7. Demarrer la VM → OOBE automatique
```

### Avantages par rapport au boot ISO

- Pas de "Press any key to boot from CD or DVD"
- Deploiement plus rapide (~90s vs ~15min)
- Pas besoin de monter 2 DVDs (ISO Windows + OEMDRV)
- Pas besoin d'envoyer des touches clavier via WMI

## Selection automatique du template unattend

Le systeme selectionne automatiquement le bon template XML selon l'OS :

| OS | Template | Compte admin |
|----|----------|-------------|
| Windows 10 | `windows_10.xml` | `Admin` (+ Administrateur active) |
| Windows 11 | `windows_11.xml` | `Admin` (+ Administrateur active) |
| Windows Server 2019 | `windows_server_2019.xml` | `Administrateur` |
| Windows Server 2022 | `windows_server_2022.xml` | `Administrateur` |

La selection est faite par `_select_windows_unattend()` dans `src/domain/template_engine.py` :

```python
def _select_windows_unattend(self, template_name, windows_edition):
    name_lower = (template_name or "").lower()
    if "11" in name_lower:
        return "windows_11.xml"
    if "10" in name_lower:
        return "windows_10.xml"
    if "2019" in name_lower:
        return "windows_server_2019.xml"
    return "windows_server_2022.xml"
```

## Differences Win10/11 vs Server

### Windows 10/11 (editions client)

- Le compte built-in `Administrateur` est **desactive par defaut**
- Le template cree un compte `Admin` avec mot de passe
- `FirstLogonCommands` active le built-in Administrateur en fallback :
  ```xml
  <CommandLine>cmd /c net user Administrateur "password" /active:yes &amp; net user Administrator "password" /active:yes</CommandLine>
  ```
- Les credentials tentent `Admin` en premier, puis `Administrateur`/`Administrator`

### Windows Server (2019/2022)

- Le compte built-in `Administrateur` est **active par defaut**
- Le template utilise `<AdministratorPassword>` directement
- AutoLogon sur `Administrateur`

## Activation RDP (3 niveaux redondants)

Le RDP est active a 3 niveaux pour garantir l'acces :

### 1. Specialize pass (unattend)
```xml
<RunSynchronous>
  <RunSynchronousCommand>
    <Path>reg add "HKLM\System\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f</Path>
  </RunSynchronousCommand>
</RunSynchronous>
```

### 2. FirstLogonCommands (unattend)
```xml
<CommandLine>cmd /c reg add ... &amp; netsh advfirewall firewall set rule group="Remote Desktop" new enable=Yes &amp; netsh advfirewall firewall set rule group="Bureau a distance" new enable=Yes &amp; reg add ... UserAuthentication ... /d 0</CommandLine>
```

### 3. Post-configuration Python (PowerShell Direct)
```python
rdp_script = """
Set-ItemProperty -Path 'HKLM:\\...\\Terminal Server' -Name "fDenyTSConnections" -Value 0
Set-ItemProperty -Path 'HKLM:\\...\\RDP-Tcp' -Name "UserAuthentication" -Value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop" -ErrorAction SilentlyContinue
Enable-NetFirewallRule -DisplayGroup "Bureau a distance" -ErrorAction SilentlyContinue
"""
```

> **Note** : Les deux groupes firewall (FR: "Bureau a distance", EN: "Remote Desktop") sont toujours configures pour supporter les deux langues.

## Templates unattend.xml

Les templates sont dans `templates/unattend/` et utilisent Jinja2 :

### Variables disponibles

| Variable | Description | Defaut |
|----------|-------------|--------|
| `hostname` | Nom de la machine | (obligatoire) |
| `admin_password` | Mot de passe admin | `TempP@ss123!` |
| `timezone` | Fuseau horaire | `Romance Standard Time` |
| `locale` | Locale d'installation | `fr-FR` |
| `product_key` | Cle de licence Windows | (optionnel) |
| `organization` | Nom de l'organisation | `VM Automation` |
| `domain_name` | Domaine AD a joindre | (optionnel) |
| `domain_username` | Compte AD pour jointure | (optionnel) |
| `domain_password` | Mot de passe AD | (optionnel) |
| `domain_ou` | OU cible pour la VM | (optionnel) |

### Structure d'un template

```xml
<unattend>
  <!-- Phase WindowsPE: Partitionnement + Selection image -->
  <settings pass="windowsPE">
    <!-- Locale, partitions GPT/UEFI, selection image WIM par index -->
  </settings>

  <!-- Phase Specialize: Nom machine, timezone, RDP -->
  <settings pass="specialize">
    <!-- ComputerName, TimeZone, activation RDP registre -->
  </settings>

  <!-- Phase OOBE: Mot de passe admin, autologon, FirstLogonCommands -->
  <settings pass="oobeSystem">
    <!-- Admin password, AutoLogon, RDP firewall, services -->
  </settings>
</unattend>
```

## Methode alternative : ISO OEMDRV

Pour les cas ou DISM n'est pas disponible (pas d'acces au fichier WIM), la methode ISO OEMDRV reste supportee :

1. Generer `autounattend.xml` via Jinja2
2. Creer une ISO avec le label `OEMDRV` (genisoimage)
3. Monter 2 DVDs : ISO Windows + ISO OEMDRV
4. Booter la VM sur le DVD Windows
5. Windows detecte automatiquement l'autounattend.xml sur OEMDRV

```bash
genisoimage -V "OEMDRV" -J -r -o /tmp/oemdrv.iso /tmp/oemdrv_content/
```

## Fichiers cles

| Fichier | Description |
|---------|-------------|
| `src/domain/template_engine.py` | Selection et rendu des templates (Jinja2) |
| `src/domain/deployment_service.py` | Logique de deploiement DISM + post-config |
| `src/integrations/hypervisors/hyperv_client.py` | `deploy_with_dism()`, PowerShell Direct |
| `templates/unattend/windows_10.xml` | Template Windows 10 |
| `templates/unattend/windows_11.xml` | Template Windows 11 |
| `templates/unattend/windows_server_2019.xml` | Template Server 2019 |
| `templates/unattend/windows_server_2022.xml` | Template Server 2022 |

## Deploiement Linux

Les templates Linux sont dans `templates/preseed/` et `templates/cloud-init/` :

| OS | Methode | Fichier |
|----|---------|---------|
| Debian 12 | Preseed | `templates/preseed/debian_12.cfg` |
| Debian 13 | Preseed | `templates/preseed/debian_13.cfg` |
| Ubuntu 24.04 | Autoinstall | `templates/cloud-init/ubuntu_autoinstall.yaml` |
| Generique | Cloud-init | `templates/cloud-init/debian_cloud_init.yaml` |

Le deploiement Linux utilise l'ISO + preseed/cloud-init, pas DISM.

*Derniere mise a jour : 2026-03-05*
