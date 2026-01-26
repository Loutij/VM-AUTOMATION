# VM Automation Tool

Outil d'automatisation complète du déploiement de machines virtuelles pour Hyper-V (et VMware à terme).

## Objectif

Supprimer toute intervention humaine lors de la création, de l'installation et de la configuration des serveurs ou postes virtuels. Une machine est **100% prête à l'usage dès le premier démarrage**.

## Fonctionnalités Principales

- **Création de VMs** : CPU, RAM, disque, réseau, VLAN
- **Installation OS automatique** : Windows 10/11/Server, Linux (Ubuntu, Debian, RHEL)
- **Configuration post-installation** : Réseau, domaine AD, services, mises à jour
- **Installation logiciels** : Catalogue prédéfini, profils par rôle
- **Interface web** : Dashboard, wizard de création, monitoring temps réel
- **API REST** : Intégration avec d'autres outils

## Stack Technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.11+ / FastAPI |
| Frontend | React 18 / TypeScript |
| Database | PostgreSQL 15+ |
| Queue | Celery / Redis |
| Hyperviseur | Hyper-V (PowerShell), VMware (futur) |

## Prérequis

Voir [PREREQUISITES.md](./docs/PREREQUISITES.md) pour la liste complète.

### Résumé
- Windows Server 2019+ avec rôle Hyper-V
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+
- PowerShell 7+

## Installation Rapide

```bash
# Cloner
git clone https://github.com/votre-org/vm-automation.git
cd vm-automation

# Backend
python -m venv venv
.\venv\Scripts\Activate
pip install -r requirements.txt

# Configuration
cp .env.example .env
# Éditer .env

# Services
docker-compose up -d

# Lancer
uvicorn src.api.main:app --reload
```

## Documentation

- [Documentation principale](./documentation.md)
- [Prérequis détaillés](./docs/PREREQUISITES.md)
- [Suivi des tâches](./docs/TASKS.md)
- [Architecture](./docs/ARCHITECTURE.md)

## Workflow de Déploiement

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Création  │───▶│ Installation│───▶│   Post-     │───▶│  Logiciels  │
│     VM      │    │     OS      │    │  Install    │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                                │
                                                                ▼
                                                        ┌─────────────┐
                                                        │  VM PRÊTE   │
                                                        │    100%     │
                                                        └─────────────┘
```

## Structure du Projet

```
vm-automation/
├── src/
│   ├── api/              # FastAPI
│   ├── domain/           # Logique métier
│   ├── integrations/     # Clients Hyper-V, AD, etc.
│   ├── workers/          # Tâches Celery
│   └── common/           # Utilitaires
├── frontend/             # React app
├── templates/            # Templates unattend/preseed
├── scripts/              # PowerShell, Ansible
├── tests/
└── docs/
```

## Contribution

1. Créer une branche feature (`git checkout -b feat/ma-feature`)
2. Commiter (`git commit -m "feat(module): description"`)
3. Pusher (`git push origin feat/ma-feature`)
4. Créer une Pull Request

## Licence

Propriétaire - Usage interne uniquement

## Contact

Équipe Infrastructure IT
