# VM Automation - Guide de Depannage

## Problemes de deploiement

### "Votre compte a ete desactive" (Windows 10/11)

**Cause** : Le compte built-in `Administrateur` est desactive par defaut sur Windows 10/11 (editions client). Le template Server 2022 etait utilise pour toutes les editions.

**Solution** : Le systeme selectionne maintenant automatiquement le bon template unattend selon l'OS. Les templates Win10/11 creent un compte `Admin` et activent le built-in `Administrateur` dans les FirstLogonCommands.

### RDP ne fonctionne pas apres deploiement

**Causes possibles** :
1. **Firewall localise** : Sur Windows FR, le groupe firewall s'appelle "Bureau a distance" (pas "Remote Desktop")
2. **NLA active** : Network Level Authentication bloque la connexion
3. **Post-install echoue** : Le script PowerShell Direct n'a pas pu s'executer

**Solution** : Le systeme active maintenant le RDP a 3 niveaux redondants :
- `specialize` pass (unattend)
- `FirstLogonCommands` (unattend) avec FR/EN + NLA desactive
- Post-configuration Python avec FR/EN + NLA desactive

### PowerShell Direct echoue

**Symptomes** : Le deploiement reste bloque a l'etape `waiting_vm_ready`.

**Verifications** :
1. La VM est-elle demarree ? `Get-VM -Name "vm-name" | Select State`
2. Les Integration Services sont-ils actifs ? `Get-VMIntegrationService -VMName "vm-name"`
3. Le heartbeat est-il present ? `(Get-VM "vm-name").Heartbeat`
4. Le mot de passe est-il correct ? Tester manuellement :
   ```powershell
   Invoke-Command -VMName "vm-name" -Credential (Get-Credential) -ScriptBlock { hostname }
   ```

### Deploiement Linux bloque a "Waiting VM ready"

**Cause** : La VM n'a pas obtenu d'IP ou SSH n'est pas accessible.

**Verifications** :
1. La VM a-t-elle une IP ? Verifier dans Hyper-V Manager
2. Le preseed/cloud-init s'est-il execute correctement ?
3. SSH est-il installe et actif ?
4. Le virtual switch est-il connecte au reseau ?

## Problemes de connexion

### WinRM : "Connection refused" ou timeout

**Verifications** :
```powershell
# Sur l'hote Hyper-V
Test-WSMan -ComputerName localhost
Get-Service WinRM
winrm enumerate winrm/config/listener
```

**Solutions** :
```powershell
Enable-PSRemoting -Force
Set-Item WSMan:\localhost\Client\TrustedHosts -Value "*" -Force
Restart-Service WinRM
```

### "Access denied" lors de la connexion WinRM

**Causes** :
- Mauvais credentials dans la config hyperviseur
- Compte desactive ou verrouille
- Firewall bloque le port 5986

**Solution** : Verifier les credentials dans Settings > Hyperviseurs > Tester connexion.

## Problemes d'infrastructure

### PostgreSQL non accessible

```bash
# Verifier le conteneur
docker compose ps postgres
docker compose logs postgres

# Tester la connexion
docker compose exec postgres psql -U vmautomation -c "SELECT 1"
```

### Redis non accessible

```bash
docker compose ps redis
docker compose exec redis redis-cli ping
```

### Celery workers non demarre

```bash
# Lancer manuellement
celery -A src.workers.celery_app worker --loglevel=info

# Verifier dans Flower
# http://localhost:5555
```

## Problemes frontend

### Page blanche apres build

**Cause** : Le proxy API n'est pas configure ou le backend n'est pas demarre.

**Solution** : Verifier que le backend tourne sur le port 8000 et que `vite.config.ts` a le bon proxy.

### WebSocket ne se connecte pas

**Cause** : Le proxy WebSocket n'est pas configure.

**Verifications** :
- Ouvrir la console navigateur (F12) et verifier les erreurs WS
- Verifier que le backend est accessible
- Verifier les regles CORS

## Logs

### Ou trouver les logs ?

| Composant | Emplacement |
|-----------|-------------|
| Backend API | Sortie standard (stdout) |
| Celery workers | Sortie standard |
| Deploiements | DB (`deployment_logs` table) + API `/deployments/{id}/logs` |
| VMs Windows | `C:\VM-Automation\setup.log` (dans la VM) |
| Preseed Linux | `/var/log/syslog` (dans la VM) |
| Cloud-init | `/var/log/cloud-init.log` |
| PostgreSQL | `docker compose logs postgres` |

### Activer le mode debug

Dans `.env` :
```
DEBUG=true
LOG_LEVEL=DEBUG
```
