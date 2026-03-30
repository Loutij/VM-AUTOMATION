#!/usr/bin/env python3
"""
Script pour tester la connexion PowerShell Direct avec le nom de la VM (correctif).
"""

import asyncio
from uuid import UUID

from src.common.database import db_session
from src.domain.models import Deployment, VirtualMachine, Hypervisor
from src.integrations.hypervisors import HyperVClient


async def test_powershell_direct():
    """Teste la connexion PowerShell Direct avec le nom de la VM."""
    async with db_session() as session:
        from sqlalchemy import select
        
        # Trouver le déploiement DEMO_LATEST
        result = await session.execute(
            select(Deployment)
            .where(Deployment.vm_name == "DEMO_LATEST")
            .order_by(Deployment.created_at.desc())
        )
        deployment = result.scalar_one_or_none()
        
        if not deployment or not deployment.vm_id:
            print("❌ Déploiement ou VM non trouvé")
            return
        
        # Récupérer la VM
        vm_result = await session.execute(
            select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
        )
        vm = vm_result.scalar_one_or_none()
        
        if not vm:
            print("❌ VM non trouvée")
            return
        
        # Récupérer l'hyperviseur
        hypervisor_result = await session.execute(
            select(Hypervisor).where(Hypervisor.id == deployment.hypervisor_id)
        )
        hypervisor = hypervisor_result.scalar_one_or_none()
        
        if not hypervisor:
            print("❌ Hyperviseur non trouvé")
            return
        
        print(f"✅ VM trouvée: {vm.name}")
        print(f"   UUID: {vm.hypervisor_vm_id}")
        print(f"   État: {vm.state.value if vm.state else 'N/A'}\n")
        
        # Se connecter à l'hyperviseur
        client = HyperVClient(
            host=hypervisor.host,
            username=hypervisor.username,
            password=hypervisor.password,
            use_ssl=hypervisor.use_ssl,
        )
        
        try:
            config = deployment.config
            admin_password = config.get("admin_password", "")
            
            if not admin_password:
                print("❌ Pas de mot de passe admin dans la config")
                return
            
            # Test avec le NOM de la VM (correctif)
            print("🔍 Test PowerShell Direct avec le NOM de la VM (correctif)...")
            test_script = '$env:COMPUTERNAME'
            credentials_list = [
                ("Administrateur", admin_password),
                ("Administrator", admin_password),
            ]
            
            for username, password in credentials_list:
                try:
                    print(f"   Test avec {username}...")
                    result = await client.execute_in_vm(
                        vm.name,  # ✅ Utiliser le NOM, pas l'UUID
                        test_script,
                        (username, password),
                        timeout=30
                    )
                    if result.success:
                        print(f"   ✅ SUCCÈS avec {username}!")
                        print(f"   Hostname: {result.output}")
                        return True
                    else:
                        print(f"   ❌ Échec: {result.error}")
                except Exception as e:
                    print(f"   ❌ Exception: {e}")
            
            print("\n❌ Aucune connexion réussie")
            return False
            
        finally:
            client.close()


if __name__ == "__main__":
    success = asyncio.run(test_powershell_direct())
    exit(0 if success else 1)
