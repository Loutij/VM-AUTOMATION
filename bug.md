# VM Automation - Rapport de Bugs et Incohérences

Document généré le 27 janvier 2026 après analyse exhaustive du code source.

---

## Table des matières

1. [Bugs Critiques](#bugs-critiques)
2. [Incohérences de Migrations Alembic](#incohérences-de-migrations-alembic)
3. [Incohérences Types Frontend/Backend](#incohérences-types-frontendbackend)
4. [Problèmes de Code](#problèmes-de-code)
5. [Duplications et Dette Technique](#duplications-et-dette-technique)
6. [Améliorations Suggérées](#améliorations-suggérées)

---

## Bugs Critiques

### 1. VMState Enum - Casse Incohérente 🔴

**Fichiers concernés:**
- `alembic/versions/889a3e192265_add_state_column_to_vm.py`
- `src/domain/models.py`

**Problème:**
La migration crée l'enum avec des valeurs en MAJUSCULES tandis que le modèle Python attend des minuscules.

**Migration (ligne 23):**
```python
vmstate_enum = sa.Enum('RUNNING', 'STOPPED', 'PAUSED', 'SUSPENDED', 'UNKNOWN', name='vmstate')
```

**Modèle (ligne 79-86):**
```python
class VMState(str, enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    SUSPENDED = "saved"
    UNKNOWN = "unknown"
```

**Impact:** PostgreSQL stockera `'RUNNING'` mais SQLAlchemy s'attend à `'running'`. Erreurs lors de la lecture des VMs depuis la base.

**Correction suggérée:**
```python
# Migration devrait utiliser les valeurs minuscules
vmstate_enum = sa.Enum('running', 'stopped', 'paused', 'saved', 'unknown', name='vmstate')
```

---

### 2. DeploymentStatus Enum - Valeurs Différentes 🔴

**Fichiers concernés:**
- `alembic/versions/001_initial_schema.py`
- `src/domain/models.py`

**Problème:**
Les valeurs de l'enum dans la migration initiale ne correspondent pas aux valeurs du modèle Python.

**Migration 001 (ligne 98):**
```python
'pending', 'vm_creating', 'os_installing', 'post_configuring', 'software_installing', 'completed', 'failed', 'cancelled'
```

**Modèle Python (ligne 89-100):**
```python
PENDING = "pending"
IN_PROGRESS = "in_progress"
CREATING_VM = "creating_vm"
INSTALLING = "installing_os"
POST_INSTALL = "post_install"
INSTALLING_SOFTWARE = "installing_software"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
```

**Différences:**
| Migration | Modèle |
|-----------|--------|
| `vm_creating` | `creating_vm` |
| `os_installing` | `installing_os` |
| `post_configuring` | `post_install` |
| (absent) | `in_progress` |

**Impact:** Les déploiements ne peuvent pas utiliser les bons statuts. La migration 002 ajoute partiellement les nouvelles valeurs mais le problème de base persiste.

---

### 3. SoftwareCategory Enum - Catégories Manquantes 🔴

**Fichiers concernés:**
- `alembic/versions/003_software_marketplace.py`
- `alembic/versions/004_extend_software_categories.py`
- `src/domain/models.py`

**Problème:**
L'enum dans la migration 003 utilise `networking` au lieu de `network`, et manque plusieurs catégories.

**Migration 003 (ligne 23-27):**
```python
'utilities', 'development', 'database', 'webserver', 
'monitoring', 'security', 'networking', 'office', 
'media', 'runtime', 'other'
```

**Modèle Python:**
```python
WINDOWS_ROLE = "windows_role"
REMOTE_ACCESS = "remote_access"
DATABASE = "database"
WEBSERVER = "webserver"
DEVELOPMENT = "development"
RUNTIME = "runtime"
MONITORING = "monitoring"
SECURITY = "security"
UTILITIES = "utilities"
BROWSER = "browser"
CONTAINERS = "containers"
FILE_TRANSFER = "file_transfer"
NETWORK = "network"  # PAS 'networking'
BACKUP = "backup"
OTHER = "other"
```

**Valeurs conflictuelles:**
- Migration utilise `networking` → Modèle utilise `network`
- Migration inclut `office`, `media` → Absents du modèle
- Migration manque `browser`, `containers`, `file_transfer`, `backup`, `windows_role`, `remote_access`

**Note:** Migration 004 ajoute les valeurs manquantes mais ne corrige pas `networking` → `network`.

---

### 4. DeploymentLog Level Mapping Incorrect 🟡

**Fichiers concernés:**
- `frontend/src/types/index.ts`
- `src/domain/models.py`
- `src/api/routers/deployments.py`

**Problème:**
Le frontend attend des valeurs de statut différentes du backend.

**Frontend (ligne 145):**
```typescript
status: 'info' | 'success' | 'warning' | 'error';
```

**Backend LogLevel enum:**
```python
DEBUG = "debug"
INFO = "info"
WARNING = "warning"
ERROR = "error"
```

**Incohérences:**
- Frontend a `success` → Backend n'a pas cette valeur
- Backend a `debug` → Frontend n'attend pas cette valeur

**Impact:** Le mapping dans `api.ts` (ligne 546) convertit `level` en `status` mais ne gère pas `debug` et ne peut pas produire `success`.

---

## Incohérences de Migrations Alembic

### 5. Nommage des Fichiers de Migration Incohérent 🟡

**Structure actuelle:**
```
001_initial_schema.py                    # Format: 001_nom
889a3e192265_add_state_column_to_vm.py   # Format: hash_nom
002_update_deployment_model.py           # Format: 002_nom
003_software_marketplace.py              # Format: 003_nom
004_extend_software_categories.py        # Format: 004_nom
```

**Problème:** Mélange de conventions de nommage (numérotation séquentielle vs hash Alembic).

---

### 6. Chaîne de Down Revision 🟡

**Fichiers:**
- `001_initial_schema.py`: `down_revision = None`
- `889a3e192265_add_state_column_to_vm.py`: `down_revision = '001'`
- `002_update_deployment_model.py`: `down_revision = '889a3e192265'`
- `003_software_marketplace.py`: `down_revision = '002_update_deployment_model'`
- `004_extend_software_categories.py`: `down_revision = '003_software_marketplace'`

**Problème:** 
- Les fichiers 003 et 004 référencent les noms complets au lieu des revision IDs
- Le fichier 002 a `revision: str = '002_update_deployment'` mais le fichier se nomme `002_update_deployment_model.py`

**Impact potentiel:** Alembic pourrait avoir des difficultés à résoudre la chaîne de migrations.

---

### 7. Colonne `hyperv_id` vs `hypervisor_vm_id` 🟡

**Fichiers:**
- `alembic/versions/001_initial_schema.py` (ligne 81): Crée `hyperv_id`
- `alembic/versions/889a3e192265_add_state_column_to_vm.py` (ligne 28): Crée `hypervisor_vm_id`
- `src/domain/models.py` (ligne 273): Définit `hypervisor_vm_id`

**Problème:** La migration 001 crée une colonne `hyperv_id`, puis la migration 889 crée `hypervisor_vm_id` et tente de renommer l'ancienne. Cela peut échouer si la migration 001 a déjà été appliquée.

---

## Incohérences Types Frontend/Backend

### 8. OSTemplate - `os_version` vs `os_type` 🟡

**Frontend (`frontend/src/types/index.ts`, ligne 120):**
```typescript
os_version: string;
```

**Backend (modèle et réponse API):**
```python
os_type: str
```

**Mapper (`frontend/src/services/api.ts`, ligne 367):**
```typescript
os_version: t.os_type,
```

**Impact:** Le mapper corrige le problème mais crée de la confusion. Les noms devraient être alignés.

---

### 9. VirtualMachine - `memory_mb` vs `ram_gb` 🟡

**Frontend (`frontend/src/types/index.ts`, ligne 24):**
```typescript
memory_mb: number;
```

**Backend:**
```python
ram_gb: Mapped[int]
```

**Mapper (`frontend/src/services/api.ts`, ligne 273):**
```typescript
memory_mb: vm.ram_gb * 1024,
```

**Impact:** Conversion implicite dans le mapper. Risque d'erreurs si quelqu'un envoie des MB au backend qui attend des GB.

---

### 10. Deployment - `template_id` vs `os_template_id` 🟡

**Frontend (`frontend/src/types/index.ts`, ligne 154):**
```typescript
template_id: string;
```

**Backend (`src/api/routers/deployments.py`, ligne 72):**
```python
template_id: UUID  # mais le modèle a os_template_id
```

**Impact:** Le schéma API utilise `template_id` mais le modèle SQLAlchemy utilise `os_template_id`. Incohérence de nommage.

---

## Problèmes de Code

### 11. React useEffect - Dépendance Manquante 🟡

**Fichier:** `frontend/src/pages/NewDeployment.tsx` (ligne 206-209)

```typescript
useEffect(() => {
  if (switches.length > 0 && !formData.network_switch) {
    setFormData((prev) => ({ ...prev, network_switch: switches[0].name }));
  }
}, [switches]);  // ⚠️ formData.network_switch manque dans les dépendances
```

**Impact:** Le linter React (eslint-plugin-react-hooks) devrait signaler ce warning. Peut causer des comportements inattendus.

---

### 12. DeploymentLogEntry.level Type Mismatch 🟡

**Fichier:** `src/api/routers/deployments.py`

**Schéma (ligne 132):**
```python
level: str
```

**Usage (ligne 435):**
```python
level=log.level,  # log.level est un enum LogLevel, pas une string
```

**Impact:** Pydantic devrait convertir automatiquement, mais c'est une incohérence de typage.

---

### 13. CATEGORY_INFO Manque la Catégorie 'other' 🟡

**Fichier:** `src/domain/software_catalog.py`

Le dictionnaire `CATEGORY_INFO` (ligne 1614-1699) ne contient pas d'entrée pour `'other'` alors que `SoftwareCategory.OTHER` existe dans l'enum.

**Impact:** La fonction `list_categories` peut retourner une catégorie sans informations.

---

### 14. Templates Router - Type `str` au lieu de `datetime` 🟡

**Fichier:** `src/api/routers/templates.py` (ligne 67-68)

```python
class OSTemplateResponse(OSTemplateBase):
    ...
    created_at: str
    updated_at: str | None
```

**Problème:** Les timestamps sont définis comme `str` au lieu de `datetime`. La conversion est faite manuellement dans `_template_to_response`.

**Impact:** Perte de la validation Pydantic pour les dates. Risque de formats incohérents.

---

## Duplications et Dette Technique

### 15. Schemas Dupliqués 🟡

**Problème:** Les schémas Pydantic sont définis dans deux endroits :
1. `src/types/schemas.py` - Fichier centralisé
2. Chaque router (`deployments.py`, `vms.py`, `templates.py`, `software_catalog.py`)

**Impact:**
- Duplication de code
- Risque d'incohérences entre les définitions
- Maintenance difficile

**Recommandation:** Utiliser uniquement `schemas.py` et l'importer dans les routers.

---

### 16. Import Inutilisé dans VMs Router 🟡

**Fichier:** `src/api/routers/vms.py` (ligne 7)

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
```

`Depends` est importé mais jamais utilisé directement dans le fichier.

---

### 17. Progress Field Non Utilisé 🟡

**Fichier:** `src/domain/models.py` (ligne 345)

```python
progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

**Problème:** Le modèle `Deployment` a un champ `progress` mais le frontend calcule la progression basée sur le statut (`api.ts` ligne 443-452).

**Impact:** Double gestion de la progression, source potentielle de désynchronisation.

---

## Améliorations Suggérées

### 18. Ajouter des Tests de Migration

Créer des tests qui vérifient la cohérence entre :
- Les enums dans les migrations
- Les enums dans les modèles Python

### 19. Uniformiser les Noms de Colonnes

Établir une convention et s'y tenir :
- `template_id` OU `os_template_id` (pas les deux)
- `hyperv_id` OU `hypervisor_vm_id` (pas les deux)

### 20. Valider les Enums Côté Frontend

Utiliser des enums TypeScript stricts qui correspondent aux valeurs backend :

```typescript
// Au lieu de string literals
export enum DeploymentStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  // ...
}
```

### 21. Ajouter des Scripts de Validation

Créer un script qui vérifie automatiquement :
- La cohérence des enums migrations/modèles
- La présence de toutes les entrées dans CATEGORY_INFO
- Les dépendances React

---

## Résumé

| Priorité | Nombre | Description |
|----------|--------|-------------|
| 🔴 Critique | 4 | Bugs qui causent des erreurs runtime |
| 🟡 Modérée | 13 | Incohérences qui peuvent causer des bugs |
| Total | 17 | Problèmes identifiés |

### Actions Prioritaires

1. **Corriger les enums dans les migrations** - VMState, DeploymentStatus, SoftwareCategory
2. **Aligner frontend/backend types** - Supprimer les conversions dans les mappers
3. **Centraliser les schémas Pydantic** - Éviter la duplication
4. **Ajouter la catégorie 'other'** dans CATEGORY_INFO
5. **Uniformiser le nommage des colonnes**

---

## Incohérences Système (Runtime)

> Analyse effectuée le 27 janvier 2026 sur l'environnement de production.

### 22. VHD Orphelins sur Hyper-V 🔴

**Localisation:** `C:\HyperV\VirtualHardDisks\`

Les fichiers VHDX suivants ne sont attachés à aucune VM active :

| Fichier | Taille | Dernière modification |
|---------|--------|----------------------|
| `NOUVELLE_VM_DE_PRODbb.vhdx` | 8.57 GB | 27/01/2026 |
| `NOUVELLE_VM_DE_PROD_aaaa.vhdx` | 0.19 GB | 27/01/2026 |
| `NOUVELLE_VM_DE_PROD_ABC.vhdx` | 0.19 GB | 27/01/2026 |

**Impact:** Espace disque gaspillé (~9 GB). Ces VHD proviennent probablement de déploiements échoués ou de VMs supprimées manuellement.

**Action suggérée:** Supprimer ces fichiers après confirmation qu'ils ne sont pas nécessaires.

---

### 23. Dossiers de Configuration VM Orphelins 🔴

**Localisation:** `C:\HyperV\VirtualMachines\`

**27 dossiers trouvés**, mais seulement **3 VMs actives** sur Hyper-V :

**VMs actives :**
- `CM_NEW_VM`
- `TEST_DISM_WEB`
- `VM_LAB_08`

**Dossiers orphelins (24) :**
```
CMA, CMA_2, CMA_32
NOUVELLE_VM_DE_PROD, NOUVELLE_VM_DE_PROD00, NOUVELLE_VM_DE_PRODbb
NOUVELLE_VM_DE_PROD_2, NOUVELLE_VM_DE_PROD_3, NOUVELLE_VM_DE_PROD_5
NOUVELLE_VM_DE_PROD_aaaa, NOUVELLE_VM_DE_PROD_ABC
TEST_DISM_AUTO
VM_02, VM_02_LAB, VM_03
VM_CMA, VM_LAB_CM, VM_LAB_CMA
VM_LAB_03, VM_LAB_04, VM_LAB_05, VM_LAB_06, VM_LAB_07, VM_LAB_09, VM_LAB_10
```

**Impact:** Fichiers de configuration, snapshots et métadonnées inutiles occupant de l'espace disque.

---

### 24. VM "A" Fantôme dans la Base de Données 🔴

**Table:** `virtual_machines`

```sql
id: 2be11b78-48aa-486e-8595-d6cedcd6332e
name: A
status: deleted
state: unknown
hypervisor_vm_id: a37126ef-abc6-42bc-aafa-2ea27c5e5730
```

**Problème:** Cette VM a un `hypervisor_vm_id` enregistré mais **n'existe pas sur Hyper-V**. Le statut est `deleted` mais l'entrée persiste en base.

**Impact:** Données obsolètes qui peuvent fausser les statistiques et causer des erreurs si on tente d'interagir avec cette VM.

**Action suggérée:** Supprimer cette entrée de la base ou ajouter un mécanisme de nettoyage automatique.

---

### 25. VMs sans Déploiement Associé 🟡

**Table:** `virtual_machines` LEFT JOIN `deployments`

Les VMs suivantes existent en base mais n'ont pas de déploiement associé :

| VM | Status | State | Créée le |
|----|--------|-------|----------|
| `A` | deleted | unknown | 27/01/2026 15:28 |
| `VM_LAB_08` | created | stopped | 27/01/2026 12:01 |
| `TEST_DISM_WEB` | creating | running | 27/01/2026 13:27 |

**Problème:** Ces VMs ont été créées mais leur déploiement n'a pas été correctement enregistré ou a été supprimé.

---

### 26. Statut VM Incohérent 🟡

**Table:** `virtual_machines`

| VM | Status DB | State DB | État réel Hyper-V |
|----|-----------|----------|-------------------|
| `CM_NEW_VM` | `creating` | `running` | Running ✓ |
| `TEST_DISM_WEB` | `creating` | `running` | Running ✓ |
| `VM_LAB_08` | `created` | `stopped` | Off ✓ |

**Problème:** 
- `CM_NEW_VM` et `TEST_DISM_WEB` ont `status=creating` alors qu'elles sont complètement opérationnelles
- Le statut `creating` devrait être transitoire, pas permanent
- Le statut `created` n'existe pas dans l'enum `VMStatus` du modèle Python

**Impact:** Le frontend affiche des états incorrects pour ces VMs.

---

### 27. Catalogue Software Vide 🟡

**Table:** `software_packages`

```sql
SELECT COUNT(*) FROM software_packages;
-- Résultat: 0 lignes
```

**Problème:** Le catalogue de logiciels est vide alors que :
1. Le code contient 100+ packages dans `src/domain/software_catalog.py`
2. Le frontend Marketplace s'attend à afficher des logiciels
3. L'endpoint `/api/software/seed` existe pour peupler le catalogue

**Impact:** La fonctionnalité Marketplace est inutilisable sans seed initial.

**Action suggérée:** Appeler `POST /api/software/seed` ou exécuter le seed automatiquement au démarrage.

---

### 28. Type de Colonne `category` Incorrect 🟡

**Table:** `software_packages`

**État actuel:**
```sql
category | character varying(50) | NOT NULL | DEFAULT 'other'
```

**Attendu (selon migration 003):**
```sql
category | softwarecategory (ENUM) | NOT NULL
```

**Problème:** La colonne `category` utilise `varchar(50)` au lieu de l'enum `softwarecategory`. La migration 003 prévoyait de convertir cette colonne mais cela ne semble pas avoir été appliqué.

---

### 29. Un Seul Template OS Disponible 🟡

**Table:** `os_templates`

```sql
SELECT * FROM os_templates;
-- 1 seul résultat: Windows_Server_2022
```

**Impact:** Le système ne peut déployer qu'un seul type d'OS. Il manque :
- Windows 10/11
- Windows Server 2019
- Templates Linux (Ubuntu, Debian, Rocky)

---

## Résumé Mis à Jour

| Priorité | Nombre | Description |
|----------|--------|-------------|
| 🔴 Critique (Code) | 4 | Bugs qui causent des erreurs runtime |
| 🔴 Critique (Système) | 4 | Ressources orphelines, données fantômes |
| 🟡 Modérée (Code) | 13 | Incohérences code source |
| 🟡 Modérée (Système) | 5 | Incohérences données/état |
| **Total** | **26** | Problèmes identifiés |

### Actions Prioritaires Système

1. **Nettoyer les VHD orphelins** - Libérer ~9 GB d'espace disque
2. **Supprimer les dossiers VM orphelins** - 24 dossiers à nettoyer
3. **Corriger les statuts VM** - Synchroniser DB avec état Hyper-V réel
4. **Seed le catalogue software** - `POST /api/software/seed`
5. **Ajouter des templates OS** - Activer le déploiement multi-OS

---

*Rapport généré automatiquement par analyse statique du code source et inspection runtime du système.*
