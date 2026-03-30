# VM Automation - Workflow de Deploiement

## Vue d'ensemble

Un deploiement passe par 9 etapes sequentielles, gerees par `DeploymentService` et executees par les workers Celery.

## Etapes du deploiement

### Windows (DISM)

```
1. VALIDATING (0%)         Validation config, espace disque, template
        |
2. CREATING_VM (10%)       Creation VM Hyper-V (VHDX, CPU, RAM, switch)
        |
3. MOUNTING_ISO (20%)      DISM : montage ISO, application image Windows sur VHDX
        |                  + injection unattend.xml via ISO OEMDRV
4. CONFIGURING_NETWORK     Configuration registre offline (OOBE bypass, RunOnce)
   (30%)
        |
5. STARTING_INSTALL (40%)  Demarrage de la VM
        |
6. WAITING_VM_READY (50%)  Attente heartbeat + PowerShell Direct (timeout 15 min)
        |
7. POST_CONFIGURATION      Activation services : RDP, WinRM, SSH
   (70%)                   Configuration securite, firewall, reseau prive
        |
8. INSTALLING_SOFTWARE     Installation Chocolatey + packages selectionnes
   (85%)
        |
9. FINALIZING (95%)        Nettoyage, mise a jour DB, notification
        |
   COMPLETED (100%)
```

### Linux (ISO + Preseed/Cloud-init)

```
1. VALIDATING (0%)         Validation config
        |
2. CREATING_VM (10%)       Creation VM Hyper-V (VHDX, CPU, RAM, switch)
        |
3. MOUNTING_ISO (20%)      Montage ISO Linux + injection preseed/cloud-init
        |
4. GENERATING_UNATTEND     Generation du fichier preseed/cloud-init/kickstart
   (25%)
        |
5. STARTING_INSTALL (40%)  Demarrage VM, boot sur ISO
        |
6. WAITING_VM_READY (50%)  Attente SSH accessible (timeout 30 min)
        |
7. POST_CONFIGURATION      Configuration via SSH (paquets, services, cles SSH)
   (70%)
        |
8. INSTALLING_SOFTWARE     Installation paquets supplementaires
   (85%)
        |
9. FINALIZING (95%)        Nettoyage, demontage ISO
        |
   COMPLETED (100%)
```

## Selection du template unattend

Le systeme selectionne automatiquement le bon fichier unattend selon l'OS :

| Template DB | Fichier unattend | Compte admin |
|-------------|-----------------|--------------|
| Windows Server 2022 | `windows_server_2022.xml` | Built-in `Administrateur` |
| Windows Server 2019 | `windows_server_2019.xml` | Built-in `Administrateur` |
| Windows 11 | `windows_11.xml` | Custom `Admin` + active built-in |
| Windows 10 | `windows_10.xml` | Custom `Admin` + active built-in |
| Debian 12 | `debian_12.cfg` | Custom `admin` (sudo) |
| Debian 13 | `debian_13.cfg` | Custom `admin` (sudo) |
| Ubuntu | `ubuntu_autoinstall.yaml` | Custom `admin` (sudo) |
| RHEL/Rocky 9 | `rhel_9.cfg` / `rocky_9.cfg` | `root` |

## Configuration des services

Par defaut lors d'un deploiement :

| Service | Windows | Linux |
|---------|---------|-------|
| RDP | Active (registre + firewall FR/EN + NLA desactive) | N/A |
| WinRM | Active (PSRemoting + TrustedHosts) | N/A |
| SSH | Desactive par defaut | Active (openssh-server) |

## Gestion des credentials

La fonction `_build_admin_credentials()` essaie dans l'ordre :
1. `admin_username` de la config du deploiement
2. `admin_username` des settings globaux
3. Fallback : `Administrateur` (FR) → `Administrator` (EN) → `Admin` (Win10/11)

## Mecanismes de fallback

Si le post-install echoue, un **fallback script** est injecte via :
1. WinRM direct (si IP disponible)
2. PowerShell Direct (via Hyper-V)

Le fallback configure : mot de passe admin, WinRM, RDP, reseau prive, flag `ready.flag`.

## Progression WebSocket

La progression est envoyee en temps reel via WebSocket (`/ws/realtime`) :

```json
{
  "type": "deployment_progress",
  "deployment_id": "uuid",
  "progress": 45,
  "step": "waiting_vm_ready",
  "message": "Waiting for VM heartbeat..."
}
```
