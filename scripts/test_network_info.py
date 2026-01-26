#!/usr/bin/env python3
"""
Test script pour récupérer les informations réseau d'une VM.

Usage:
    python scripts/test_network_info.py [vm_name]
"""

import asyncio
import json
import sys

# Ajouter le path du projet
sys.path.insert(0, "/home/otoroot/VM-AUTOMATION")

from src.integrations.hypervisors.hyperv_client import HyperVClient


async def main():
    vm_name = sys.argv[1] if len(sys.argv) > 1 else "WinSrv2022-Test"
    
    print(f"=" * 60)
    print(f"Test récupération infos réseau - VM: {vm_name}")
    print(f"=" * 60)
    
    # Créer le client Hyper-V
    client = HyperVClient(
        host="10.250.0.20",
        username="administrateur",
        password="1Lapins,",
        use_ssl=False,
    )
    
    try:
        # Test connexion
        print("\n[1] Test connexion Hyper-V...")
        connected = await client.test_connection()
        if not connected:
            print("❌ Connexion échouée")
            return
        print("✅ Connexion OK")
        
        # Test infos réseau basiques (sans credentials)
        print(f"\n[2] Récupération infos réseau Hyper-V (sans guest)...")
        network_info = await client.get_vm_network_info(vm_name)
        
        print(f"\n📡 VM: {network_info.vm_name}")
        print(f"\nAdaptateurs Hyper-V ({len(network_info.adapters_hyperv)}):")
        for adapter in network_info.adapters_hyperv:
            print(f"  - {adapter.name}")
            print(f"    Switch: {adapter.switch_name}")
            print(f"    MAC: {adapter.mac_address}")
            print(f"    VLAN: {adapter.vlan_id or 'None'}")
            print(f"    IPs (Hyper-V): {adapter.ip_addresses}")
        
        # Test infos réseau complètes (avec credentials)
        print(f"\n[3] Récupération infos réseau complètes (avec guest)...")
        vm_credentials = ("Administrateur", "Admin123!")
        
        full_network_info = await client.get_vm_network_info(vm_name, vm_credentials)
        
        print(f"\n📡 VM: {full_network_info.vm_name}")
        print(f"🖥️  Hostname: {full_network_info.hostname}")
        print(f"🌐 IP principale: {full_network_info.get_primary_ip()}")
        print(f"🔗 MAC principale: {full_network_info.get_primary_mac()}")
        
        print(f"\nInterfaces Guest ({len(full_network_info.interfaces_guest)}):")
        for iface in full_network_info.interfaces_guest:
            print(f"\n  📶 {iface.interface_alias}")
            print(f"     Index: {iface.interface_index}")
            print(f"     MAC: {iface.mac_address}")
            print(f"     IP: {iface.ip_address}")
            print(f"     Masque: {iface.subnet_mask} (/{iface.prefix_length})")
            print(f"     Gateway: {iface.default_gateway}")
            print(f"     DNS: {iface.dns_servers}")
            print(f"     DHCP: {'Oui' if iface.dhcp_enabled else 'Non'}")
            if iface.dhcp_server:
                print(f"     Serveur DHCP: {iface.dhcp_server}")
            print(f"     Status: {iface.connection_status}")
            print(f"     Vitesse: {iface.link_speed_mbps} Mbps")
        
        # Test résumé
        print(f"\n[4] Résumé réseau...")
        summary = await client.get_vm_network_summary(vm_name, vm_credentials)
        print(f"\n{json.dumps(summary, indent=2, ensure_ascii=False)}")
        
        print(f"\n{'=' * 60}")
        print("✅ Test terminé avec succès")
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
