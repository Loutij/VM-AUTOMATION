# VM Automation - Suivi des Tâches

## Légende des Statuts

| Statut | Icône | Description |
|--------|-------|-------------|
| À FAIRE | ⬜ | Non commencé |
| EN COURS | 🔄 | En développement |
| À TESTER | 🧪 | Développé, en attente de tests |
| TERMINÉ | ✅ | Complété et validé |
| BLOQUÉ | 🚫 | Bloqué par une dépendance |

---

## Phase 1 : Fondations

**Objectif** : API fonctionnelle capable de créer une VM vide sur Hyper-V

### 1.1 Setup Projet
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 1.1.1 | Créer structure dossiers | ✅ | Agent | 26 fichiers Python créés |
| 1.1.2 | Configurer Python/FastAPI | ✅ | Agent | config.py, requirements.txt |
| 1.1.3 | Configurer React/TypeScript | ⬜ | - | - |
| 1.1.4 | Setup Docker Compose | ✅ | Agent | PostgreSQL, Redis |
| 1.1.5 | Configurer CI/CD GitHub Actions | ⬜ | - | Linting, tests |
| 1.1.6 | Configurer pre-commit hooks | ⬜ | - | Black, isort, mypy |

### 1.2 Modèle de Données
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 1.2.1 | Définir modèle Hypervisor | ✅ | Agent | src/domain/models.py |
| 1.2.2 | Définir modèle VirtualMachine | ✅ | Agent | src/domain/models.py |
| 1.2.3 | Définir modèle OSTemplate | ✅ | Agent | src/domain/models.py |
| 1.2.4 | Définir modèle Deployment | ✅ | Agent | src/domain/models.py |
| 1.2.5 | Définir modèle SoftwarePackage | ✅ | Agent | src/domain/models.py |
| 1.2.6 | Créer migrations Alembic | ⬜ | - | - |

### 1.3 API de Base
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 1.3.1 | Configurer FastAPI + CORS | ✅ | Agent | src/api/main.py |
| 1.3.2 | Implémenter auth JWT | ⬜ | - | - |
| 1.3.3 | CRUD Hypervisors | ✅ | Agent | Implémenté avec VMService |
| 1.3.4 | CRUD VirtualMachines | ✅ | Agent | Implémenté avec VMService |
| 1.3.5 | CRUD OSTemplates | ✅ | Agent | Implémenté avec VMService |
| 1.3.6 | Setup Swagger/OpenAPI | ✅ | Agent | /docs disponible |

### 1.4 Client Hyper-V
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 1.4.1 | Wrapper PowerShell exécution | ✅ | Agent | src/common/powershell.py (WinRM) |
| 1.4.2 | Connexion Hyper-V host | ✅ | Agent | Testé sur 10.250.0.20 |
| 1.4.3 | Lister VMs existantes | ✅ | Agent | list_vms() implémenté |
| 1.4.4 | Lister Virtual Switches | ✅ | Agent | External-Switch, Internal-Switch créés |
| 1.4.5 | Créer VM basique | ✅ | Agent | VM WinSrv2022-Test créée |
| 1.4.6 | Démarrer/Arrêter VM | ✅ | Agent | start_vm(), stop_vm(), restart_vm() |

### 1.5 Frontend Skeleton
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 1.5.1 | Setup Vite + React + TS | ⬜ | - | - |
| 1.5.2 | Configurer TailwindCSS | ⬜ | - | - |
| 1.5.3 | Setup React Router | ⬜ | - | - |
| 1.5.4 | Créer layout principal | ⬜ | - | - |
| 1.5.5 | Créer service API | ⬜ | - | Axios/fetch |
| 1.5.6 | Page Dashboard vide | ⬜ | - | - |

---

## Phase 2 : Création de VMs

**Objectif** : Création de VM paramétrée complète via interface

### 2.1 Création VM Complète
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 2.1.1 | Paramètres génération (Gen1/Gen2) | ✅ | Agent | Gen2 par défaut |
| 2.1.2 | Configuration CPU (vCPU) | ✅ | Agent | Paramétrable via VMSpecs |
| 2.1.3 | Configuration RAM (dynamique/statique) | ✅ | Agent | Paramétrable via VMSpecs |
| 2.1.4 | Sélection emplacement VM | ✅ | Agent | C:\HyperV\VirtualMachines |
| 2.1.5 | Nommage automatique/manuel | ✅ | Agent | Paramétrable |

### 2.2 Gestion Réseau
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 2.2.1 | Lister Virtual Switches | ✅ | Agent | list_switches() |
| 2.2.2 | Attacher NIC à switch | ✅ | Agent | Via create_vm() |
| 2.2.3 | Configuration VLAN | ⬜ | - | - |
| 2.2.4 | Récupération adresse MAC | ✅ | Agent | Via Get-VMNetworkAdapter |
| 2.2.5 | Support multi-NIC | ⬜ | - | - |

### 2.3 Gestion Stockage
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 2.3.1 | Créer disque VHDX | ✅ | Agent | Via New-VHD |
| 2.3.2 | Taille dynamique/fixe | ✅ | Agent | Dynamique par défaut |
| 2.3.3 | Sélection emplacement | ✅ | Agent | C:\HyperV\VirtualHardDisks |
| 2.3.4 | Support multi-disques | ⬜ | - | - |

### 2.4 Montage ISO
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 2.4.1 | Lister ISOs disponibles | ✅ | Agent | C:\HyperV\ISOs |
| 2.4.2 | Monter ISO sur DVD | ✅ | Agent | Add-VMDvdDrive |
| 2.4.3 | Configurer boot order | ✅ | Agent | Set-VMFirmware -FirstBootDevice |
| 2.4.4 | Démonter ISO post-install | ⬜ | - | - |

### 2.5 Interface Création
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 2.5.1 | Wizard étape 1 : OS | ⬜ | - | Frontend requis |
| 2.5.2 | Wizard étape 2 : Ressources | ⬜ | - | Frontend requis |
| 2.5.3 | Wizard étape 3 : Réseau | ⬜ | - | Frontend requis |
| 2.5.4 | Wizard étape 4 : Stockage | ⬜ | - | Frontend requis |
| 2.5.5 | Résumé et validation | ⬜ | - | Frontend requis |

---

## Phase 3 : Installation OS Automatique

**Objectif** : Installation OS 100% automatique sans intervention

### 3.1 Templates Windows Unattend
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 3.1.1 | Template Windows 10 | ⬜ | - | - |
| 3.1.2 | Template Windows 11 | ⬜ | - | - |
| 3.1.3 | Template Windows Server 2019 | ⬜ | - | - |
| 3.1.4 | Template Windows Server 2022 | ✅ | Agent | templates/unattend/ + ISO OEMDRV |
| 3.1.5 | Injection clé produit | ✅ | Agent | Supporté dans template |

### 3.2 Templates Linux
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 3.2.1 | Preseed Ubuntu 22.04 | ✅ | Agent | Autoinstall format (Ubuntu 24.04) |
| 3.2.2 | Preseed Debian 12 | ✅ | Agent | templates/preseed/debian_12.cfg |
| 3.2.3 | Kickstart RHEL 9 | ⬜ | - | - |
| 3.2.4 | Kickstart Rocky Linux 9 | ⬜ | - | - |
| 3.2.5 | Cloud-init générique | ✅ | Agent | templates/cloud-init/ |

### 3.3 Génération Dynamique
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 3.3.1 | Moteur de templating Jinja2 | ✅ | Agent | src/domain/template_engine.py |
| 3.3.2 | Injection nom machine | ✅ | Agent | hostname paramétrable |
| 3.3.3 | Injection config réseau | ✅ | Agent | DHCP/Static, DNS, gateway |
| 3.3.4 | Injection mot de passe admin | ✅ | Agent | admin_password paramétrable |
| 3.3.5 | Injection locale/timezone | ✅ | Agent | locale, timezone paramétrables |

### 3.4 Injection Fichiers Réponse
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 3.4.1 | Création ISO OEMDRV | ✅ | Agent | genisoimage avec label OEMDRV |
| 3.4.2 | Montage second DVD | ✅ | Agent | Add-VMDvdDrive |
| 3.4.3 | Copie via SMB | ✅ | Agent | smbclient fonctionnel |
| 3.4.4 | Hyper-V Integration Services | ⬜ | - | - |

### 3.5 Monitoring Installation
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 3.5.1 | Détection heartbeat | 🔄 | Agent | Get-VMIntegrationService |
| 3.5.2 | Polling PowerShell Direct | 🔄 | Agent | Invoke-Command -VMName |
| 3.5.3 | Callback HTTP | ⬜ | - | Script post-install |
| 3.5.4 | Timeout et gestion erreurs | ⬜ | - | - |

### 3.6 Gestion Partitionnement
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 3.6.1 | Schéma par défaut | ✅ | Agent | EFI + MSR + Windows |
| 3.6.2 | Partition personnalisée | ⬜ | - | - |
| 3.6.3 | Support GPT/MBR | ✅ | Agent | GPT pour Gen2 |
| 3.6.4 | Partition data séparée | ⬜ | - | - |

---

## Phase 4 : Post-Installation

**Objectif** : VM configurée et intégrée au domaine

### 4.1 Configuration Réseau
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.1.1 | Configuration DHCP | ✅ | Agent | Par défaut dans templates |
| 4.1.2 | Configuration IP statique | ✅ | Agent | Supporté dans templates |
| 4.1.3 | Configuration DNS | ✅ | Agent | Paramétrable |
| 4.1.4 | Génération resolv.conf (Linux) | ✅ | Agent | Dans cloud-init |
| 4.1.5 | Configuration gateway | ✅ | Agent | Paramétrable |

### 4.2 Jointure Domaine AD
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.2.1 | Jointure Windows | ✅ | Agent | Supporté dans unattend.xml |
| 4.2.2 | Jointure Linux (realmd) | ⬜ | - | sssd |
| 4.2.3 | Placement OU spécifique | ✅ | Agent | Paramétrable |
| 4.2.4 | Gestion credentials sécurisée | ⬜ | - | - |
| 4.2.5 | Validation DNS avant jointure | ⬜ | - | - |

### 4.3 Activation Services
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.3.1 | Activer SSH (Linux) | ✅ | Agent | Dans cloud-init/preseed |
| 4.3.2 | Activer WinRM (Windows) | ✅ | Agent | Enable-PSRemoting dans unattend |
| 4.3.3 | Activer RDP (Windows) | ✅ | Agent | Firewall rule dans unattend |
| 4.3.4 | Services personnalisés | ⬜ | - | - |

### 4.4 Mises à Jour Système
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.4.1 | Windows Update automatique | ⬜ | - | - |
| 4.4.2 | apt update/upgrade | ✅ | Agent | Dans preseed/cloud-init |
| 4.4.3 | yum/dnf update | ⬜ | - | - |
| 4.4.4 | Option désactiver MAJ | ⬜ | - | - |

### 4.5 Configuration Sécurité
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.5.1 | Configuration firewall Windows | ✅ | Agent | RDP rule activée |
| 4.5.2 | Configuration firewalld/ufw | ⬜ | - | - |
| 4.5.3 | Création comptes locaux | ✅ | Agent | Admin account créé |
| 4.5.4 | Politiques mot de passe | ⬜ | - | - |

### 4.6 Gestion Redémarrages
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.6.1 | Orchestration multi-reboot | ⬜ | - | - |
| 4.6.2 | Reprise workflow post-reboot | ⬜ | - | - |
| 4.6.3 | Timeout et détection échec | ⬜ | - | - |

---

## Phase 5 : Installation Logiciels

**Objectif** : Installation automatique de stack logicielle complète

*(Phase non démarrée)*

---

## Phase 6 : Orchestration & Monitoring

**Objectif** : Pipeline end-to-end avec visibilité complète

### 6.1 Workflow Complet
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 6.1.1 | State machine déploiement | ✅ | Agent | DeploymentService avec statuts |
| 6.1.2 | Chaînage tâches Celery | ⬜ | - | - |
| 6.1.3 | Parallélisation possible | ⬜ | - | - |
| 6.1.4 | Points de checkpoint | ✅ | Agent | DeploymentLog par étape |

*(Reste de la phase non démarrée)*

---

## Phase 7 : Industrialisation

**Objectif** : Outil production-ready

*(Phase non démarrée)*

---

## Phase 8 : Extension VMware (Futur)

*(Phase non démarrée)*

---

## Statistiques

| Phase | Total | À Faire | En Cours | Terminé | % Complet |
|-------|-------|---------|----------|---------|-----------|
| Phase 1 | 30 | 8 | 0 | 22 | **73%** |
| Phase 2 | 24 | 9 | 0 | 15 | **63%** |
| Phase 3 | 26 | 8 | 2 | 16 | **62%** |
| Phase 4 | 23 | 12 | 0 | 11 | **48%** |
| Phase 5 | 20 | 20 | 0 | 0 | 0% |
| Phase 6 | 16 | 14 | 0 | 2 | **13%** |
| Phase 7 | 16 | 16 | 0 | 0 | 0% |
| Phase 8 | 7 | 7 | 0 | 0 | 0% |
| **TOTAL** | **162** | **94** | **2** | **66** | **~41%** |

---

## Test en cours

**VM: WinSrv2022-Test** sur Hyper-V 10.250.0.20
- Statut: Installation automatique en cours
- OS: Windows Server 2022 Standard (Desktop Experience)
- Config: 2 vCPU, 4 GB RAM, 60 GB Disk
- Credentials: Administrateur / Admin123!

---

*Dernière mise à jour : 2026-01-26 16:15*
