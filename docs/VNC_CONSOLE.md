# VNC Console

Acces VNC/RDP aux machines virtuelles directement depuis le navigateur.

## Architecture

- **VMs Linux** : serveur TigerVNC/x11vnc installe dans la VM, acces via proxy WebSocket
- **VMs Windows** : RDP natif via Apache Guacamole daemon (guacd)
- **Frontend** : client noVNC (VNC direct) + client Guacamole (RDP)
- **Proxy** : endpoint WebSocket FastAPI relayant entre navigateur et VM

## Fonctionnement

### VMs Linux (VNC)
1. Le serveur VNC (TigerVNC) est installe dans la VM via SSH
2. Le serveur ecoute sur le port 5900 (configurable 5900-5999)
3. Le backend proxie la connexion WebSocket vers TCP (VNC)
4. Le frontend utilise la librairie JavaScript noVNC pour le rendu

### VMs Windows (RDP)
1. RDP est active sur la VM Windows (Bureau a distance integre)
2. Apache Guacamole daemon (guacd) gere le protocole RDP
3. Le backend proxie WebSocket vers guacd via le protocole Guacamole
4. Le frontend effectue le rendu via le client JavaScript Guacamole

## Endpoints API

### Proxy VNC
- `WS /api/v1/vnc/ws/{vm_id}?token=JWT&vnc_port=5900` — Proxy WebSocket VNC direct

### Proxy Guacamole
- `WS /api/v1/guacamole/ws/{vm_id}?token=JWT&width=1280&height=720` — RDP/VNC via guacd

### Gestion VNC
- `POST /api/v1/vms/{vm_id}/vnc/install` — Installer le serveur VNC (Linux) / Activer RDP (Windows)
- `GET /api/v1/vms/{vm_id}/vnc/status` — Verifier l'accessibilite du serveur VNC
- `GET /api/v1/vnc/sessions` — Lister les sessions VNC proxy actives

## Configuration

Variables d'environnement dans `.env` :

| Variable | Defaut | Description |
|----------|--------|-------------|
| VNC_DEFAULT_PORT | 5900 | Port VNC par defaut |
| VNC_MAX_SESSIONS | 10 | Sessions VNC simultanees maximum |
| VNC_SESSION_TIMEOUT | 3600 | Timeout de session (secondes) |
| VNC_PROXY_ENABLED | true | Activer le proxy WebSocket VNC |

## Docker Setup

Service guacd dans `docker-compose.yml` :

```yaml
  guacd:
    image: guacamole/guacd:1.5.4
    container_name: vmautomation-guacd
    restart: unless-stopped
    ports:
      - "4822:4822"
    networks:
      - vmautomation-network
```

## Utilisation Frontend

1. Naviguer vers la liste des VMs
2. Cliquer sur le bouton **VNC** d'une VM en cours d'execution
3. Si VNC n'est pas installe, cliquer d'abord sur **Installer VNC**
4. La visionneuse VNC s'ouvre avec une barre d'outils : Ctrl+Alt+Del, plein ecran, echelle, presse-papiers, lecture seule

## Raccourcis Clavier

| Raccourci | Action |
|-----------|--------|
| `Ctrl+Alt+Del` | Envoyer Ctrl+Alt+Suppr a la VM |
| `F11` ou bouton barre d'outils | Basculer en plein ecran |

## Depannage

| Probleme | Solution |
|----------|----------|
| "Cannot connect to VNC server" | Verifier que VNC est installe et que le pare-feu de la VM autorise le port 5900 |
| "Unauthorized" | Token JWT expire, rafraichir la page |
| Ecran noir | La VM n'a pas d'environnement graphique, installer `xfce4` |
| RDP Windows echoue | Verifier que RDP est active et que la regle pare-feu existe |
| guacd indisponible | Verifier `docker compose logs guacd` |
