# Charte Graphique OTO Technology

## Résumé pour intégration dans VM Automation

Ce document résume les éléments graphiques identifiés dans la présentation OTO Technology (2025.OTO_PPT-IT.pdf) à intégrer dans l'outil VM Automation.

---

## 1. Logo OTO

### Logo Principal
Le logo OTO se compose de deux éléments :

1. **Logotype texte** : "OTO" dans un cadre ovale/arrondi
   - Style épuré et minimaliste
   - Fichier extrait : `logo_extract-001.png`

2. **Élément graphique (marque visuelle)**
   - Trois formes géométriques alignées horizontalement :
     - Un cercle noir avec encoche (forme en "C")
     - Un cercle noir plein
     - Un carré bleu
   - Cet élément apparaît en haut à droite de chaque slide

### Utilisation recommandée
- Header de l'application : élément graphique (3 formes) en haut à droite
- Footer/Sidebar : logotype texte "OTO"

---

## 2. Palette de Couleurs

### Couleurs Principales

| Nom | Code Hex | RGB | Utilisation |
|-----|----------|-----|-------------|
| **OTO Blue (Principal)** | `#3B82F6` | rgb(59, 130, 246) | Accents, boutons primaires, liens, icônes |
| **OTO Blue Foncé** | `#1E40AF` | rgb(30, 64, 175) | Hover states, éléments actifs |
| **OTO Navy** | `#1E3A5F` | rgb(30, 58, 95) | Barres de progression, éléments secondaires |
| **Noir** | `#000000` | rgb(0, 0, 0) | Titres, texte principal |
| **Blanc** | `#FFFFFF` | rgb(255, 255, 255) | Fond principal |

### Couleurs Secondaires (Nuances)

| Nom | Code Hex | RGB | Utilisation |
|-----|----------|-----|-------------|
| **Bleu Très Clair** | `#EFF6FF` | rgb(239, 246, 255) | Fonds de sections, hover léger |
| **Bleu Clair** | `#BFDBFE` | rgb(191, 219, 254) | En-têtes de tableaux, badges |
| **Bleu Medium** | `#93C5FD` | rgb(147, 197, 253) | Éléments interactifs secondaires |
| **Gris Texte** | `#6B7280` | rgb(107, 114, 128) | Texte secondaire, labels |
| **Gris Clair** | `#F3F4F6` | rgb(243, 244, 246) | Bordures, séparateurs |

### Palette Tailwind CSS

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        'oto': {
          50: '#EFF6FF',
          100: '#DBEAFE',
          200: '#BFDBFE',
          300: '#93C5FD',
          400: '#60A5FA',
          500: '#3B82F6',  // Couleur principale
          600: '#2563EB',
          700: '#1D4ED8',
          800: '#1E40AF',
          900: '#1E3A5F',
        }
      }
    }
  }
}
```

---

## 3. Typographie

### Police des Titres
- **Style** : Sans-serif condensé, Extra Bold / Black
- **Caractéristiques** : Tout en MAJUSCULES, très impactant
- **Recommandation** : `Bebas Neue`, `Oswald`, ou `Inter` en poids 800-900
- **Fallback** : `system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`

### Police du Corps de Texte
- **Style** : Sans-serif lisible, poids Regular (400) à Semi-Bold (600)
- **Recommandation** : `Inter`, `Roboto`, `Open Sans`
- **Taille** : 14-16px pour le corps, 12-13px pour les labels

### Hiérarchie Typographique

| Élément | Taille | Poids | Style |
|---------|--------|-------|-------|
| H1 (Titre principal) | 48-64px | 900 (Black) | Majuscules |
| H2 (Sous-titre) | 32-40px | 800 (Extra Bold) | Majuscules |
| H3 (Section) | 24-28px | 700 (Bold) | Majuscules, couleur bleue |
| H4 (Sous-section) | 18-20px | 600 (Semi-Bold) | Normal |
| Corps de texte | 14-16px | 400 (Regular) | Normal |
| Labels/Caption | 12-13px | 500 (Medium) | Normal |

### CSS Recommandé

```css
/* Import des polices */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

/* Variables de typographie */
:root {
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-heading: 'Inter', system-ui, sans-serif;
}

/* Styles de base */
body {
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  color: #000000;
}

h1, h2, h3 {
  font-family: var(--font-heading);
  text-transform: uppercase;
  letter-spacing: -0.02em;
}

h1 { font-size: 3rem; font-weight: 900; }
h2 { font-size: 2rem; font-weight: 800; }
h3 { font-size: 1.5rem; font-weight: 700; color: #3B82F6; }
```

---

## 4. Style de Mise en Page

### Principes Généraux
- **Minimalisme** : Beaucoup d'espace blanc, design épuré
- **Géométrie** : Formes nettes, carrées et rectangulaires
- **Grille** : Layout basé sur une grille structurée
- **Contraste** : Fort contraste entre texte noir et fond blanc

### Éléments de Design

#### Barre de Progression (Footer)
La charte utilise une barre de progression distinctive en bas de page :
- Série de rectangles allant du bleu vif au bleu foncé puis noir
- Représente la progression/navigation

```css
/* Exemple de barre de progression OTO */
.oto-progress-bar {
  display: flex;
  height: 8px;
  gap: 4px;
}

.oto-progress-bar span:nth-child(1) { background: #3B82F6; flex: 3; }
.oto-progress-bar span:nth-child(2) { background: #2563EB; flex: 2; }
.oto-progress-bar span:nth-child(3) { background: #1E40AF; flex: 1; }
.oto-progress-bar span:nth-child(4) { background: #1E3A5F; flex: 0.5; }
.oto-progress-bar span:nth-child(5) { background: #000000; flex: 0.5; }
```

#### Tableaux
- **En-têtes** : Fond bleu clair (#BFDBFE), texte bleu foncé (#1E40AF)
- **Lignes** : Alternance blanc / très légèrement gris
- **Bordures** : Fines, couleur grise claire

#### Cartes/Blocs
- Fond blanc
- Ombre légère optionnelle
- Coins légèrement arrondis (4-8px)
- Bordure fine grise claire

---

## 5. Iconographie et Illustrations

### Style d'Icônes
- **Type** : Line icons (contours fins)
- **Couleur** : Bleu OTO (#3B82F6) ou Noir (#000000)
- **Épaisseur de trait** : 1.5-2px

### Illustrations
- Style géométrique et minimaliste
- Flèches et formes circulaires pour les schémas
- Couleur bleue principale

---

## 6. Éléments à Intégrer dans VM Automation

### Header
```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo OTO]                              ⚫ ● 🟦  │
│  VM Automation                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Sidebar
- Fond blanc ou très légèrement bleu (#EFF6FF)
- Icônes bleues (#3B82F6)
- Item actif : fond bleu clair (#BFDBFE), texte bleu foncé

### Boutons

```css
/* Bouton primaire */
.btn-primary {
  background-color: #3B82F6;
  color: #FFFFFF;
  font-weight: 600;
  padding: 10px 20px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.btn-primary:hover {
  background-color: #1E40AF;
}

/* Bouton secondaire */
.btn-secondary {
  background-color: transparent;
  color: #3B82F6;
  border: 2px solid #3B82F6;
  font-weight: 600;
  padding: 10px 20px;
  border-radius: 6px;
}
```

### Status Badges

| Status | Fond | Texte | Exemple |
|--------|------|-------|---------|
| Success | `#D1FAE5` | `#065F46` | Déployé, Actif |
| Warning | `#FEF3C7` | `#92400E` | En attente |
| Error | `#FEE2E2` | `#991B1B` | Erreur |
| Info | `#DBEAFE` | `#1E40AF` | En cours |
| Neutral | `#F3F4F6` | `#374151` | Inactif |

---

## 7. Fichiers Extraits

Les fichiers suivants ont été extraits du PDF et sont disponibles dans ce dossier :

- `logo_extract-001.png` - Logo OTO texte
- `logo_extract-004.png` - Barre de couleurs/progression
- `preview-01.png` à `preview-05.png` - Aperçus des premières pages
- `preview2-08.png` à `preview2-12.png` - Pages de contenu
- `preview3-13.png` à `preview3-16.png` - Pages textuelles

---

## 8. Recommandations d'Implémentation

### Priorité Haute
1. Intégrer la palette de couleurs OTO dans Tailwind
2. Appliquer la typographie (titres en majuscules, Inter/sans-serif)
3. Mettre à jour les boutons avec le style OTO
4. Ajouter le logo/élément graphique dans le header

### Priorité Moyenne
1. Refaire les tableaux avec le style OTO
2. Mettre à jour les status badges
3. Appliquer le style aux formulaires

### Priorité Basse
1. Ajouter les animations/transitions subtiles
2. Intégrer les icônes line-style
3. Ajouter la barre de progression dans le footer

---

## Informations Entreprise

**OTO Technology**
- Adresse : 79-83 Rue Baudin, 92300 Levallois-Perret, France
- Téléphone : +33 (0)1 84 79 97 36
- Email : hello@oto-technology.fr
- Site web : www.oto-technology.fr
- SIREN : 534 628 318 00030

---

*Document généré le 28/01/2026*
*Source : 2025.OTO_PPT-IT.pdf*
