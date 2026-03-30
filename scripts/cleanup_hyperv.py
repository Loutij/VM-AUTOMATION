#!/usr/bin/env python3
"""
Script de nettoyage des ressources orphelines sur Hyper-V.

Ce script identifie et supprime:
- VHD/VHDX non attachés à aucune VM
- Dossiers de configuration VM orphelins

Usage:
    python scripts/cleanup_hyperv.py --dry-run    # Voir sans supprimer
    python scripts/cleanup_hyperv.py --execute    # Supprimer réellement

Requiert les variables d'environnement:
    HYPERV_HOST, HYPERV_USER, HYPERV_PASSWORD
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main(dry_run: bool = True):
    """Point d'entrée principal."""
    from dotenv import load_dotenv
    load_dotenv()
    
    from src.integrations.hypervisors.hyperv_client import HyperVClient
    
    # Configuration depuis les variables d'environnement
    host = os.getenv("HYPERV_HOST")
    user = os.getenv("HYPERV_USER")
    password = os.getenv("HYPERV_PASSWORD")
    vhdx_path = os.getenv("HYPERV_VHDX_PATH", r"C:\HyperV\VirtualHardDisks")
    vm_path = os.getenv("HYPERV_VM_PATH", r"C:\HyperV\VirtualMachines")
    
    if not all([host, user, password]):
        print("Erreur: Variables HYPERV_HOST, HYPERV_USER, HYPERV_PASSWORD requises")
        return 1
    
    print(f"=== Nettoyage Hyper-V sur {host} ===")
    print(f"Mode: {'DRY-RUN (simulation)' if dry_run else 'EXECUTE (suppression réelle)'}")
    print()
    
    client = HyperVClient(host=host, username=user, password=password, use_ssl=False)
    
    try:
        # Test de connexion
        connected = await client.test_connection()
        if not connected:
            print("❌ Impossible de se connecter à Hyper-V")
            return 1
        print("✅ Connecté à Hyper-V")
        
        # 1. Lister les VMs actives
        print("\n--- VMs actives ---")
        vms = await client.list_vms()
        active_vm_names = {vm.name for vm in vms}
        print(f"VMs actives: {len(active_vm_names)}")
        for name in sorted(active_vm_names):
            print(f"  - {name}")
        
        # 2. Lister les VHD attachés
        print("\n--- VHD attachés ---")
        attached_vhds = set()
        for vm in vms:
            vm_name = vm.name
            try:
                result = await client._execute(
                    f"Get-VMHardDiskDrive -VMName '{vm_name}' | Select-Object -ExpandProperty Path"
                )
                if result.success and result.output:
                    for line in result.output.strip().split("\n"):
                        if line.strip():
                            attached_vhds.add(line.strip().lower())
            except Exception:
                pass
        
        print(f"VHD attachés: {len(attached_vhds)}")
        
        # 3. Lister tous les VHD dans le dossier
        print(f"\n--- VHD dans {vhdx_path} ---")
        all_vhds_result = await client._execute(
            f"Get-ChildItem -Path '{vhdx_path}' -Filter '*.vhdx' -Recurse | Select-Object -ExpandProperty FullName"
        )
        
        all_vhds = set()
        if all_vhds_result.success and all_vhds_result.output:
            for line in all_vhds_result.output.strip().split("\n"):
                if line.strip():
                    all_vhds.add(line.strip())
        
        print(f"VHD trouvés: {len(all_vhds)}")
        
        # 4. Identifier les VHD orphelins
        orphan_vhds = []
        for vhd in all_vhds:
            if vhd.lower() not in attached_vhds:
                orphan_vhds.append(vhd)
        
        print(f"\n--- VHD orphelins à supprimer: {len(orphan_vhds)} ---")
        total_size_gb = 0
        for vhd in orphan_vhds:
            # Obtenir la taille
            size_result = await client._execute(
                f"(Get-Item '{vhd}').Length / 1GB"
            )
            size_gb = 0
            if size_result.success and size_result.output:
                try:
                    size_gb = float(size_result.output.strip())
                except ValueError:
                    pass
            total_size_gb += size_gb
            print(f"  - {vhd} ({size_gb:.2f} GB)")
        
        print(f"Espace total récupérable: {total_size_gb:.2f} GB")
        
        # 5. Lister les dossiers VM
        print(f"\n--- Dossiers VM dans {vm_path} ---")
        all_folders_result = await client._execute(
            f"Get-ChildItem -Path '{vm_path}' -Directory | Select-Object -ExpandProperty Name"
        )
        
        all_folders = set()
        if all_folders_result.success and all_folders_result.output:
            for line in all_folders_result.output.strip().split("\n"):
                if line.strip():
                    all_folders.add(line.strip())
        
        print(f"Dossiers trouvés: {len(all_folders)}")
        
        # 6. Identifier les dossiers orphelins
        orphan_folders = []
        for folder in all_folders:
            if folder not in active_vm_names:
                orphan_folders.append(folder)
        
        print(f"\n--- Dossiers orphelins à supprimer: {len(orphan_folders)} ---")
        for folder in sorted(orphan_folders):
            print(f"  - {folder}")
        
        # 7. Supprimer si pas dry-run
        if not dry_run:
            print("\n=== SUPPRESSION EN COURS ===")
            
            # Supprimer les VHD orphelins
            for vhd in orphan_vhds:
                print(f"Suppression VHD: {vhd}...")
                try:
                    result = await client._execute(f"Remove-Item -Path '{vhd}' -Force")
                    if result.success:
                        print(f"  ✅ Supprimé")
                    else:
                        print(f"  Erreur: {result.stderr or 'Unknown'}")
                except Exception as e:
                    print(f"  Exception: {e}")

            # Supprimer les dossiers orphelins
            for folder in orphan_folders:
                folder_path = f"{vm_path}\\{folder}"
                print(f"Suppression dossier: {folder_path}...")
                try:
                    result = await client._execute(
                        f"Remove-Item -Path '{folder_path}' -Recurse -Force"
                    )
                    if result.success:
                        print(f"  OK")
                    else:
                        print(f"  Erreur: {result.stderr or 'Unknown'}")
                except Exception as e:
                    print(f"  ❌ Exception: {e}")
            
            print("\n=== NETTOYAGE TERMINÉ ===")
        else:
            print("\n=== DRY-RUN TERMINÉ ===")
            print("Relancez avec --execute pour supprimer réellement.")
        
        return 0
        
    except Exception as e:
        import traceback
        print(f"❌ Erreur: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nettoyage des ressources Hyper-V orphelines")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Simulation sans suppression")
    group.add_argument("--execute", action="store_true", help="Suppression réelle")
    
    args = parser.parse_args()
    
    exit_code = asyncio.run(main(dry_run=args.dry_run))
    sys.exit(exit_code)
