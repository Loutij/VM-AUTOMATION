# VM Automation - Guide de Démarrage Rapide

## 1. Installation de Git

Git n'est pas détecté sur ce système. Installation requise :

### Option 1 : Téléchargement direct
1. Télécharger depuis https://git-scm.com/download/win
2. Exécuter l'installateur
3. Redémarrer le terminal/VSCode

### Option 2 : Via Chocolatey
```powershell
choco install git -y
```

### Option 3 : Via Winget
```powershell
winget install Git.Git
```

---

## 2. Initialisation du Repository

Une fois Git installé, exécuter dans le dossier du projet :

```powershell
# Naviguer vers le projet
cd "c:\Users\cma.ext\OneDrive - OTO Technology\Documents\CURSOR\2"

# Initialiser Git
git init

# Ajouter tous les fichiers
git add .

# Premier commit
git commit -m "feat: initialisation du projet VM Automation

- Structure de base du projet Python/FastAPI
- Documentation initiale (README, TASKS, PREREQUISITES, ARCHITECTURE)
- Configuration (.gitignore, requirements.txt, docker-compose.yml)
- Structure des dossiers (src/, templates/, scripts/, tests/, docs/)"
```

---

## 3. Création du Repository GitHub

```powershell
# Créer le repo sur GitHub (nécessite GitHub CLI)
gh repo create vm-automation --private --source=. --push

# OU manuellement :
# 1. Créer le repo sur github.com
# 2. Ajouter le remote
git remote add origin https://github.com/VOTRE-ORG/vm-automation.git

# 3. Pousser
git push -u origin main
```

---

## 4. Installation des Dépendances

### Backend (Python)

```powershell
# Créer l'environnement virtuel
python -m venv venv

# Activer l'environnement
.\venv\Scripts\Activate

# Installer les dépendances
pip install -r requirements.txt
```

### Services (Docker)

```powershell
# Lancer PostgreSQL et Redis
docker-compose up -d

# Vérifier les services
docker-compose ps
```

### Configuration

```powershell
# Copier le fichier de configuration
copy config\env.example .env

# Éditer les valeurs (notamment les credentials Hyper-V)
notepad .env
```

---

## 5. Vérification de l'Installation

```powershell
# Vérifier Python
python --version  # Doit être >= 3.11

# Vérifier les services Docker
docker-compose ps

# Tester la connexion DB
python -c "import asyncpg; print('asyncpg OK')"

# Tester la connexion Redis
python -c "import redis; r = redis.Redis(); r.ping(); print('Redis OK')"
```

---

## 6. Prochaines Étapes

1. **Configurer Hyper-V** : Voir `docs/PREREQUISITES.md`
2. **Lancer l'API** : `uvicorn src.api.main:app --reload`
3. **Consulter les tâches** : Voir `docs/TASKS.md`

---

## Troubleshooting

### Git non reconnu après installation
- Fermer et rouvrir le terminal/VSCode
- Vérifier que Git est dans le PATH : `$env:PATH -split ';' | Select-String git`

### Docker non disponible
- Installer Docker Desktop : https://www.docker.com/products/docker-desktop/
- Ou utiliser PostgreSQL/Redis installés localement

### Erreur de connexion Hyper-V
- Vérifier que WinRM est activé sur l'hôte Hyper-V
- Tester : `Test-WSMan -ComputerName <hyperv-host>`

---

*Document créé le 2026-01-26*
