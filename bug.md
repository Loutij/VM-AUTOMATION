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

*Rapport généré automatiquement par analyse statique du code source.*
