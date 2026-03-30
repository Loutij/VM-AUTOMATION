# =============================================================================
# VM Automation - Types Package
# =============================================================================
"""
Package contenant les types et schémas.

Note: Les schémas Pydantic sont actuellement définis localement dans chaque router
(src/api/routers/*.py) plutôt que centralisés ici. Ceci permet une meilleure
flexibilité et évite les dépendances circulaires.

Si une centralisation est souhaitée à l'avenir, créer un fichier schemas.py ici
et migrer les schémas des routers progressivement.
"""

__all__: list[str] = []
