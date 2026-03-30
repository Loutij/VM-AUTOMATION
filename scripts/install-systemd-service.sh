#!/bin/bash
# =============================================================================
# VM Automation - Installation du service systemd (démarrage au boot)
# =============================================================================
# Usage: ./scripts/install-systemd-service.sh
# Nécessite les droits sudo pour copier dans /etc/systemd/system/
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="vm-automation.service"
UNIT_SRC="$PROJECT_DIR/config/$SERVICE_NAME"
UNIT_DST="/etc/systemd/system/$SERVICE_NAME"

if [[ ! -f "$UNIT_SRC" ]]; then
    echo "Erreur: $UNIT_SRC introuvable."
    exit 1
fi

echo "Installation du service systemd pour VM Automation..."
echo "  Source: $UNIT_SRC"
echo "  Cible:  $UNIT_DST"
echo ""

sudo cp "$UNIT_SRC" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo ""
echo "Service installé et activé au boot."
echo ""
echo "Commandes utiles:"
echo "  Démarrer maintenant:  sudo systemctl start vm-automation"
echo "  Arrêter:             sudo systemctl stop vm-automation"
echo "  Statut:              sudo systemctl status vm-automation"
echo "  Désactiver au boot:  sudo systemctl disable vm-automation"
echo ""
echo "Pour démarrer immédiatement sans redémarrer la machine:"
echo "  sudo systemctl start vm-automation"
echo ""
