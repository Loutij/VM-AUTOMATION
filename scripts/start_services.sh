#!/bin/bash
# =============================================================================
# VM Automation - Script de démarrage des services
# =============================================================================
# Ce script démarre tous les services nécessaires :
# - Backend FastAPI (uvicorn)
# - Frontend Vite (React)
# - Celery Worker (traitement des déploiements)
# - Celery Beat (tâches périodiques)
# - Redis (vérification)
# =============================================================================

set -e

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Répertoire racine du projet
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/.pids"

# Créer les répertoires nécessaires
mkdir -p "$LOG_DIR" "$PID_DIR"

# Fonction d'affichage
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Fonction pour vérifier si un service est en cours d'exécution
is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Fonction pour arrêter un service
stop_service() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"
    
    if is_running "$pid_file"; then
        local pid=$(cat "$pid_file")
        log_info "Arrêt de $name (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        # Force kill si nécessaire
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
        log_success "$name arrêté"
    fi
}

# Fonction pour démarrer le backend
start_backend() {
    log_info "Démarrage du backend FastAPI..."
    
    cd "$PROJECT_DIR"
    source .venv/bin/activate
    
    # Arrêter si déjà en cours
    stop_service "backend"
    
    # Démarrer uvicorn
    nohup uvicorn src.api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        > "$LOG_DIR/backend.log" 2>&1 &
    
    echo $! > "$PID_DIR/backend.pid"
    sleep 2
    
    if is_running "$PID_DIR/backend.pid"; then
        log_success "Backend démarré sur http://localhost:8000"
    else
        log_error "Échec du démarrage du backend"
        cat "$LOG_DIR/backend.log"
        return 1
    fi
}

# Fonction pour démarrer le frontend
start_frontend() {
    log_info "Démarrage du frontend Vite..."
    
    cd "$PROJECT_DIR/frontend"
    
    # Arrêter si déjà en cours
    stop_service "frontend"
    
    # Vérifier node_modules
    if [ ! -d "node_modules" ]; then
        log_info "Installation des dépendances npm..."
        npm install
    fi
    
    # Démarrer vite
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    
    echo $! > "$PID_DIR/frontend.pid"
    sleep 3
    
    if is_running "$PID_DIR/frontend.pid"; then
        # Récupérer le port depuis les logs
        local port=$(grep -oP 'localhost:\K[0-9]+' "$LOG_DIR/frontend.log" | head -1)
        log_success "Frontend démarré sur http://localhost:${port:-3000}"
    else
        log_error "Échec du démarrage du frontend"
        cat "$LOG_DIR/frontend.log"
        return 1
    fi
}

# Fonction pour démarrer Celery Worker
start_celery_worker() {
    log_info "Démarrage du Celery Worker..."
    
    cd "$PROJECT_DIR"
    source .venv/bin/activate
    
    # Arrêter si déjà en cours
    stop_service "celery_worker"
    
    # Démarrer le worker
    nohup celery -A src.workers.celery_app worker \
        --loglevel=info \
        --concurrency=4 \
        > "$LOG_DIR/celery_worker.log" 2>&1 &
    
    echo $! > "$PID_DIR/celery_worker.pid"
    sleep 3
    
    if is_running "$PID_DIR/celery_worker.pid"; then
        log_success "Celery Worker démarré"
    else
        log_error "Échec du démarrage du Celery Worker"
        cat "$LOG_DIR/celery_worker.log"
        return 1
    fi
}

# Fonction pour démarrer Celery Beat
start_celery_beat() {
    log_info "Démarrage du Celery Beat (tâches périodiques)..."
    
    cd "$PROJECT_DIR"
    source .venv/bin/activate
    
    # Arrêter si déjà en cours
    stop_service "celery_beat"
    
    # Démarrer beat
    nohup celery -A src.workers.celery_app beat \
        --loglevel=info \
        > "$LOG_DIR/celery_beat.log" 2>&1 &
    
    echo $! > "$PID_DIR/celery_beat.pid"
    sleep 2
    
    if is_running "$PID_DIR/celery_beat.pid"; then
        log_success "Celery Beat démarré"
    else
        log_error "Échec du démarrage du Celery Beat"
        cat "$LOG_DIR/celery_beat.log"
        return 1
    fi
}

# Fonction pour vérifier Redis
check_redis() {
    log_info "Vérification de Redis..."
    
    if redis-cli ping > /dev/null 2>&1; then
        log_success "Redis est disponible"
        return 0
    else
        log_error "Redis n'est pas disponible. Démarrez Redis avec: sudo systemctl start redis"
        return 1
    fi
}

# Fonction pour vérifier PostgreSQL
check_postgres() {
    log_info "Vérification de PostgreSQL..."
    
    if pg_isready -q 2>/dev/null; then
        log_success "PostgreSQL est disponible"
        return 0
    else
        log_warning "Impossible de vérifier PostgreSQL (pg_isready non disponible ou DB distante)"
        return 0
    fi
}

# Fonction pour afficher le statut
show_status() {
    echo ""
    echo "=========================================="
    echo "        STATUT DES SERVICES"
    echo "=========================================="
    
    for service in backend frontend celery_worker celery_beat; do
        if is_running "$PID_DIR/$service.pid"; then
            local pid=$(cat "$PID_DIR/$service.pid")
            echo -e "${GREEN}●${NC} $service (PID: $pid)"
        else
            echo -e "${RED}●${NC} $service (arrêté)"
        fi
    done
    
    echo ""
    echo "Logs disponibles dans: $LOG_DIR/"
    echo "=========================================="
}

# Fonction pour tout arrêter
stop_all() {
    log_info "Arrêt de tous les services..."
    
    stop_service "celery_beat"
    stop_service "celery_worker"
    stop_service "frontend"
    stop_service "backend"
    
    # Nettoyage supplémentaire
    pkill -f "uvicorn src.api.main:app" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    pkill -f "celery -A src.workers" 2>/dev/null || true
    
    log_success "Tous les services sont arrêtés"
}

# Fonction pour tout démarrer
start_all() {
    echo ""
    echo "=========================================="
    echo "   VM AUTOMATION - Démarrage des services"
    echo "=========================================="
    echo ""
    
    # Vérifications préalables
    check_redis || exit 1
    check_postgres
    
    echo ""
    
    # Démarrage des services
    start_backend
    start_frontend
    start_celery_worker
    start_celery_beat
    
    # Afficher le statut
    show_status
    
    echo ""
    log_success "Tous les services sont démarrés!"
    echo ""
    echo "URLs:"
    echo "  - Backend API:  http://localhost:8000"
    echo "  - Frontend:     http://localhost:3000"
    echo "  - API Docs:     http://localhost:8000/docs"
    echo ""
}

# Fonction pour redémarrer
restart_all() {
    stop_all
    sleep 2
    start_all
}

# Fonction d'aide
show_help() {
    echo "Usage: $0 [commande]"
    echo ""
    echo "Commandes:"
    echo "  start     Démarrer tous les services"
    echo "  stop      Arrêter tous les services"
    echo "  restart   Redémarrer tous les services"
    echo "  status    Afficher le statut des services"
    echo "  logs      Afficher les logs (tail -f)"
    echo "  help      Afficher cette aide"
    echo ""
}

# Fonction pour suivre les logs
follow_logs() {
    echo "Appuyez sur Ctrl+C pour arrêter"
    tail -f "$LOG_DIR"/*.log
}

# Point d'entrée principal
case "${1:-start}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        restart_all
        ;;
    status)
        show_status
        ;;
    logs)
        follow_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Commande inconnue: $1"
        show_help
        exit 1
        ;;
esac
