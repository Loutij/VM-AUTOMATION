# HANDOFF - Transfert de Session Agent

**Date**: 2026-01-27  
**Session précédente**: Déploiement automatique Windows via DISM

---

## État Actuel du Projet

### Ce qui fonctionne ✅

1. **Déploiement DISM** (`deploy_with_dism()` dans `hyperv_client.py`)
   - Applique une image Windows directement sur le VHD via DISM
   - Partitionne automatiquement (EFI + MSR + Windows)
   - Configure le bootloader UEFI
   - **Évite le "Press any key to boot from CD or DVD"**
   - Temps de déploiement: ~90 secondes

2. **Injection Unattend** (`inject_unattend()` dans `hyperv_client.py`)
   - Crée un VHDX dédié avec `autounattend.xml`
   - Supporte le base64 chunking pour surmonter les limites WinRM

3. **Création ISO Custom** (`create_custom_iso()` dans `hyperv_client.py`)
   - Utilise `oscdimg.exe` + `efisys_noprompt.bin`
   - Windows ADK installé sur l'hyperviseur

4. **Frontend React** - 8 pages fonctionnelles
5. **Backend FastAPI** - Tous les endpoints CRUD
6. **PowerShell Direct** - Communication avec les VMs

---

## Problème Non Résolu ⚠️

### OOBE Windows (Out-of-Box Experience)

**Symptôme**: Après le déploiement DISM, Windows démarre mais reste bloqué sur l'écran OOBE qui demande des interactions manuelles (région, clavier, mot de passe admin, etc.)

**Tentatives effectuées**:

1. **Placement du unattend.xml dans plusieurs emplacements**:
   - `C:\Windows\Panther\unattend.xml`
   - `C:\Windows\System32\Sysprep\unattend.xml`
   - `C:\unattend.xml`
   - **Résultat**: Ignoré par Windows

2. **Modification du registre offline**:
   ```powershell
   reg add "HKLM\OFFLINE_SW\Microsoft\Windows\CurrentVersion\Setup\OOBE" /v OOBEInProgress /t REG_DWORD /d 0 /f
   reg add "HKLM\OFFLINE_SW\Microsoft\Windows\CurrentVersion\Setup\OOBE" /v SkipMachineOOBE /t REG_DWORD /d 1 /f
   reg add "HKLM\OFFLINE_SW\Microsoft\Windows\CurrentVersion\Setup\OOBE" /v SkipUserOOBE /t REG_DWORD /d 1 /f
   ```
   - **Résultat**: Ignoré car Windows détecte un premier boot "frais"

3. **Script SetupComplete.cmd**:
   - Placé dans `C:\Windows\Setup\Scripts\`
   - Active l'admin et configure WinRM
   - **Résultat**: S'exécute APRÈS l'OOBE (pas avant)

4. **AutoLogon via registre offline**:
   - Configuré dans `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`
   - **Résultat**: Nécessite que l'OOBE soit terminé d'abord

**Raison fondamentale**: Le déploiement DISM crée une image "neuve" qui n'a jamais été syspreppée. Windows détecte automatiquement qu'il doit passer par l'OOBE.

---

## Solutions Potentielles à Explorer

### Option 1: Image WIM pré-configurée (Recommandé)
1. Déployer une VM manuellement une fois
2. La configurer entièrement (admin, WinRM, etc.)
3. Utiliser Sysprep en mode Generalize + OOBE avec `/unattend`
4. Capturer l'image avec DISM
5. Utiliser cette image personnalisée pour tous les déploiements

```powershell
# Sur la VM template
C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown /unattend:C:\unattend.xml

# Sur l'hyperviseur - capturer
Dism /Capture-Image /ImageFile:C:\Images\CustomWindows.wim /CaptureDir:W:\ /Name:"Windows Server 2022 Custom"
```

### Option 2: WDS/MDT (Infrastructure)
- Windows Deployment Services pour le PXE boot
- Microsoft Deployment Toolkit pour l'orchestration
- 100% automatique mais nécessite infrastructure supplémentaire

### Option 3: Hybrid DISM + VNC/RDP
- Garder le déploiement DISM rapide (~90s)
- Accepter l'OOBE manuel (5 clics)
- Ou automatiser via VNC/RDP scripting

### Option 4: `/Apply-Image` avec `/UnattendFile`
```powershell
Dism /Apply-Image /ImageFile:install.wim /Index:2 /ApplyDir:W:\ /UnattendFile:C:\unattend.xml
```
- À tester: le `/UnattendFile` pendant l'apply pourrait configurer l'OOBE

---

## VM de Test Actuelle

**VM_LAB_06** sur Hyper-V 10.250.0.20
- État: Running, mais OOBE bloqué
- Config: Gen2, 2 vCPU, 4 GB RAM, 60 GB VHDX
- VHD: `C:\HyperV\VirtualHardDisks\VM_LAB_06.vhdx`
- Credentials prévus: Administrator / Admin123!
- PowerShell Direct: Ne fonctionne pas (OOBE non terminé)

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
