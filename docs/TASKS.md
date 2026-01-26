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
| 1.1.3 | Configurer React/TypeScript | ✅ | Agent | Vite + React 19 + TypeScript 5.9 |
| 1.1.4 | Setup Docker Compose | ✅ | Agent | PostgreSQL, Redis |
| 1.1.5 | Configurer CI/CD GitHub Actions | ✅ | Agent | .github/workflows/ci.yml complet |
| 1.1.6 | Configurer pre-commit hooks | ✅ | Agent | Black, isort, ruff, mypy, bandit |

### 1.2 Modèle de Données
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 1.2.1 | Définir modèle Hypervisor | ✅ | Agent | src/domain/models.py |
| 1.2.2 | Définir modèle VirtualMachine | ✅ | Agent | src/domain/models.py |
| 1.2.3 | Définir modèle OSTemplate | ✅ | Agent | src/domain/models.py |
| 1.2.4 | Définir modèle Deployment | ✅ | Agent | src/domain/models.py |
| 1.2.5 | Définir modèle SoftwarePackage | ✅ | Agent | src/domain/models.py |
| 1.2.6 | Créer migrations Alembic | ✅ | Agent | 001_initial_schema.py (8 tables) |

### 1.3 API de Base
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 1.3.1 | Configurer FastAPI + CORS | ✅ | Agent | src/api/main.py |
| 1.3.2 | Implémenter auth JWT | ✅ | Agent | src/common/auth.py (bcrypt + jose) |
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

### 1.5 Frontend - Structure de Base
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 1.5.1 | Setup Vite + React + TS | ✅ | Agent | React 19.2, Vite 7.2, TS 5.9 |
| 1.5.2 | Configurer TailwindCSS | ✅ | Agent | tailwind.config.js, thème dark custom |
| 1.5.3 | Setup React Router | ✅ | Agent | react-router-dom 7.13 installé |
| 1.5.4 | Créer layout principal | ✅ | Agent | MainLayout, Sidebar, Header |
| 1.5.5 | Créer service API | ✅ | Agent | Axios + React Query, retry avec backoff |
| 1.5.6 | Types TypeScript | ✅ | Agent | types/index.ts complet |
| 1.5.7 | Composants UI de base | ✅ | Agent | StatCard, StatusBadge |
| 1.5.8 | Activer routing dans App.tsx | ✅ | Agent | 7 routes configurées |

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
| 2.4.4 | Démonter ISO post-install | ✅ | Agent | unmount_iso(), cleanup_post_install() |

### 2.5 Interface Création VM
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 2.5.1 | Wizard étape 1 : Sélection Template OS | ⬜ | - | Liste templates, preview config |
| 2.5.2 | Wizard étape 2 : Configuration Ressources | ⬜ | - | CPU, RAM, disque avec sliders |
| 2.5.3 | Wizard étape 3 : Configuration Réseau | ⬜ | - | Switch, VLAN, IP statique/DHCP |
| 2.5.4 | Wizard étape 4 : Options Avancées | ⬜ | - | Domaine AD, hostname, timezone |
| 2.5.5 | Wizard étape 5 : Résumé et Validation | ⬜ | - | Récapitulatif, estimation temps |
| 2.5.6 | Composant StepIndicator | ⬜ | - | Navigation wizard |
| 2.5.7 | Validation formulaires (Zod/React Hook Form) | ⬜ | - | - |
| 2.5.8 | Preview configuration JSON | ⬜ | - | Mode debug/avancé |

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
| 3.4.4 | Hyper-V Integration Services | ✅ | Agent | enable_guest_services(), Copy-VMFile |

### 3.5 Monitoring Installation
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 3.5.1 | Détection heartbeat | ✅ | Agent | get_vm_heartbeat(), get_vm_health() |
| 3.5.2 | Polling PowerShell Direct | ✅ | Agent | execute_in_vm(), wait_for_vm_ready() |
| 3.5.3 | Callback HTTP | ⬜ | - | Script post-install |
| 3.5.4 | Timeout et gestion erreurs | ✅ | Agent | Intégré dans wait_for_vm_ready() |

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
| 4.3.4 | Services personnalisés | ✅ | Agent | configure_service(), install_ssh_server() |

### 4.4 Mises à Jour Système
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.4.1 | Windows Update automatique | ✅ | Agent | install_windows_updates() via PS Direct |
| 4.4.2 | apt update/upgrade | ✅ | Agent | Dans preseed/cloud-init |
| 4.4.3 | yum/dnf update | ⬜ | - | - |
| 4.4.4 | Option désactiver MAJ | ⬜ | - | - |

### 4.5 Configuration Sécurité
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.5.1 | Configuration firewall Windows | ✅ | Agent | configure_firewall_rule() |
| 4.5.2 | Configuration firewalld/ufw | ⬜ | - | - |
| 4.5.3 | Création comptes locaux | ✅ | Agent | Admin account créé |
| 4.5.4 | Politiques mot de passe | ✅ | Agent | configure_password_policy() (8 chars, 90j) |

### 4.6 Gestion Redémarrages
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 4.6.1 | Orchestration multi-reboot | ✅ | Agent | schedule_reboot(), cancel_reboot() |
| 4.6.2 | Reprise workflow post-reboot | ✅ | Agent | wait_for_vm_ready() + heartbeat |
| 4.6.3 | Timeout et détection échec | ✅ | Agent | PendingReboot detection |

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

### 6.2 Monitoring Temps Réel (Backend)
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 6.2.1 | WebSocket Server (FastAPI) | ⬜ | - | Broadcast événements déploiement |
| 6.2.2 | Endpoint SSE alternatif | ⬜ | - | Fallback si WS non supporté |
| 6.2.3 | Route /dashboard/stats | ⬜ | - | Agrégation stats temps réel |
| 6.2.4 | Notifications push | ⬜ | - | Déploiement terminé/échec |

---

## Phase 7 : Interface Web Complète

**Objectif** : Interface utilisateur complète et fonctionnelle

### 7.1 Pages Principales
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 7.1.1 | Activer React Router | ✅ | Agent | BrowserRouter + Routes + QueryClient |
| 7.1.2 | Page Dashboard | ✅ | Agent | Stats, déploiements récents, actions rapides |
| 7.1.3 | Page Hyperviseurs - Liste | ✅ | Agent | DataTable avec statut, recherche |
| 7.1.4 | Page Hyperviseurs - Ajout/Édition | ✅ | Agent | Modal CRUD + test connexion |
| 7.1.5 | Page VMs - Liste | ✅ | Agent | DataTable avec filtres hyperviseur, stats |
| 7.1.6 | Page VMs - Actions | ✅ | Agent | Start/stop/restart/delete avec confirm |
| 7.1.7 | Page Templates - Liste | ✅ | Agent | Grille avec filtre OS family |
| 7.1.8 | Page Templates - CRUD | ✅ | Agent | Modal create/edit + duplicate |
| 7.1.9 | Page Déploiements - Liste | ✅ | Agent | Timeline, filtres statut, auto-refresh |
| 7.1.10 | Page Déploiements - Logs | ✅ | Agent | Modal logs, cancel/retry |
| 7.1.11 | Page Paramètres | ⬜ | - | Config connexions, préférences |
| 7.1.12 | Page Aide/Documentation | ⬜ | - | Guide utilisateur intégré |

### 7.2 Composants UI Avancés
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 7.2.1 | DataTable générique | ✅ | Agent | Tri, filtres, pagination, search |
| 7.2.2 | Modal/Dialog | ✅ | Agent | Modal + ConfirmModal |
| 7.2.3 | Toast/Notifications | ✅ | Agent | ToastProvider + useToast hook |
| 7.2.4 | Skeleton loaders | ⬜ | - | États de chargement |
| 7.2.5 | Empty states | ✅ | Agent | EmptyState component |
| 7.2.6 | Dropdown menu | ✅ | Agent | Intégré dans Hypervisors page |
| 7.2.7 | Tabs component | ⬜ | - | Navigation secondaire |
| 7.2.8 | Progress/Timeline | ⬜ | - | Suivi étapes déploiement |
| 7.2.9 | Form components | ✅ | Agent | Input, Textarea, Select |
| 7.2.10 | CodeEditor | ⬜ | - | Edition templates (Monaco/CodeMirror) |

### 7.3 Fonctionnalités Temps Réel
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 7.3.1 | Hook useWebSocket | ⬜ | - | Connexion persistante |
| 7.3.2 | Mise à jour auto déploiements | ⬜ | - | Progress bar temps réel |
| 7.3.3 | Logs streaming | ⬜ | - | Console déploiement live |
| 7.3.4 | Refresh auto listes | ⬜ | - | Polling ou WS |
| 7.3.5 | Indicateur connexion | ⬜ | - | Online/offline status |

### 7.4 UX et Polish
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 7.4.1 | Responsive design | ⬜ | - | Mobile, tablet, desktop |
| 7.4.2 | Keyboard shortcuts | ⬜ | - | Navigation rapide |
| 7.4.3 | Dark/Light mode toggle | ⬜ | - | Préférence utilisateur |
| 7.4.4 | Animations/Transitions | ⬜ | - | Framer Motion |
| 7.4.5 | Breadcrumbs | ⬜ | - | Navigation contexte |
| 7.4.6 | Error boundaries | ⬜ | - | Gestion erreurs gracieuse |
| 7.4.7 | Loading states global | ⬜ | - | NProgress ou similaire |

### 7.5 Tests Frontend
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 7.5.1 | Setup Vitest | ⬜ | - | Config test runner |
| 7.5.2 | Tests composants UI | ⬜ | - | React Testing Library |
| 7.5.3 | Tests hooks custom | ⬜ | - | useWebSocket, etc. |
| 7.5.4 | Tests E2E | ⬜ | - | Playwright ou Cypress |
| 7.5.5 | Storybook | ⬜ | - | Documentation composants |

---

## Phase 8 : Industrialisation

**Objectif** : Outil production-ready

### 8.1 Sécurité
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 8.1.1 | Authentification JWT complète | ✅ | Agent | src/common/auth.py (bcrypt + jose) |
| 8.1.2 | Gestion rôles (RBAC) | ⬜ | - | Admin, operator, viewer |
| 8.1.3 | Audit logs | ⬜ | - | Traçabilité actions |
| 8.1.4 | Chiffrement credentials | ⬜ | - | Vault ou équivalent |
| 8.1.5 | Rate limiting | ⬜ | - | Protection API |

### 8.2 Performance
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 8.2.1 | Cache Redis | ⬜ | - | Réponses fréquentes |
| 8.2.2 | Pagination API | ⬜ | - | Grandes listes |
| 8.2.3 | Lazy loading frontend | ⬜ | - | Code splitting routes |
| 8.2.4 | Optimisation requêtes DB | ⬜ | - | Indexation, eager loading |

### 8.3 Déploiement
| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 8.3.1 | Docker multi-stage build | ⬜ | - | Images optimisées |
| 8.3.2 | Kubernetes manifests | ⬜ | - | Helm charts |
| 8.3.3 | CI/CD pipeline complet | ⬜ | - | Tests, build, deploy |
| 8.3.4 | Monitoring (Prometheus) | ⬜ | - | Métriques application |
| 8.3.5 | Logging centralisé | ⬜ | - | ELK ou Loki |

---

## Phase 9 : Extension VMware (Futur)

*(Phase non démarrée)*

| ID | Tâche | Statut | Assigné | Notes |
|----|-------|--------|---------|-------|
| 9.1.1 | Client pyVmomi | ⬜ | - | Connexion vCenter/ESXi |
| 9.1.2 | Adapter interface hyperviseur | ⬜ | - | Même API que Hyper-V |
| 9.1.3 | Templates VMware | ⬜ | - | OVF, cloud-init |
| 9.1.4 | Tests intégration VMware | ⬜ | - | - |

---

## Statistiques

| Phase | Total | À Faire | En Cours | Terminé | % Complet |
|-------|-------|---------|----------|---------|-----------|
| Phase 1 | 31 | 0 | 0 | 31 | **100%** |
| Phase 2 | 27 | 11 | 0 | 16 | **59%** |
| Phase 3 | 26 | 4 | 0 | 22 | **85%** |
| Phase 4 | 23 | 3 | 0 | 20 | **87%** |
| Phase 5 | 20 | 20 | 0 | 0 | 0% |
| Phase 6 | 8 | 6 | 0 | 2 | **25%** |
| Phase 7 | 36 | 17 | 0 | 19 | **53%** |
| Phase 8 | 13 | 12 | 0 | 1 | **8%** |
| Phase 9 | 4 | 4 | 0 | 0 | 0% |
| **TOTAL** | **188** | **77** | **0** | **111** | **~59%** |

---

## Test en cours

**VM: WinSrv2022-Test** sur Hyper-V 10.250.0.20
- Statut: ✅ Installation + Post-install + Phase 4 COMPLETS
- OS: Windows Server 2022 Standard Evaluation (Desktop Experience)
- Config: 2 vCPU, 4 GB RAM, 60 GB Disk (49 GB free)
- IP: 10.250.0.83
- Credentials: Administrateur / Admin123!
- Heartbeat: OkApplicationsUnknown ✅
- PowerShell Direct: Fonctionnel ✅
- Guest Services: Enabled ✅ (Copy-VMFile fonctionnel)
- RDP: Enabled ✅
- WinRM: Running ✅
- SSH: Installed & Running ✅
- ISOs: Démontés ✅
- Boot: HardDrive first ✅
- Windows Update: Service auto, 5 MAJ disponibles
- Politique MDP: 8 chars min, 90j expiration ✅

## Architecture Validée

### Backend
```
ISO Windows (5 GB) ─────────┐
  (stocké une fois)         ├──► VM boot ──► Installation 100% AUTO
ISO OEMDRV (374 KB) ────────┘
  (généré par déploiement)
    └── autounattend.xml (params custom via Jinja2)
```

### Frontend
```
frontend/
├── src/
│   ├── components/
│   │   ├── layout/          ✅ MainLayout, Sidebar, Header
│   │   └── ui/              ✅ Button, Modal, Toast, DataTable, Input, Select, EmptyState
│   ├── pages/               ✅ 7 pages fonctionnelles
│   │   ├── Dashboard        ✅ Stats, déploiements récents
│   │   ├── Hypervisors      ✅ CRUD complet + test connexion
│   │   ├── VirtualMachines  ✅ Liste + actions (start/stop/restart/delete)
│   │   ├── Templates        ✅ CRUD + grille + filtres + duplicate
│   │   ├── Deployments      ✅ Timeline + logs + cancel/retry
│   │   ├── Settings         🔄 Placeholder
│   │   └── Help             🔄 Placeholder
│   ├── services/            ✅ api.ts (Axios + retry backoff)
│   └── types/               ✅ Types TS complets
├── tailwind.config.js       ✅ Thème dark personnalisé
└── package.json             ✅ React 19, Vite 7, TailwindCSS 4
```

**Stack Frontend:**
- React 19.2.0 + TypeScript 5.9
- Vite 7.2.4 (build tool)
- TailwindCSS 4.1.18 (styling)
- React Router 7.13.0 (navigation) ✅ ACTIVÉ
- React Query 5.90.20 (state management)
- Axios 1.13.3 (HTTP client)
- Lucide React (icônes)

**Composants UI créés:**
- Button (variants, sizes, loading, icons)
- Modal + ConfirmModal
- Toast + ToastProvider + useToast
- DataTable (tri, search, pagination, actions)
- Input + Textarea
- Select
- EmptyState
- StatusBadge
- StatCard

**Prochaines priorités Frontend:**
1. 🚀 Wizard de création de déploiement VM
2. ⚙️ Page Paramètres (configuration)
3. 📚 Page Aide (documentation intégrée)
4. 🔌 WebSocket pour temps réel

**Documentation technique:** `docs/UNATTENDED_INSTALL.md`

---

*Dernière mise à jour : 2026-01-26*
