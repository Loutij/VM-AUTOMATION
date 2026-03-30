# VM Automation - Documentation

## Index

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architecture technique, structure du code, modele de donnees |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Installation, configuration, premier lancement |
| [PREREQUISITES.md](PREREQUISITES.md) | Prerequis infrastructure (Hyper-V, reseau, stockage) |
| [API_REFERENCE.md](API_REFERENCE.md) | Reference complete de l'API REST et WebSocket |
| [DEPLOYMENT_WORKFLOW.md](DEPLOYMENT_WORKFLOW.md) | Flux de deploiement VM de bout en bout |
| [TEMPLATES.md](TEMPLATES.md) | Templates d'installation (unattend, preseed, cloud-init, kickstart) |
| [POST_INSTALL.md](POST_INSTALL.md) | Services post-installation (RDP, WinRM, SSH, logiciels) |
| [FRONTEND.md](FRONTEND.md) | Application frontend React (pages, composants, hooks) |
| [VNC_CONSOLE.md](VNC_CONSOLE.md) | Console VNC/RDP dans le navigateur (noVNC, Guacamole) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Guide de depannage et problemes connus |
| [ENV_REFERENCE.md](ENV_REFERENCE.md) | Reference des variables d'environnement |
| [UNATTENDED_INSTALL.md](UNATTENDED_INSTALL.md) | Guide technique installation automatique Windows |
| [TASKS.md](TASKS.md) | Suivi detaille des taches par phase |
| [HANDOFF.md](HANDOFF.md) | Etat du projet et transfert de session |

## Projet

**VM Automation** est un outil interne d'automatisation du deploiement de machines virtuelles sur Hyper-V. Il permet de creer, installer et configurer des VMs Windows et Linux de maniere 100% automatisee, de la creation du disque virtuel jusqu'a l'installation des logiciels.

### Stack technique

- **Backend** : Python 3.11+ / FastAPI / SQLAlchemy / Celery
- **Frontend** : React 19 / TypeScript / Vite / TailwindCSS
- **Infrastructure** : PostgreSQL / Redis / Docker Compose
- **Hyperviseur** : Hyper-V via WinRM/PowerShell
