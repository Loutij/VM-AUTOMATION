#!/usr/bin/env python3
"""
Script pour vérifier l'état réel de la VM DEMO_LATEST sur l'hyperviseur.
"""

import asyncio
import json
from uuid import UUID

from src.common.database import db_session
from src.domain.models import Deployment, VirtualMachine, Hypervisor
from src.integrations.hypervisors import HyperVClient


async def check_vm_status():
    """Vérifie l'état réel de la VM DEMO_LATEST."""
    async with db_session() as session:
        # Trouver le déploiement
        from sqlalchemy import select
        result = await session.execute(
            select(Deployment)
            .where(Deployment.vm_name == "DEMO_LATEST")
            .order_by(Deployment.created_at.desc())
        )
        deployment = result.scalar_one_or_none()
        
        if not deployment:
            print("❌ Déploiement DEMO_LATEST non trouvé")
            return
        
        print(f"✅ Déploiement trouvé: {deployment.id}")
        print(f"   Status: {deployment.status.value}")
        print(f"   Current Step: {deployment.current_step}")
        print(f"   VM ID: {deployment.vm_id}\n")
        
        if not deployment.vm_id:
            print("❌ Aucune VM associée au déploiement")
            return
        
        # Récupérer la VM
        vm_result = await session.execute(
            select(VirtualMachine).where(VirtualMachine.id == deployment.vm_id)
        )
        vm = vm_result.scalar_one_or_none()
        
        if not vm:
            print("❌ VM non trouvée en base de données")
            return
        
        print(f"✅ VM trouvée en base:")
        print(f"   Name: {vm.name}")
        print(f"   State: {vm.state.value if vm.state else 'N/A'}")
        print(f"   Status: {vm.status.value if vm.status else 'N/A'}")
        print(f"   Hypervisor VM ID: {vm.hypervisor_vm_id}\n")
        
        # Récupérer l'hyperviseur
        hypervisor_result = await session.execute(
            select(Hypervisor).where(Hypervisor.id == deployment.hypervisor_id)
        )
        hypervisor = hypervisor_result.scalar_one_or_none()
        
        if not hypervisor:
            print("❌ Hyperviseur non trouvé")
            return
        
        print(f"✅ Hyperviseur trouvé:")
        print(f"   Name: {hypervisor.name}")
        print(f"   Host: {hypervisor.host}\n")
        
        # Se connecter à l'hyperviseur et vérifier l'état réel
        print("🔍 Vérification de l'état réel sur l'hyperviseur...\n")
        
        client = HyperVClient(
            host=hypervisor.host,
            username=hypervisor.username,
            password=hypervisor.password,
            use_ssl=hypervisor.use_ssl,
        )
        
        try:
            vm_identifier = vm.hypervisor_vm_id or vm.name
            
            # 1. Vérifier si la VM existe
            print("1. Vérification de l'existence de la VM...")
            try:
                hyperv_vm = await client.get_vm(vm_identifier)
                if hyperv_vm:
                    print(f"   ✅ VM trouvée sur l'hyperviseur")
                    print(f"   State: {hyperv_vm.get('state', 'N/A')}")
                    print(f"   Status: {hyperv_vm.get('status', 'N/A')}")
                else:
                    print(f"   ❌ VM non trouvée sur l'hyperviseur")
            except Exception as e:
                print(f"   ❌ Erreur: {e}")
            
            print()
            
            # 2. Vérifier le heartbeat
            print("2. Vérification du heartbeat...")
            try:
                heartbeat = await client.get_vm_heartbeat(vm_identifier)
                print(f"   Heartbeat: {heartbeat}")
                if heartbeat and heartbeat not in ("NoContact", "None", None, ""):
                    print(f"   ✅ Windows semble démarré")
                else:
                    print(f"   ⚠️  Windows peut ne pas être démarré")
            except Exception as e:
                print(f"   ❌ Erreur: {e}")
            
            print()
            
            # 3. Vérifier l'IP
            print("3. Vérification de l'adresse IP...")
            try:
                vm_ips = await client.get_vm_ip_addresses(vm_identifier)
                valid_ips = [ip for ip in vm_ips if ip and not ip.startswith("169.254.") and not ip.startswith("fe80:")]
                if valid_ips:
                    print(f"   ✅ IP valide: {valid_ips[0]}")
                    if len(valid_ips) > 1:
                        print(f"   Autres IPs: {valid_ips[1:]}")
                else:
                    print(f"   ⚠️  Aucune IP valide trouvée")
                    if vm_ips:
                        print(f"   IPs trouvées: {vm_ips}")
            except Exception as e:
                print(f"   ❌ Erreur: {e}")
            
            print()
            
            # 4. Tester PowerShell Direct
            print("4. Test de connexion PowerShell Direct...")
            config = deployment.config
            admin_password = config.get("admin_password", "")
            
            if admin_password:
                test_script = '$env:COMPUTERNAME'
                credentials_list = [
                    ("Administrateur", admin_password),
                    ("Administrator", admin_password),
                ]
                
                for username, password in credentials_list:
                    try:
                        result = await client.execute_in_vm(
                            vm_identifier, test_script, (username, password), timeout=30
                        )
                        if result.success:
                            print(f"   ✅ Connexion réussie avec {username}")
                            print(f"   Hostname: {result.output}")
                            break
                        else:
                            print(f"   ❌ Échec avec {username}: {result.error}")
                    except Exception as e:
                        print(f"   ❌ Erreur avec {username}: {e}")
            else:
                print("   ⚠️  Pas de mot de passe admin dans la config")
            
            print()
            
            # 5. Vérifier le fichier ready.flag
            print("5. Vérification du fichier ready.flag...")
            if admin_password:
                flag_script = 'if (Test-Path "C:\\VM-Automation\\ready.flag") { "FLAG_FOUND" } else { "FLAG_NOT_FOUND" }'
                credentials_list = [
                    ("Administrateur", admin_password),
                    ("Administrator", admin_password),
                ]
                
                for username, password in credentials_list:
                    try:
                        result = await client.execute_in_vm(
                            vm_identifier, flag_script, (username, password), timeout=30
                        )
                        if result.success:
                            output = str(result.output).strip()
                            if "FLAG_FOUND" in output:
                                print(f"   ✅ ready.flag trouvé (connexion avec {username})")
                            else:
                                print(f"   ⚠️  ready.flag non trouvé (connexion avec {username})")
                            break
                        else:
                            print(f"   ❌ Échec avec {username}: {result.error}")
                    except Exception as e:
                        print(f"   ❌ Erreur avec {username}: {e}")
            
        finally:
            client.close()


if __name__ == "__main__":
    asyncio.run(check_vm_status())
