# HANDOFF - Transfert de Session Agent

**Date**: 2026-01-27  
**Session précédente**: Déploiement automatique Windows via DISM - OOBE BYPASS RÉSOLU

---

## État Actuel du Projet

### Ce qui fonctionne ✅

1. **Déploiement DISM** (`deploy_with_dism()` dans `hyperv_client.py`)
   - Applique une image Windows directement sur le VHD via DISM
   - Partitionne automatiquement (EFI + MSR + Windows)
   - Configure le bootloader UEFI
   - **Évite le "Press any key to boot from CD or DVD"**
   - Temps de déploiement: ~2-2.5 minutes

2. **OOBE Bypass RÉSOLU** ✅
   - Le namespace `wcm` a été ajouté au template unattend.xml
   - Fichier unattend.xml placé dans tous les emplacements possibles
   - Configuration du registre offline pour bypass OOBE
   - **Windows boot directement au bureau sans interaction manuelle**

3. **Injection Unattend** (`inject_unattend()` dans `hyperv_client.py`)
   - Crée un VHDX dédié avec `autounattend.xml`
   - Supporte le base64 chunking pour surmonter les limites WinRM

4. **Création ISO Custom** (`create_custom_iso()` dans `hyperv_client.py`)
   - Utilise `oscdimg.exe` + `efisys_noprompt.bin`
   - Windows ADK installé sur l'hyperviseur

5. **Frontend React** - 8 pages fonctionnelles
6. **Backend FastAPI** - Tous les endpoints CRUD
7. **Screenshot VM** - Capture d'écran en temps réel via `get_vm_screenshot()`

---

## Problème Partiellement Résolu ⚠️

### Mot de passe Administrator

**Symptôme**: Après le déploiement DISM, Windows boot au bureau mais le mot de passe Administrator n'est pas configuré correctement pour PowerShell Direct.

**Ce qui a été tenté**:

1. **Configuration via unattend.xml `<AdministratorPassword>`**
   - Résultat: Non appliqué pour image DISM (non syspreppée)

2. **FirstLogonCommands avec `net user Administrator "password"`**
   - Résultat: Ne s'exécute pas car pas de "premier logon" réel

3. **SetupComplete.cmd**
   - Placé dans `C:\Windows\Setup\Scripts\`
   - Contient `net user Administrator "Admin123!" /active:yes`
   - Résultat: Semble ne pas s'exécuter ou échouer

4. **Configuration AutoLogon via registre offline**
   - Résultat: AutoLogon fonctionne (LogonCount=1) puis session se termine

**Raison fondamentale**: Pour une image DISM non-syspreppée, les mécanismes FirstLogonCommands et `<AdministratorPassword>` ne fonctionnent pas comme avec une installation normale depuis ISO.

---

## Solutions pour le Mot de Passe

### Option 1: Image WIM pré-configurée avec Sysprep (Recommandé)
1. Déployer une VM avec DISM une fois
2. Se connecter manuellement et configurer :
   - Mot de passe Administrator
   - WinRM activé
   - Tout autre configuration nécessaire
3. Utiliser Sysprep en mode Generalize + OOBE avec `/unattend`
4. Capturer l'image avec DISM
5. Utiliser cette image personnalisée pour tous les futurs déploiements

```powershell
# Sur la VM template, après configuration
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown /unattend:C:\unattend.xml

# Sur l'hyperviseur - capturer l'image
Dism /Capture-Image /ImageFile:C:\Images\CustomWindows.wim /CaptureDir:W:\ /Name:"Windows Server 2022 Custom"
```

### Option 2: Configuration manuelle initiale
- Le déploiement DISM est rapide (~2 min)
- Windows boot directement au bureau (OOBE bypassé)
- Première connexion : définir le mot de passe Administrator
- PowerShell Direct fonctionne ensuite

### Option 3: Modifier le hash du mot de passe dans le registre SAM offline
- Complexe car Windows utilise des hashes NT
- Nécessite des outils spécialisés (chntpw, etc.)
- Non recommandé pour production

---

## VMs de Test Actuelles

### VM_LAB_08 et VM_LAB_09 sur Hyper-V 10.250.0.20

**État**: Running, OOBE bypassé, Windows au bureau
- Config: Gen2, 2 vCPU, 4 GB RAM, 60 GB VHDX
- Credentials: Administrator / mot de passe à définir manuellement
- PowerShell Direct: Ne fonctionne pas (mot de passe non configuré)
- Screenshot VM: Fonctionnel via `get_vm_screenshot()`

**Pour configurer le mot de passe manuellement**:
1. Se connecter via Hyper-V Manager (Enhanced Session) ou console
2. Cliquer sur l'écran de verrouillage
3. Définir le mot de passe Administrator
4. PowerShell Direct fonctionnera ensuite

---

## Fichiers Clés Modifiés

### `src/integrations/hypervisors/hyperv_client.py`

Méthodes principales:

```python
# Déploiement DISM (fonctionne pour l'installation)
async def deploy_with_dism(self, vm_id: str, iso_path: str, vhd_path: str, 
                           image_index: int = 2, unattend_content: str | None = None) -> bool

# Injection unattend via VHDX dédié
async def inject_unattend(self, vm_id: str, unattend_content: str) -> bool

# Création ISO custom (avec efisys_noprompt.bin)
async def create_custom_iso(self, source_iso: str, target_iso: str, 
                            autounattend_content: str) -> bool
```

### `src/domain/deployment_service.py`

Le service appelle `deploy_with_dism()` ou `inject_unattend()` selon la configuration.

### `templates/unattend/windows_server_2022.xml`

Template Jinja2 complet avec:
- Phase windowsPE (partitionnement, image selection)
- Phase specialize (hostname, timezone, RDP)
- Phase oobeSystem (admin password, AutoLogon, WinRM)

---

## Commandes Utiles

```bash
# Tester la connexion VM
cd /home/otoroot/VM-AUTOMATION && . .venv/bin/activate
python3 -c "
import asyncio
from src.integrations.hypervisors.hyperv_client import HyperVClient
async def test():
    c = HyperVClient()
    r = await c._execute(\"Get-VM -Name 'VM_LAB_06' | Select State, Uptime\")
    print(r.output)
    c.close()
asyncio.run(test())
"

# Screenshot VM
python3 scripts/check_vm_status.py

# Supprimer et recréer la VM
python3 -c "
import asyncio
from src.integrations.hypervisors.hyperv_client import HyperVClient
async def cleanup():
    c = HyperVClient()
    await c._execute(\"Stop-VM 'VM_LAB_06' -Force -TurnOff -ErrorAction SilentlyContinue\")
    await c._execute(\"Remove-VM 'VM_LAB_06' -Force -ErrorAction SilentlyContinue\")
    await c._execute(\"Remove-Item 'C:\\HyperV\\VirtualHardDisks\\VM_LAB_06.vhdx' -Force -ErrorAction SilentlyContinue\")
    c.close()
asyncio.run(cleanup())
"
```

---

## Prochaines Étapes Recommandées

1. **Créer une image WIM personnalisée** avec Sysprep + unattend intégré
2. Modifier `deploy_with_dism()` pour utiliser cette image custom
3. Tester le déploiement end-to-end
4. Mettre à jour la documentation

---

## ClickUp

- **Task ID**: 869bxaf8k
- **Dernier statut**: in progress
- **Commentaires**: Déploiement DISM implémenté, OOBE automation en cours

---

## Git

Tout est pushé. Branch: `main`

```bash
git log --oneline -5
# Vérifier les derniers commits
```

---

*Document créé pour faciliter la reprise par un autre agent*
