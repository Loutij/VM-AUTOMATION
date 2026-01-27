#!/bin/bash
# =============================================================================
# VM Automation - Script de démarrage et supervision des services
# =============================================================================
# Usage: ./scripts/start_services.sh [start|stop|status|restart]
# =============================================================================

set -e

PROJECT_DIR="/home/otoroot/VM-AUTOMATION"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="/tmp"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Fonctions de vérification
# =============================================================================

check_api() {
    curl -s http://localhost:8000/health > /dev/null 2>&1
    return $?
}

check_frontend() {
    curl -s http://localhost:3000 > /dev/null 2>&1
    return $?
}

check_postgres() {
    pg_isready -h localhost -p 5432 > /dev/null 2>&1
    return $?
}

check_redis() {
    redis-cli ping > /dev/null 2>&1
    return $?
}

check_celery() {
    pgrep -f "celery.*worker" > /dev/null 2>&1
    return $?
}

check_celery_beat() {
    pgrep -f "celery.*beat" > /dev/null 2>&1
    return $?
}

# =============================================================================
# Fonctions de démarrage
# =============================================================================

start_api() {
    if check_api; then
        log_info "API déjà en cours d'exécution"
        return 0
    fi
    
    log_info "Démarrage de l'API..."
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/api.log" 2>&1 &
    
    # Attendre le démarrage
    for i in {1..30}; do
        sleep 1
        if check_api; then
            log_info "API démarrée avec succès (PID: $(pgrep -f 'uvicorn.*8000' | head -1))"
            return 0
        fi
    done
    
    log_error "Échec du démarrage de l'API"
    return 1
}

start_frontend() {
    if check_frontend; then
        log_info "Frontend déjà en cours d'exécution"
        return 0
    fi
    
    log_info "Démarrage du Frontend..."
    cd "$FRONTEND_DIR"
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    
    # Attendre le démarrage
    for i in {1..30}; do
        sleep 1
        if check_frontend; then
            log_info "Frontend démarré avec succès"
            return 0
        fi
    done
    
    log_error "Échec du démarrage du Frontend"
    return 1
}

start_celery() {
    if check_celery; then
        log_info "Celery Worker déjà en cours d'exécution"
    else
        log_info "Démarrage de Celery Worker..."
        cd "$PROJECT_DIR"
        source "$VENV_DIR/bin/activate"
        nohup celery -A src.workers.celery_app worker --loglevel=info --concurrency=4 > "$LOG_DIR/celery_worker.log" 2>&1 &
        sleep 3
        if check_celery; then
            log_info "Celery Worker démarré"
        else
            log_error "Échec du démarrage de Celery Worker"
        fi
    fi
    
    if check_celery_beat; then
        log_info "Celery Beat déjà en cours d'exécution"
    else
        log_info "Démarrage de Celery Beat..."
        cd "$PROJECT_DIR"
        source "$VENV_DIR/bin/activate"
        nohup celery -A src.workers.celery_app beat --loglevel=info > "$LOG_DIR/celery_beat.log" 2>&1 &
        sleep 2
        if check_celery_beat; then
            log_info "Celery Beat démarré"
        else
            log_error "Échec du démarrage de Celery Beat"
        fi
    fi
}

# =============================================================================
# Fonctions d'arrêt
# =============================================================================

stop_api() {
    log_info "Arrêt de l'API..."
    pkill -f "uvicorn.*8000" 2>/dev/null || true
    sleep 2
    if ! check_api; then
        log_info "API arrêtée"
    else
        pkill -9 -f "uvicorn.*8000" 2>/dev/null || true
    fi
}

stop_frontend() {
    log_info "Arrêt du Frontend..."
    pkill -f "vite" 2>/dev/null || true
    pkill -f "npm.*dev" 2>/dev/null || true
    sleep 2
    log_info "Frontend arrêté"
}

stop_celery() {
    log_info "Arrêt de Celery..."
    pkill -f "celery.*worker" 2>/dev/null || true
    pkill -f "celery.*beat" 2>/dev/null || true
    sleep 2
    log_info "Celery arrêté"
}

# =============================================================================
# Fonction de statut
# =============================================================================

show_status() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              VM AUTOMATION - État des Services                  ║"
    echo "╠════════════════════════════════════════════════════════════════╣"
    
    # API
    if check_api; then
        API_PID=$(pgrep -f 'uvicorn.*8000' | head -1)
        echo -e "║  API Backend     │ ${GREEN}✓ RUNNING${NC}  │ PID: $API_PID          ║"
    else
        echo -e "║  API Backend     │ ${RED}✗ STOPPED${NC}  │                        ║"
    fi
    
    # Frontend
    if check_frontend; then
        echo -e "║  Frontend        │ ${GREEN}✓ RUNNING${NC}  │ http://localhost:3000  ║"
    else
        echo -e "║  Frontend        │ ${RED}✗ STOPPED${NC}  │                        ║"
    fi
    
    # PostgreSQL
    if check_postgres; then
        echo -e "║  PostgreSQL      │ ${GREEN}✓ RUNNING${NC}  │ localhost:5432         ║"
    else
        echo -e "║  PostgreSQL      │ ${RED}✗ STOPPED${NC}  │                        ║"
    fi
    
    # Redis
    if check_redis; then
        echo -e "║  Redis           │ ${GREEN}✓ RUNNING${NC}  │ localhost:6379         ║"
    else
        echo -e "║  Redis           │ ${RED}✗ STOPPED${NC}  │                        ║"
    fi
    
    # Celery Worker
    if check_celery; then
        CELERY_PIDS=$(pgrep -f 'celery.*worker' | wc -l)
        echo -e "║  Celery Worker   │ ${GREEN}✓ RUNNING${NC}  │ $CELERY_PIDS workers            ║"
    else
        echo -e "║  Celery Worker   │ ${RED}✗ STOPPED${NC}  │                        ║"
    fi
    
    # Celery Beat
    if check_celery_beat; then
        echo -e "║  Celery Beat     │ ${GREEN}✓ RUNNING${NC}  │ scheduler              ║"
    else
        echo -e "║  Celery Beat     │ ${RED}✗ STOPPED${NC}  │                        ║"
    fi
    
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
}

# =============================================================================
# Fonction de supervision (watchdog)
# =============================================================================

watchdog() {
    log_info "Démarrage du watchdog de supervision..."
    
    while true; do
        # Vérifier l'API
        if ! check_api; then
            log_warn "API non disponible, redémarrage..."
            start_api
        fi
        
        # Vérifier le Frontend
        if ! check_frontend; then
            log_warn "Frontend non disponible, redémarrage..."
            start_frontend
        fi
        
        # Vérifier Celery Worker
        if ! check_celery; then
            log_warn "Celery Worker non disponible, redémarrage..."
            start_celery
        fi
        
        # Vérifier Celery Beat
        if ! check_celery_beat; then
            log_warn "Celery Beat non disponible, redémarrage..."
            start_celery
        fi
        
        # Attendre 30 secondes avant la prochaine vérification
        sleep 30
    done
}

# =============================================================================
# Main
# =============================================================================

case "${1:-start}" in
    start)
        log_info "Démarrage de tous les services..."
        start_api
        start_frontend
        start_celery
        show_status
        ;;
    stop)
        log_info "Arrêt de tous les services..."
        stop_api
        stop_frontend
        stop_celery
        show_status
        ;;
    restart)
        log_info "Redémarrage de tous les services..."
        stop_api
        stop_frontend
        stop_celery
        sleep 2
        start_api
        start_frontend
        start_celery
        show_status
        ;;
    status)
        show_status
        ;;
    watchdog)
        # Démarrer les services puis surveiller
        start_api
        start_frontend
        show_status
        watchdog
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|watchdog}"
        exit 1
        ;;
esac
