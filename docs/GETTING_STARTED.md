# VM Automation - Guide de Demarrage

## Prerequis

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- Acces a un serveur Hyper-V (WinRM active)

Voir [PREREQUISITES.md](PREREQUISITES.md) pour les details infrastructure.

## 1. Cloner le projet

```bash
git clone <repo-url>
cd VM-AUTOMATION
```

## 2. Backend

### Environnement Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

```bash
cp config/env.example .env
# Editer .env avec vos valeurs (credentials Hyper-V, etc.)
```

Voir [ENV_REFERENCE.md](ENV_REFERENCE.md) pour toutes les variables.

### Services Docker (PostgreSQL + Redis)

```bash
docker compose up -d
```

### Base de donnees

```bash
# Appliquer les migrations
alembic upgrade head
```

### Lancer l'API

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

API accessible sur http://localhost:8000
Documentation Swagger : http://localhost:8000/docs

### Lancer les workers Celery

```bash
celery -A src.workers.celery_app worker --loglevel=info
```

### Monitoring Celery (optionnel)

```bash
# Flower disponible via Docker Compose sur http://localhost:5555
```

## 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend accessible sur http://localhost:5173

## 4. Premier deploiement

1. Ouvrir http://localhost:5173
2. Se connecter (ou creer un compte via l'API `/auth/register`)
3. Aller dans **Hyperviseurs** > Ajouter votre serveur Hyper-V
4. Cliquer **Tester la connexion** pour verifier
5. Aller dans **Templates** > Verifier que les templates OS sont presents
6. Aller dans **Nouveau Deploiement** > Suivre le wizard

## 5. Service systemd (production)

```bash
# Installer le service
sudo bash scripts/install-systemd-service.sh

# Gerer le service
sudo systemctl start vm-automation
sudo systemctl enable vm-automation
sudo systemctl status vm-automation
```

Configuration du service : `config/vm-automation.service`

## Verification

```bash
# Verifier l'API
curl http://localhost:8000/health

# Verifier les services Docker
docker compose ps

# Verifier Celery
celery -A src.workers.celery_app inspect ping
```

## Prochaines etapes

- [ARCHITECTURE.md](ARCHITECTURE.md) - Comprendre l'architecture
- [API_REFERENCE.md](API_REFERENCE.md) - Reference API
- [DEPLOYMENT_WORKFLOW.md](DEPLOYMENT_WORKFLOW.md) - Comprendre le flux de deploiement
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Resoudre les problemes
