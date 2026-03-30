# VM Automation - Variables d'Environnement

Fichier de reference : `config/env.example`
Fichier a creer : `.env` (a la racine du projet)

## Application

| Variable | Description | Defaut |
|----------|-------------|--------|
| `APP_NAME` | Nom de l'application | `vm-automation` |
| `APP_ENV` | Environnement (development/production) | `development` |
| `DEBUG` | Mode debug (logs detailles) | `true` |
| `LOG_LEVEL` | Niveau de log (DEBUG, INFO, WARNING, ERROR) | `INFO` |

## API

| Variable | Description | Defaut |
|----------|-------------|--------|
| `API_HOST` | Adresse d'ecoute de l'API | `0.0.0.0` |
| `API_PORT` | Port de l'API | `8000` |
| `API_SECRET_KEY` | Cle secrete JWT (changer en production !) | `your-super-secret-key-change-in-production` |
| `API_ALGORITHM` | Algorithme JWT | `HS256` |
| `API_ACCESS_TOKEN_EXPIRE_MINUTES` | Duree de vie du token (minutes) | `30` |
| `CORS_ORIGINS` | Origines CORS autorisees (separees par virgules) | `http://localhost:3000,http://localhost:5173` |

## Base de donnees (PostgreSQL)

| Variable | Description | Defaut |
|----------|-------------|--------|
| `DB_HOST` | Hote PostgreSQL | `localhost` |
| `DB_PORT` | Port PostgreSQL | `5432` |
| `DB_NAME` | Nom de la base | `vmautomation` |
| `DB_USER` | Utilisateur DB | `vmautomation` |
| `DB_PASSWORD` | Mot de passe DB | (obligatoire) |

## Redis

| Variable | Description | Defaut |
|----------|-------------|--------|
| `REDIS_HOST` | Hote Redis | `localhost` |
| `REDIS_PORT` | Port Redis | `6379` |
| `REDIS_PASSWORD` | Mot de passe Redis (vide si non protege) | (vide) |
| `REDIS_DB` | Numero de la base Redis | `0` |
| `REDIS_URL` | URL complete Redis | `redis://localhost:6379/0` |

## Celery

| Variable | Description | Defaut |
|----------|-------------|--------|
| `CELERY_BROKER_URL` | URL du broker Celery (Redis DB 0) | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Backend de resultats (Redis DB 1) | `redis://localhost:6379/1` |

## Hyper-V

| Variable | Description | Defaut |
|----------|-------------|--------|
| `HYPERV_HOST` | Hote Hyper-V (FQDN ou IP) | (obligatoire) |
| `HYPERV_USER` | Utilisateur WinRM (DOMAIN\\user) | (obligatoire) |
| `HYPERV_PASSWORD` | Mot de passe WinRM | (obligatoire) |
| `HYPERV_USE_SSL` | Utiliser HTTPS pour WinRM (port 5986) | `true` |
| `HYPERV_VM_PATH` | Chemin des configurations VMs sur l'hote | `D:\HyperV\VirtualMachines` |
| `HYPERV_VHDX_PATH` | Chemin des disques VHDX | `D:\HyperV\VirtualHardDisks` |
| `HYPERV_ISO_PATH` | Chemin des ISOs | `D:\HyperV\ISOs` |
| `HYPERV_TEMP_PATH` | Chemin temporaire (ISOs OEMDRV, etc.) | `D:\HyperV\Temp` |
| `HYPERV_UNATTEND_PATH` | Chemin des fichiers unattend generes | `D:\HyperV\Unattend` |
| `HYPERV_DEFAULT_SWITCH` | Virtual switch par defaut | `External-Switch` |

## Active Directory (optionnel)

| Variable | Description | Defaut |
|----------|-------------|--------|
| `AD_ENABLED` | Activer la jointure domaine | `false` |
| `AD_DOMAIN` | Nom du domaine AD | (optionnel) |
| `AD_USER` | Compte AD pour jointure (DOMAIN\\user) | (optionnel) |
| `AD_PASSWORD` | Mot de passe du compte AD | (optionnel) |
| `AD_DEFAULT_OU` | OU par defaut pour les VMs | (optionnel) |
| `AD_DNS_SERVER` | Serveur DNS du domaine | (optionnel) |

## Installation OS

| Variable | Description | Defaut |
|----------|-------------|--------|
| `DEFAULT_ADMIN_PASSWORD` | Mot de passe admin par defaut des VMs | `TempP@ss123!` |
| `DEFAULT_TIMEZONE` | Fuseau horaire | `Europe/Paris` |
| `DEFAULT_LOCALE` | Locale d'installation | `fr-FR` |

## Performance

| Variable | Description | Defaut |
|----------|-------------|--------|
| `MAX_CONCURRENT_DEPLOYMENTS` | Nombre max de deploiements simultanes | `5` |
| `VM_CREATION_TIMEOUT` | Timeout creation VM (secondes) | `300` |
| `OS_INSTALL_TIMEOUT` | Timeout installation OS (secondes) | `3600` |
| `POST_INSTALL_TIMEOUT` | Timeout post-installation (secondes) | `1800` |

## Email SMTP (optionnel)

| Variable | Description | Defaut |
|----------|-------------|--------|
| `SMTP_HOST` | Serveur SMTP | (optionnel) |
| `SMTP_PORT` | Port SMTP | `465` |
| `SMTP_SSL` | Utiliser SSL | `true` |
| `SMTP_USER` | Utilisateur SMTP | (optionnel) |
| `SMTP_PASSWORD` | Mot de passe SMTP | (optionnel) |
| `SMTP_FROM` | Adresse expediteur | (optionnel) |
| `SMTP_ENABLED` | Activer les notifications email | `false` |

## Securite

| Variable | Description | Defaut |
|----------|-------------|--------|
| `ENCRYPTION_KEY` | Cle Fernet pour chiffrement credentials hyperviseurs | Auto-generee si absente |

> **Important** : En production, definir `ENCRYPTION_KEY` explicitement pour conserver les credentials chiffres apres un redemarrage.

## Monitoring

| Variable | Description | Defaut |
|----------|-------------|--------|
| `FLOWER_PASSWORD` | Mot de passe du dashboard Flower (monitoring Celery) | `changeme` |

> Flower est accessible sur `http://localhost:5555`.
