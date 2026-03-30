# VM Automation - Frontend

## Stack technique

- **React 19** avec TypeScript 5.9
- **Vite** comme bundler
- **TailwindCSS** pour le styling
- **Axios** pour les appels API
- **WebSocket natif** pour le temps reel

## Pages

### Dashboard (`/`)
Tableau de bord avec :
- Statistiques globales (VMs, deploiements, hyperviseurs)
- VMs recentes avec statut
- Activite recente (deploiements en cours)

### Virtual Machines (`/vms`)
- Liste des VMs avec filtres (statut, hyperviseur, recherche)
- Actions : demarrer, arreter, redemarrer, supprimer
- Details VM dans un panneau lateral
- Telechargement fichier RDP
- Lien vers console/terminal

### New Deployment (`/deployments/new`)
Formulaire wizard multi-etapes :
1. Selection hyperviseur + template OS
2. Configuration ressources (CPU, RAM, disque)
3. Configuration reseau (DHCP ou IP statique)
4. Services (RDP, WinRM, SSH)
5. Logiciels (profils + packages individuels)
6. Resume et lancement

### Deployments (`/deployments`)
- Liste des deploiements avec progression temps reel
- Barre de progression animee
- Logs detailles par deploiement
- Filtres par statut

### Templates (`/templates`)
- Liste des templates OS disponibles
- Creation/edition de templates
- Validation Jinja2

### Hypervisors (`/hypervisors`)
- Liste des hyperviseurs configures
- Test de connexion
- Synchronisation des VMs
- Virtual switches disponibles

### Marketplace (`/marketplace`)
- Catalogue de 150+ logiciels Windows
- Recherche et filtrage par categorie
- Selection pour deploiement

### VM Console (`/vms/{id}/console`)
- Console graphique (screenshots WMI en temps reel)
- Envoi de touches clavier
- Rafraichissement automatique

### Settings (`/settings`)
- Configuration de l'application
- Chemins par defaut (VHDX, ISO)
- Parametres Hyper-V

### Login (`/login`)
- Page de connexion (JWT)
- Branding OTO

### Help (`/help`)
- Documentation integree
- Guide d'utilisation
- FAQ

## Composants UI

### Layout
- `MainLayout` : Layout principal avec sidebar + header
- `Sidebar` : Navigation laterale (style OTO bleu)
- `Header` : En-tete avec user, theme toggle, notifications

### Auth
| Composant | Description |
|-----------|-------------|
| `ProtectedRoute` | Route protegee par JWT (redirige vers /login) |

### Composants reutilisables
| Composant | Description |
|-----------|-------------|
| `Button` | Bouton (variants, sizes, loading, icons) |
| `Input` / `Textarea` | Champs de saisie |
| `Select` | Selecteur |
| `Switch` | Interrupteur on/off |
| `DataTable` | Tableau avec tri, pagination, selection |
| `StatusBadge` | Badge colore selon le statut |
| `StatCard` | Carte statistique avec icone |
| `ProgressBar` / `ProgressTimeline` / `ProgressCircle` | Barres et indicateurs de progression |
| `Modal` / `ConfirmModal` | Modal/Dialog + confirmation |
| `Toast` / `ToastProvider` | Notifications toast |
| `Dropdown` | Menu deroulant |
| `Tooltip` | Info-bulle |
| `CommandPalette` | Palette de commandes (Ctrl+K) |
| `CopyButton` | Bouton copier dans le presse-papier |
| `ThemeToggle` / `ThemeDropdown` | Bascule dark/light mode |
| `Skeleton` / `SkeletonCard` / `SkeletonTable` | Placeholders de chargement |
| `EmptyState` | Etat vide avec action |

### Composants VM
| Composant | Description |
|-----------|-------------|
| `VMConsole` | Console graphique (WebSocket + screenshots) |
| `VMTerminal` | Terminal PowerShell (WebSocket + texte) |

## Hooks

| Hook | Description |
|------|-------------|
| `useWebSocket` | Connexion WebSocket avec reconnexion automatique |
| `useKeyboardShortcuts` | Raccourcis clavier globaux |
| `useVMConsole` | Gestion console VM (screenshots, clavier) |
| `useVMTerminal` | Gestion terminal VM (input/output) |

## Contextes

| Contexte | Description |
|----------|-------------|
| `AuthContext` | Authentification JWT (login, logout, user) |
| `ThemeContext` | Theme dark/light (persiste en localStorage) |

## Theme

- **Dark mode** par defaut
- Couleur primaire : bleu OTO (`#2563eb`)
- Responsive (sidebar collapsible sur mobile)

## Developpement

```bash
cd frontend
npm install
npm run dev          # Dev server sur http://localhost:5173
npm run build        # Build production
npm run lint         # Linting ESLint
```

### Proxy API

Le `vite.config.ts` configure un proxy vers le backend :
- `/api/*` → `http://localhost:8000`
- `/ws/*` → `ws://localhost:8000`
- `/health` → `http://localhost:8000`
