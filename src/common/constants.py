# =============================================================================
# VM Automation - Shared Constants
# =============================================================================
"""
Constantes partagées entre les différentes couches de l'application.
"""

# Mapping étape de déploiement -> pourcentage de progression.
# Utilisé par le service de déploiement et le router API pour calculer
# la progression à afficher dans l'interface.
DEPLOYMENT_STEP_PROGRESS: dict[str, int] = {
    "validating": 5,
    "creating_vm": 15,
    "mounting_iso": 25,
    "deploying_dism": 35,
    "configuring_network": 45,
    "starting_installation": 55,
    "waiting_vm_ready": 65,
    "post_configuration": 75,
    "installing_software": 85,
    "finalizing": 95,
    "completed": 100,
    "completed_with_warnings": 100,
    "failed": 0,
    # Étapes spécifiques Linux (utilisent les mêmes valeurs que les étapes
    # génériques pour la compatibilité avec l'interface)
    "generating_seed_config": 25,
    "creating_seed_iso": 30,
    "waiting_ssh_ready": 65,
    "linux_post_install": 75,
}
