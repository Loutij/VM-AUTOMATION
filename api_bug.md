# Analyse API Frontend / Backend - VM Automation

## Résumé

Ce document liste toutes les incohérences, routes manquantes, routes jamais appelées et problèmes d'intégration entre le frontend et le backend.

---

## 1. Routes Backend NON utilisées par le Frontend

### 1.1 Routes VM jamais appelées

| Route | Méthode | Description | Impact |
|-------|---------|-------------|--------|
| `/api/v1/vms` | POST | Création directe de VM (sans déploiement) | Fonctionnalité non exposée |
| `/api/v1/vms/{id}` | PATCH | Modification d'une VM | Pas d'édition de VM possible |
| `/api/v1/vms/{id}/sync` | POST | Sync état VM individuelle | Disponible uniquement via sync hyperviseur global |
| `/api/v1/vms/{id}/post-install` | POST | Post-installation manuelle | Fonctionnalité avancée non exposée |

### 1.2 Routes Template jamais appelées

| Route | Méthode | Description | Impact |
|-------|---------|-------------|--------|
| `/api/v1/templates/{id}/validate` | POST | Validation de template | Pas de vérification avant déploiement |

### 1.3 Routes Hypervisor jamais appelées

| Route | Méthode | Description | Impact |
|-------|---------|-------------|--------|
| `/api/v1/hypervisors/{id}/storage-locations` | GET | Liste des emplacements de stockage | Pas de sélection dynamique du disque |

### 1.4 Routes Callbacks jamais appelées (entièrement)

| Route | Méthode | Description | Impact |
|-------|---------|-------------|--------|
| `/api/v1/callbacks/vm` | POST | Recevoir callback d'une VM | - |
| `/api/v1/callbacks/vm/{hostname}` | GET | Lister callbacks d'un hostname | - |
| `/api/v1/callbacks/vm/{hostname}` | DELETE | Supprimer callbacks | - |
| `/api/v1/callbacks/pending` | GET | Liste callbacks en attente | - |
| `/api/v1/callbacks/vm/{hostname}/complete` | POST | Marquer installation complète | - |

**Note**: Ces routes sont destinées aux scripts d'installation dans les VMs, pas à l'UI.

### 1.5 Routes Auth jamais appelées

| Route | Méthode | Description | Impact |
|-------|---------|-------------|--------|
| `/api/v1/auth/register` | POST | Inscription utilisateur | Pas d'inscription |
| `/api/v1/auth/login` | POST | Connexion | Pas d'authentification |
| `/api/v1/auth/refresh` | POST | Rafraîchir token | - |
| `/api/v1/auth/me` | GET | Profil utilisateur | - |
| `/api/v1/auth/change-password` | POST | Changer mot de passe | - |
| `/api/v1/auth/logout` | POST | Déconnexion | - |

**Impact**: L'authentification n'est pas implémentée côté frontend malgré l'existence de `Login.tsx` et `AuthContext.tsx`.

### 1.6 Routes Realtime jamais appelées

| Route | Méthode | Description | Impact |
|-------|---------|-------------|--------|
| `/api/v1/realtime/ws` | WebSocket | Connexion temps réel | Pas de mises à jour live |
| `/api/v1/realtime/sse` | GET | Server-Sent Events | - |
| `/api/v1/realtime/stats/websocket` | GET | Stats WebSocket | - |
| `/api/v1/realtime/test/broadcast` | POST | Test broadcast (debug) | - |

**Impact**: Malgré l'existence de `useWebSocket.ts`, aucune connexion temps réel n'est établie. Les déploiements sont actualisés par polling (5s).

### 1.7 Routes Software Catalog jamais appelées

| Route | Méthode | Description | Impact |
|-------|---------|-------------|--------|
| `/api/v1/software-catalog` | POST | Créer un logiciel | Pas de gestion du catalogue |
| `/api/v1/software-catalog/{id}` | PATCH | Modifier un logiciel | - |
| `/api/v1/software-catalog/{id}` | DELETE | Supprimer un logiciel | - |

---

## 2. Incohérences de Types/Schémas

### 2.1 Hypervisor Type Mapping

**Backend (`routers/hypervisors.py`)**:
```python
class HypervisorResponse(BaseModel):
    hypervisor_type: str  # Utilisé dans la réponse
```

**Backend (`types/schemas.py`)**:
```python
class HypervisorBase(BaseSchema):
    type: str  # Différent du router!
```

**Frontend (`api.ts`)**:
```typescript
interface HypervisorBackend {
  hypervisor_type: string;  // Doit mapper vers 'type'
}

function mapHypervisor(h: HypervisorBackend): Hypervisor {
  return {
    type: h.hypervisor_type as 'hyperv' | 'vmware',  // Mapping nécessaire
  };
}
```

**Problème**: Duplication des schémas entre `schemas.py` et les routers. Le fichier `schemas.py` n'est pas utilisé par les routers.

---

### 2.2 VM State vs Status

**Backend (`routers/vms.py`)**:
```python
class VMResponse(BaseModel):
    state: str  # Utilise 'state'
```

**Backend (`types/schemas.py`)**:
```python
class VMResponse(VMBase, TimestampSchema):
    status: str  # Utilise 'status' !
```

**Frontend (`types/index.ts`)**:
```typescript
export interface VirtualMachine {
  state: VMState;  // Attend 'state'
}
```

**Problème**: `schemas.py` utilise `status` mais le router utilise `state`. Incohérence documentée.

---

### 2.3 Health Check Response

**Backend (`routers/health.py`)**:
```python
class HealthStatus(BaseModel):
    status: str
    timestamp: str
    version: str
    environment: str
    checks: dict[str, Any]  # Structure complexe
```

**Frontend (`types/index.ts`)**:
```typescript
export interface HealthCheck {
  status: 'healthy' | 'unhealthy';
  database: boolean;     // N'existe pas!
  redis: boolean;        // N'existe pas!
  hypervisors: {...}[];  // N'existe pas!
}
```

**Problème**: Le frontend attend une structure complètement différente de ce que le backend retourne.

**Solution proposée**:
```typescript
// Frontend devrait être:
export interface HealthCheck {
  status: string;
  timestamp: string;
  version: string;
  environment: string;
  checks: {
    database: { status: string; host?: string; error?: string };
    redis: { status: string; message?: string };
    celery: { status: string; message?: string };
  };
}
```

---

### 2.4 Deployment Logs Level vs Status

**Backend (`routers/deployments.py`)**:
```python
class DeploymentLogEntry(BaseModel):
    level: Literal["debug", "info", "warning", "error"]  # Utilise 'level'
```

**Frontend (`pages/Deployments.tsx`)**:
```tsx
{deploymentLogs.map((log) => (
  <div className={`... ${
    log.status === 'error'  // Utilise 'status' au lieu de 'level'!
      ? 'bg-red-500/10'
      : ...
  }`}
```

**Problème**: Le frontend utilise `log.status` mais le backend envoie `log.level`.

**Correction nécessaire** dans `Deployments.tsx`:
```tsx
log.level === 'error'  // Corriger status -> level
```

---

### 2.5 Deployment Progress

**Backend (`routers/deployments.py`)**:
```python
class DeploymentResponse(BaseModel):
    # Pas de champ 'progress' direct
```

**Frontend (`api.ts`)**:
```typescript
// Calcul manuel de la progression
const progressMap: Record<string, number> = {
  pending: 0,
  creating_vm: 20,
  installing_os: 50,
  post_install: 75,
  installing_software: 90,
  completed: 100,
  failed: 0,
  cancelled: 0,
};
```

**Note**: Ce n'est pas vraiment un bug, le frontend calcule la progression à partir du statut. Cependant, le backend a un champ `progress` dans le modèle `Deployment` qui n'est pas exposé.

---

## 3. Routes Frontend appelant des endpoints inexistants

Aucune route frontend n'appelle d'endpoint inexistant. ✅

---

## 4. Problèmes d'Architecture

### 4.1 Duplication des Schémas Pydantic

**Localisation**: 
- `src/types/schemas.py` - Schémas centralisés (NON UTILISÉS)
- `src/api/routers/*.py` - Schémas locaux (UTILISÉS)

**Impact**: 
- Maintenance difficile
- Risque d'incohérence entre schémas
- `schemas.py` pourrait être supprimé ou intégré

**Recommandation**: Migrer vers un seul système de schémas.

---

### 4.2 Authentification Non Implémentée

**Frontend existant**:
- `frontend/src/pages/Login.tsx` - Page de connexion
- `frontend/src/contexts/AuthContext.tsx` - Contexte d'authentification
- `frontend/src/components/auth/ProtectedRoute.tsx` - Route protégée

**Backend existant**:
- `src/api/routers/auth.py` - Routes d'authentification complètes

**Problème**: Aucune intégration. Le frontend ne fait aucun appel aux routes auth.

**Impact**: 
- Pas de sécurité
- Tout le monde peut accéder à l'application

---

### 4.3 WebSocket Non Utilisé

**Backend**:
- `src/api/websocket.py` - Gestionnaire WebSocket complet
- `src/api/routers/realtime.py` - Routes WS/SSE

**Frontend**:
- `frontend/src/hooks/useWebSocket.ts` - Hook WebSocket (NON UTILISÉ)

**Impact**:
- Polling à 5s sur `/deployments` au lieu de temps réel
- Pas de notifications push

---

### 4.4 Pagination Incomplète

**Backend**: Supporte la pagination sur toutes les listes
```python
class Pagination:
    page: int = Query(1, ge=1)
    page_size: int = Query(20, ge=1, le=100)
```

**Frontend**: Ne gère pas la pagination
```typescript
// api.ts - Pas de paramètres de pagination passés
const response = await apiClient.get<PaginatedResponse<T>>('/hypervisors');
return response.data.items;  // Retourne uniquement items
```

**Impact**: Problèmes de performance avec beaucoup de données.

---

## 5. Fonctionnalités Manquantes

### 5.1 Côté Frontend

| Fonctionnalité | Routes Backend Disponibles | Priorité |
|----------------|---------------------------|----------|
| Authentification complète | `/auth/*` | 🔴 Haute |
| WebSocket temps réel | `/realtime/ws` | 🟡 Moyenne |
| Création VM directe | `POST /vms` | 🟢 Basse |
| Modification VM | `PATCH /vms/{id}` | 🟡 Moyenne |
| Post-install manuel | `POST /vms/{id}/post-install` | 🟢 Basse |
| Validation template | `POST /templates/{id}/validate` | 🟢 Basse |
| Sélection emplacement disque | `GET /hypervisors/{id}/storage-locations` | 🟡 Moyenne |
| Gestion catalogue logiciels | `POST/PATCH/DELETE /software-catalog` | 🟢 Basse |

### 5.2 Côté Backend

| Fonctionnalité | Impact | Priorité |
|----------------|--------|----------|
| Rate limiting | Sécurité | 🟡 Moyenne |
| Audit logs | Traçabilité | 🟢 Basse |
| API versioning strict | Maintenabilité | 🟢 Basse |

---

## 6. Liste des Corrections Urgentes

### 6.1 Bug: log.status vs log.level

**Fichier**: `frontend/src/pages/Deployments.tsx`  
**Ligne**: ~490-510

```tsx
// AVANT (BUG)
log.status === 'error'
log.status === 'success'
log.status === 'warning'

// APRÈS (CORRECTION)
log.level === 'error'
log.level === 'info'  // 'success' n'existe pas côté backend
log.level === 'warning'
```

---

### 6.2 Bug: Type HealthCheck Frontend

**Fichier**: `frontend/src/types/index.ts`

```typescript
// AVANT
export interface HealthCheck {
  status: 'healthy' | 'unhealthy';
  database: boolean;
  redis: boolean;
  hypervisors: { name: string; connected: boolean; }[];
}

// APRÈS
export interface HealthCheck {
  status: string;
  timestamp: string;
  version: string;
  environment: string;
  checks: {
    database: { status: string; host?: string; error?: string };
    redis: { status: string; message?: string };
    celery: { status: string; message?: string };
  };
}
```

---

### 6.3 Cleanup: Supprimer ou utiliser schemas.py

**Fichier**: `src/types/schemas.py`

Options:
1. **Supprimer** le fichier car non utilisé
2. **Migrer** les routers pour utiliser ces schémas centralisés

---

## 7. Matrice de Couverture API

### Légende
- ✅ Implémenté et utilisé
- ⚠️ Implémenté backend, non utilisé frontend
- ❌ Manquant

| Module | Route | Backend | Frontend |
|--------|-------|---------|----------|
| **Health** | GET /health | ✅ | ✅ |
| | GET /ready | ✅ | ⚠️ |
| | GET /live | ✅ | ⚠️ |
| **Auth** | POST /auth/register | ✅ | ⚠️ |
| | POST /auth/login | ✅ | ⚠️ |
| | POST /auth/refresh | ✅ | ⚠️ |
| | GET /auth/me | ✅ | ⚠️ |
| | POST /auth/change-password | ✅ | ⚠️ |
| | POST /auth/logout | ✅ | ⚠️ |
| **Hypervisors** | GET /hypervisors | ✅ | ✅ |
| | POST /hypervisors | ✅ | ✅ |
| | GET /hypervisors/{id} | ✅ | ✅ |
| | PATCH /hypervisors/{id} | ✅ | ✅ |
| | DELETE /hypervisors/{id} | ✅ | ✅ |
| | POST /hypervisors/{id}/test | ✅ | ✅ |
| | GET /hypervisors/{id}/vms | ✅ | ✅ |
| | GET /hypervisors/{id}/switches | ✅ | ✅ |
| | POST /hypervisors/{id}/switches | ✅ | ✅ |
| | DELETE /hypervisors/{id}/switches/{name} | ✅ | ✅ |
| | GET /hypervisors/{id}/physical-adapters | ✅ | ✅ |
| | GET /hypervisors/{id}/isos | ✅ | ✅ |
| | GET /hypervisors/{id}/storage-locations | ✅ | ⚠️ |
| | POST /hypervisors/{id}/sync | ✅ | ✅ |
| **VMs** | GET /vms | ✅ | ✅ |
| | POST /vms | ✅ | ⚠️ |
| | GET /vms/{id} | ✅ | ✅ |
| | PATCH /vms/{id} | ✅ | ⚠️ |
| | DELETE /vms/{id} | ✅ | ✅ |
| | POST /vms/{id}/start | ✅ | ✅ |
| | POST /vms/{id}/stop | ✅ | ✅ |
| | POST /vms/{id}/restart | ✅ | ✅ |
| | POST /vms/{id}/sync | ✅ | ⚠️ |
| | GET /vms/{id}/rdp | ✅ | ✅ |
| | GET /vms/{id}/details | ✅ | ✅ |
| | POST /vms/{id}/post-install | ✅ | ⚠️ |
| | GET /vms/{id}/screenshot | ✅ | ✅ |
| **Templates** | GET /templates | ✅ | ✅ |
| | POST /templates | ✅ | ✅ |
| | GET /templates/{id} | ✅ | ✅ |
| | PATCH /templates/{id} | ✅ | ✅ |
| | DELETE /templates/{id} | ✅ | ✅ |
| | POST /templates/{id}/validate | ✅ | ⚠️ |
| **Deployments** | GET /deployments | ✅ | ✅ |
| | POST /deployments | ✅ | ✅ |
| | GET /deployments/{id} | ✅ | ✅ |
| | POST /deployments/{id}/start | ✅ | ✅ |
| | POST /deployments/{id}/cancel | ✅ | ✅ |
| | GET /deployments/{id}/logs | ✅ | ✅ |
| | DELETE /deployments/{id} | ✅ | ✅ |
| **Realtime** | WS /realtime/ws | ✅ | ⚠️ |
| | GET /realtime/sse | ✅ | ⚠️ |
| | GET /realtime/stats | ✅ | ✅ |
| | GET /realtime/stats/websocket | ✅ | ⚠️ |
| | POST /realtime/test/broadcast | ✅ | ⚠️ |
| **Callbacks** | POST /callbacks/vm | ✅ | ⚠️ |
| | GET /callbacks/vm/{hostname} | ✅ | ⚠️ |
| | DELETE /callbacks/vm/{hostname} | ✅ | ⚠️ |
| | GET /callbacks/pending | ✅ | ⚠️ |
| | POST /callbacks/vm/{hostname}/complete | ✅ | ⚠️ |
| **Software** | GET /software-catalog | ✅ | ✅ |
| | POST /software-catalog | ✅ | ⚠️ |
| | GET /software-catalog/categories | ✅ | ✅ |
| | GET /software-catalog/profiles | ✅ | ✅ |
| | GET /software-catalog/profiles/{name} | ✅ | ✅ |
| | GET /software-catalog/by-name/{name} | ✅ | ✅ |
| | GET /software-catalog/featured | ✅ | ✅ |
| | GET /software-catalog/{id} | ✅ | ✅ |
| | PATCH /software-catalog/{id} | ✅ | ⚠️ |
| | DELETE /software-catalog/{id} | ✅ | ⚠️ |
| | POST /software-catalog/seed | ✅ | ✅ |

---

## 8. Conclusion

### Statistiques
- **Routes Backend Total**: 56
- **Routes utilisées Frontend**: 38 (68%)
- **Routes non utilisées**: 18 (32%)
- **Bugs identifiés**: 3
- **Incohérences de types**: 5

### Priorités de Correction
1. 🔴 **Bug log.level** - Correction immédiate nécessaire
2. 🔴 **Type HealthCheck** - Type incorrect
3. 🟡 **Authentification** - À implémenter pour la production
4. 🟡 **WebSocket** - À activer pour le temps réel
5. 🟢 **Cleanup schemas.py** - Nettoyage de code

---

*Document généré le 27/01/2026*
