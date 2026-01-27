# Rapport de Tests Utilisateur - VM-AUTOMATION

**Date**: 27 janvier 2026  
**Testeur**: Agent Claude  
**Environnement**: http://localhost:3001  
**Identifiants**: Admin / Admin123!  
**Backend**: http://localhost:8000

---

## Résumé Exécutif

| Catégorie | Critique | Majeur | Mineur | Total | Corrigés |
|-----------|----------|--------|--------|-------|----------|
| Bugs | 2 | 4 | 3 | 9 | 6 |
| UX/UI | 0 | 3 | 5 | 8 | 1 |
| Incohérences | 0 | 2 | 2 | 4 | 0 |
| Manques | 0 | 3 | 2 | 5 | 0 |

**Bugs corrigés le 27/01/2026**: BUG-001, BUG-002, BUG-003, BUG-004, BUG-009, UX-001

---

## BUGS CRITIQUES

### BUG-001: Nom du déploiement non affiché ✅ CORRIGÉ
- **Page**: Dashboard, Déploiements
- **Description**: La colonne "Nom" des déploiements récents est vide. Impossible d'identifier quel déploiement est affiché.
- **Reproduction**: Aller sur Dashboard → Section "Déploiements récents" → La colonne Nom est vide
- **Impact**: L'utilisateur ne peut pas distinguer ses déploiements
- **Priorité**: CRITIQUE
- **Correction**: Ajout de la propriété `name` comme alias de `vm_name` dans le type Deployment et le mapper API

### BUG-002: Validation formulaire sans feedback utilisateur ✅ CORRIGÉ
- **Page**: Nouveau déploiement (/deployments/new)
- **Description**: Quand on clique sur "Suivant" sans remplir les champs obligatoires, rien ne se passe. Pas de message d'erreur visible.
- **Reproduction**: 
  1. Aller sur /deployments/new
  2. Sélectionner hyperviseur et template
  3. Cliquer Suivant → Étape 2 (Ressources)
  4. Ne pas remplir "Nom de la VM"
  5. Cliquer Suivant → Rien ne se passe
- **Erreur console**: `API Error: Request failed with status code 422`
- **Impact**: L'utilisateur ne comprend pas pourquoi le formulaire ne progresse pas
- **Priorité**: CRITIQUE
- **Correction**: Ajout de messages d'erreur visuels + toast notifications pour la validation

---

## BUGS MAJEURS

### BUG-003: Colonne VMs des hyperviseurs affiche "-" ✅ CORRIGÉ
- **Page**: Hyperviseurs (/hypervisors)
- **Description**: La colonne "VMs" de l'hyperviseur affiche "-" alors qu'il y a 3 VMs sur le Dashboard
- **Reproduction**: Aller sur Hyperviseurs → Voir colonne VMs = "-"
- **Attendu**: Devrait afficher "3" (nombre de VMs gérées)
- **Priorité**: MAJEURE
- **Correction**: Ajout de vm_count dans le schéma HypervisorResponse et calcul dans l'endpoint list_hypervisors

### BUG-004: Titre de page HTML générique ✅ CORRIGÉ
- **Page**: Toutes les pages
- **Description**: Le titre de l'onglet du navigateur est "frontend" au lieu de "VM Automation - [Page]"
- **Reproduction**: Ouvrir n'importe quelle page → Regarder le titre de l'onglet
- **Impact**: Mauvais référencement, confusion avec plusieurs onglets ouverts
- **Priorité**: MAJEURE
- **Correction**: Changement du titre dans index.html de "frontend" à "VM Automation"

### BUG-005: Templates liste seulement 1 template alors que déploiement en liste 7
- **Page**: Templates (/templates)
- **Description**: La page Templates n'affiche qu'un seul template (Windows_Server_2022) alors que le formulaire de déploiement en propose 7
- **Reproduction**: 
  1. Aller sur Templates → 1 template visible
  2. Aller sur Nouveau déploiement → 7 templates disponibles
- **Incohérence**: Les templates viennent de sources différentes ?
- **Priorité**: MAJEURE

### BUG-006: Erreurs React Router Future Flag
- **Page**: Toutes (console)
- **Description**: Warnings React Router sur les future flags v7
- **Erreur**: 
  ```
  ⚠️ React Router Future Flag Warning: React Router will begin wrapping state updates in `React.startTransition` in v7
  ⚠️ React Router Future Flag Warning: Relative route resolution within Splat routes is changing in v7
  ```
- **Impact**: Préparer la migration vers React Router v7
- **Priorité**: MAJEURE (dette technique)

---

## BUGS MINEURS

### BUG-007: Nom de template tronqué
- **Page**: Templates (/templates)
- **Description**: Le nom "Windows_Server_2022" est affiché comme "Windows_Ser..."
- **Reproduction**: Aller sur Templates → Observer la carte du template
- **Attendu**: Nom complet ou tooltip au survol
- **Priorité**: MINEURE

### BUG-008: Bouton "Ajouter un hyperviseur" tronqué
- **Page**: Hyperviseurs (/hypervisors) - selon résolution
- **Description**: Le texte du bouton peut être tronqué sur certaines résolutions
- **Attendu**: Bouton responsive ou icône + texte adaptatif
- **Priorité**: MINEURE

### BUG-009: Stepper du formulaire - dernier step tronqué ✅ CORRIGÉ
- **Page**: Nouveau déploiement (/deployments/new)
- **Description**: Le dernier step du stepper affiche "Résu..." au lieu de "Résumé"
- **Reproduction**: Aller sur /deployments/new → Observer le stepper
- **Priorité**: MINEURE
- **Correction**: Amélioration du CSS du stepper avec whitespace-nowrap et meilleur responsive

---

## PROBLÈMES UX/UI

### UX-001: Incohérence de vocabulaire - État des VMs ✅ CORRIGÉ
- **Description**: 
  - Stats en haut: "En cours d'exécution"
  - Tableau: "En cours"
- **Suggestion**: Uniformiser vers "En cours d'exécution" ou "Running"
- **Priorité**: MAJEURE
- **Correction**: StatusBadge modifié pour afficher "En cours d'exécution" pour l'état running

### UX-002: Pas de sélection par défaut dans le formulaire de déploiement
- **Description**: L'hyperviseur et le template ne sont pas pré-sélectionnés
- **Suggestion**: Pré-sélectionner le premier hyperviseur disponible
- **Priorité**: MAJEURE

### UX-003: Recherche globale non fonctionnelle
- **Description**: Le champ "Rechercher..." dans le header ne semble pas connecté
- **Reproduction**: Taper quelque chose → Aucune réaction visible
- **Suggestion**: Implémenter une recherche globale ou retirer le champ
- **Priorité**: MAJEURE

### UX-004: Menu d'actions VM - positionnement
- **Description**: Le menu dropdown des actions VM peut chevaucher d'autres lignes
- **Suggestion**: Ajuster le z-index et la position
- **Priorité**: MINEURE

### UX-005: Pas d'indication de chargement sur les boutons
- **Description**: Quand on clique sur "Actualiser" ou "Synchroniser", pas de spinner
- **Suggestion**: Ajouter un état de chargement visuel
- **Priorité**: MINEURE

### UX-006: Dashboard - Actions rapides redondantes
- **Description**: Les boutons "Actions rapides" ne sont pas visibles sur la capture complète du Dashboard
- **Suggestion**: Les mettre en évidence ou les déplacer
- **Priorité**: MINEURE

### UX-007: Pas de confirmation avant actions destructives
- **Description**: Non testé mais à vérifier: confirmation avant suppression de VM ?
- **Suggestion**: Modal de confirmation pour Supprimer, Arrêter, etc.
- **Priorité**: MINEURE

### UX-008: Marketplace vide sans explication claire
- **Description**: "Aucun logiciel trouvé" mais pas d'explication que le catalogue doit être initialisé
- **Suggestion**: Message explicatif + CTA vers "Initialiser le catalogue"
- **Priorité**: MINEURE

---

## INCOHÉRENCES

### INC-001: Nombre de templates
- **Dashboard/Templates**: 1 template affiché
- **Formulaire déploiement**: 7 templates disponibles
- **Problème**: Source de données différente ou cache ?

### INC-002: État du health check Redis/Celery
- **Endpoint**: /health
- **Réponse**: 
  ```json
  {"redis":{"status":"unknown","message":"Not implemented yet"},
   "celery":{"status":"unknown","message":"Not implemented yet"}}
  ```
- **Problème**: Health check incomplet

### INC-003: Deux champs de recherche sur certaines pages
- **Page**: VMs, Hyperviseurs
- **Description**: Recherche globale (header) + recherche locale (dans la page)
- **Suggestion**: Clarifier les rôles ou unifier

### INC-004: Unités de stockage
- **Constat**: RAM en "Go", Disque en "GB"
- **Suggestion**: Uniformiser (Go/GB ou Gio/GiB)

---

## FONCTIONNALITÉS MANQUANTES

### MISS-001: Pas de page de détails VM
- **Description**: Clic sur "Détails" non testé mais probablement manquant
- **Attendu**: Page détaillée avec infos complètes, logs, historique

### MISS-002: Pas de gestion des utilisateurs
- **Description**: Menu utilisateur ne montre que "Se déconnecter"
- **Attendu**: Gestion du profil, changement de mot de passe

### MISS-003: Pas de pagination
- **Pages**: VMs, Déploiements, Templates
- **Description**: Si beaucoup d'éléments, la liste va devenir ingérable
- **Attendu**: Pagination ou scroll infini

### MISS-004: Pas d'export des données
- **Description**: Impossible d'exporter la liste des VMs en CSV/Excel
- **Attendu**: Bouton d'export pour rapports

### MISS-005: Pas de dark/light mode toggle visible
- **Description**: Les paramètres montrent "Sombre" mais pas de toggle rapide
- **Attendu**: Toggle dans le header ou menu utilisateur

---

## POINTS POSITIFS

1. **Interface moderne et cohérente** - Design dark mode élégant
2. **Navigation claire** - Sidebar bien organisée
3. **Page d'aide complète** - Documentation intégrée avec étapes claires
4. **Formulaire de déploiement multi-étapes** - Bien structuré avec stepper
5. **Menu d'actions VM complet** - Détails, RDP, Aperçu écran, etc.
6. **Paramètres de notifications** - Configuration granulaire
7. **Support multi-OS** - Windows et Linux templates
8. **WebSocket connecté** - Indicateur "Notifications (connecté)"

---

## RECOMMANDATIONS PRIORITAIRES

1. **URGENT**: Corriger l'affichage du nom des déploiements (BUG-001)
2. **URGENT**: Ajouter les messages d'erreur de validation (BUG-002)
3. **IMPORTANT**: Synchroniser les templates entre les pages (BUG-005)
4. **IMPORTANT**: Corriger le titre de page HTML (BUG-004)
5. **AMÉLIORATION**: Uniformiser le vocabulaire (UX-001)
6. **AMÉLIORATION**: Implémenter la recherche globale ou la retirer (UX-003)

---

## TESTS NON EFFECTUÉS

- [ ] Test de déconnexion/reconnexion
- [ ] Test de création complète d'un déploiement
- [ ] Test des actions VM (Arrêter, Redémarrer, Supprimer)
- [ ] Test de l'aperçu écran VM
- [ ] Test de la connexion RDP
- [ ] Test de la synchronisation des VMs
- [ ] Test de l'ajout d'un hyperviseur
- [ ] Test de la création d'un template
- [ ] Test de l'initialisation du catalogue Marketplace
- [ ] Test de la recherche locale dans les tableaux
- [ ] Test du tri des colonnes
- [ ] Test responsive (mobile/tablet)

---

*Rapport généré le 27/01/2026 à 15:00*  
*Mis à jour le 27/01/2026 à 16:00 - Corrections appliquées*
