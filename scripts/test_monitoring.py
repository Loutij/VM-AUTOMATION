#!/usr/bin/env python3
"""Test des fonctions de monitoring Hyper-V."""

import asyncio
import winrm
import json

# Connexion à Hyper-V (HTTP port 5985)
session = winrm.Session(
    'http://10.250.0.20:5985/wsman',
    auth=('administrateur', '1Lapins,'),
    transport='ntlm'
)


def run_ps(script: str) -> dict:
    """Exécute un script PowerShell et retourne le résultat."""
    result = session.run_ps(script)
    stdout = result.std_out.decode('cp1252', errors='replace')
    stderr = result.std_err.decode('cp1252', errors='replace') if result.std_err else None
    return {
        'stdout': stdout,
        'stderr': stderr,
        'status_code': result.status_code
    }


def test_get_vm_health():
    """Test: Récupérer l'état de santé complet."""
    print("\n" + "="*60)
    print("TEST: get_vm_health()")
    print("="*60)
    
    script = '''
    $vm = Get-VM -Name "WinSrv2022-Test"
    if ($vm) {
        $intServices = Get-VMIntegrationService -VM $vm | Select-Object Name, Enabled, 
            @{N='Status';E={$_.PrimaryOperationalStatus.ToString()}}
        
        $nic = Get-VMNetworkAdapter -VM $vm
        
        @{
            VMName = $vm.Name
            State = $vm.State.ToString()
            Heartbeat = $vm.Heartbeat.ToString()
            Uptime = $vm.Uptime.ToString()
            CPUUsage = $vm.CPUUsage
            MemoryMB = [math]::Round($vm.MemoryAssigned/1MB)
            IPAddresses = $nic.IPAddresses
            IntegrationServices = $intServices | ForEach-Object {
                @{
                    Name = $_.Name
                    Enabled = $_.Enabled
                    Status = $_.Status
                }
            }
        } | ConvertTo-Json -Depth 3
    }
    '''
    
    result = run_ps(script)
    if result['status_code'] == 0 and result['stdout'].strip():
        try:
            data = json.loads(result['stdout'].strip())
            print(f"VM: {data.get('VMName')}")
            print(f"State: {data.get('State')}")
            print(f"Heartbeat: {data.get('Heartbeat')}")
            print(f"Uptime: {data.get('Uptime')}")
            print(f"CPU: {data.get('CPUUsage')}%")
            print(f"Memory: {data.get('MemoryMB')} MB")
            print(f"IPs: {data.get('IPAddresses')}")
            print(f"Integration Services: {len(data.get('IntegrationServices', []))} services")
            
            # Vérifier is_healthy
            is_healthy = (
                data.get('State') == 'Running' and
                data.get('Heartbeat') in ('OkApplicationsHealthy', 'OkApplicationsUnknown', 'Ok')
            )
            print(f"\nIS HEALTHY: {is_healthy}")
            return True
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")
            print(f"Output: {result['stdout'][:500]}")
            return False
    else:
        print(f"Error: {result.get('stderr', 'Unknown error')}")
        return False


def test_get_vm_heartbeat():
    """Test: Récupérer le heartbeat."""
    print("\n" + "="*60)
    print("TEST: get_vm_heartbeat()")
    print("="*60)
    
    script = '''
    $vm = Get-VM -Name "WinSrv2022-Test"
    if ($vm) {
        Write-Output $vm.Heartbeat.ToString()
    }
    '''
    
    result = run_ps(script)
    if result['status_code'] == 0:
        heartbeat = result['stdout'].strip()
        print(f"Heartbeat: {heartbeat}")
        return True
    return False


def test_get_vm_ip():
    """Test: Récupérer les IPs."""
    print("\n" + "="*60)
    print("TEST: get_vm_ip_addresses()")
    print("="*60)
    
    script = '''
    $vm = Get-VM -Name "WinSrv2022-Test"
    if ($vm) {
        $nic = Get-VMNetworkAdapter -VM $vm
        $nic.IPAddresses | ConvertTo-Json
    }
    '''
    
    result = run_ps(script)
    if result['status_code'] == 0:
        try:
            ips = json.loads(result['stdout'].strip())
            if isinstance(ips, str):
                ips = [ips]
            print(f"IP Addresses: {ips}")
            return True
        except:
            print(f"Raw: {result['stdout']}")
            return True
    return False


def test_execute_in_vm():
    """Test: PowerShell Direct."""
    print("\n" + "="*60)
    print("TEST: execute_in_vm() - PowerShell Direct")
    print("="*60)
    
    script = '''
    $vmName = "WinSrv2022-Test"
    $cred = New-Object System.Management.Automation.PSCredential(
        "Administrateur",
        (ConvertTo-SecureString "Admin123!" -AsPlainText -Force)
    )
    
    try {
        $result = Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock {
            @{
                Hostname = $env:COMPUTERNAME
                OS = (Get-WmiObject Win32_OperatingSystem).Caption
                Uptime = ((Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime).ToString()
                Services = (Get-Service | Where-Object { $_.Status -eq "Running" }).Count
            }
        } -ErrorAction Stop
        
        @{
            Success = $true
            Output = $result
            Error = $null
        } | ConvertTo-Json -Depth 5
    } catch {
        @{
            Success = $false
            Output = $null
            Error = $_.Exception.Message
        } | ConvertTo-Json -Depth 5
    }
    '''
    
    result = run_ps(script)
    if result['status_code'] == 0:
        try:
            data = json.loads(result['stdout'].strip())
            if data.get('Success'):
                output = data.get('Output', {})
                print(f"Hostname: {output.get('Hostname')}")
                print(f"OS: {output.get('OS')}")
                print(f"Uptime: {output.get('Uptime')}")
                print(f"Running Services: {output.get('Services')}")
                print("\nPowerShell Direct: SUCCESS")
                return True
            else:
                print(f"Error: {data.get('Error')}")
                return False
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")
            return False
    return False


def main():
    print("="*60)
    print("VM AUTOMATION - TEST DES FONCTIONS DE MONITORING")
    print("="*60)
    print("VM cible: WinSrv2022-Test")
    print("Hyperviseur: 10.250.0.20")
    
    results = {
        'get_vm_health': test_get_vm_health(),
        'get_vm_heartbeat': test_get_vm_heartbeat(),
        'get_vm_ip_addresses': test_get_vm_ip(),
        'execute_in_vm': test_execute_in_vm(),
    }
    
    print("\n" + "="*60)
    print("RÉSUMÉ DES TESTS")
    print("="*60)
    
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test}: {status}")
    
    all_passed = all(results.values())
    print(f"\nRésultat global: {'✅ TOUS LES TESTS PASSENT' if all_passed else '❌ CERTAINS TESTS ONT ÉCHOUÉ'}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
