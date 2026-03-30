# VM Automation - Templates d'Installation

## Vue d'ensemble

Les templates sont des fichiers Jinja2 qui generent les fichiers de reponse automatique pour chaque OS. Ils sont stockes dans `templates/`.

```
templates/
├── unattend/                  # Windows (Answer files XML)
│   ├── windows_server_2022.xml
│   ├── windows_server_2019.xml
│   ├── windows_10.xml
│   └── windows_11.xml
├── preseed/                   # Debian (Preseed)
│   ├── debian_12.cfg
│   └── debian_13.cfg
├── cloud-init/                # Cloud images
│   ├── debian_cloud_init.yaml
│   └── ubuntu_autoinstall.yaml
└── kickstart/                 # RHEL/Rocky (Kickstart)
    ├── rhel_9.cfg
    └── rocky_9.cfg
```

## Variables Jinja2 communes

| Variable | Description | Defaut |
|----------|-------------|--------|
| `hostname` | Nom de la machine | `debian-vm` / `WIN-VM` |
| `admin_password` | Mot de passe administrateur | `TempP@ss123!` |
| `locale` | Locale systeme | `fr-FR` / `fr_FR.UTF-8` |
| `timezone` | Fuseau horaire | `Romance Standard Time` / `Europe/Paris` |
| `keyboard_layout` | Layout clavier | `fr` / `040c:0000040c` |
| `static_ip` | Utiliser IP statique (bool) | `false` |
| `ip_address` | Adresse IP | - |
| `gateway` | Passerelle | - |
| `dns_server_1` | DNS primaire | `8.8.8.8` |
| `dns_server_2` | DNS secondaire | - |
| `post_install_commands` | Commandes post-install | `[]` |

## Templates Windows (Unattend)

### Structure d'un unattend.xml

Les unattend Windows ont 3 phases :

1. **windowsPE** : Partitionnement disque (GPT/UEFI), selection de l'image
2. **specialize** : Nom machine, timezone, **activation RDP** + firewall, IP statique
3. **oobeSystem** : Compte admin, OOBE bypass, AutoLogon, FirstLogonCommands

### Differences Win10/11 vs Server

| Aspect | Server 2019/2022 | Windows 10/11 |
|--------|-------------------|---------------|
| Compte admin | `AdministratorPassword` (active built-in) | `LocalAccount "Admin"` (custom) |
| AutoLogon | `Administrateur` | `Admin` |
| Built-in admin | Active automatiquement | Desactive → active via FirstLogonCommands |
| TPM bypass | N/A | Win11 : bypass TPM/SecureBoot/RAM (si `bypass_tpm`) |
| OOBE network | N/A | Win11 : bypass NRO |

### FirstLogonCommands (Windows)

Toutes les templates executent au premier boot :

1. Activation compte Administrateur built-in (Win10/11 uniquement)
2. WinRM : `Enable-PSRemoting`, `winrm quickconfig`
3. RDP : registre `fDenyTSConnections=0` + firewall FR/EN + NLA desactive
4. Reseau prive + decouverte reseau (FR/EN)
5. Desactivation AutoLogon
6. Jonction domaine AD (optionnel)
7. Callback URL (optionnel)

### Variables specifiques Windows

| Variable | Description |
|----------|-------------|
| `admin_username` | Nom du compte admin (defaut: `Admin` pour Win10/11) |
| `windows_edition` | Edition a installer (`Windows 11 Pro`, `Windows Server 2022 SERVERSTANDARD`) |
| `product_key` | Cle produit (optionnel) |
| `bypass_tpm` | Bypass TPM/SecureBoot (Win11, bool) |
| `join_domain` | Joindre un domaine AD (bool) |
| `domain_name`, `domain_user`, `domain_password`, `domain_ou` | Config AD |
| `callback_url` | URL de callback post-install |
| `local_users` | Liste d'utilisateurs locaux supplementaires |

## Templates Debian (Preseed)

### Paquets installes par defaut

```
openssh-server sudo curl wget vim htop net-tools python3 python3-pip hyperv-daemons
```

### Post-installation (late_command)

- Sudo sans mot de passe pour l'utilisateur
- SSH active
- Cles SSH autorisees (optionnel)
- Commandes personnalisees

### Variables specifiques

| Variable | Description |
|----------|-------------|
| `username` | Utilisateur (defaut: `admin`) |
| `user_password` | Mot de passe |
| `user_password_crypted` | Mot de passe SHA-512 (Debian 13) |
| `ssh_authorized_keys` | Liste de cles SSH publiques |
| `packages` | Paquets supplementaires |
| `mirror_host` | Miroir APT (defaut: `deb.debian.org`) |

## Templates Ubuntu (Autoinstall)

Format Subiquity (Ubuntu 24.04+). Supporte :
- Partitionnement LVM automatique
- SSH avec mot de passe ou cles
- Cloud-init integre
- Guest agent QEMU

## Templates RHEL/Rocky (Kickstart)

Supporte :
- Installation depuis URL ou CDROM
- SELinux enforcing
- Firewalld avec SSH
- Jonction AD (realmd/sssd)
- Red Hat Subscription Manager

## Injection des templates

### Windows (DISM)
Le template est rendu en XML, puis injecte via une ISO OEMDRV (label `OEMDRV`) montee comme second lecteur DVD. Windows Setup le detecte automatiquement.

### Linux (ISO boot)
Le preseed/autoinstall est passe via :
- Parametres kernel (`preseed/url`, `auto`, `priority=critical`)
- HTTP serve depuis le backend
- Ou injecte dans l'initrd
