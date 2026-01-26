#!/usr/bin/env python3
"""Test des fonctions de nettoyage post-installation."""

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


def test_vm_status():
    """Affiche le statut actuel de la VM."""
    print("\n" + "="*60)
    print("ÉTAT ACTUEL DE LA VM WinSrv2022-Test")
    print("="*60)
    
    script = '''
    $vm = Get-VM -Name "WinSrv2022-Test"
    
    Write-Host "=== VM ==="
    Write-Host "State: $($vm.State)"
    Write-Host "Uptime: $($vm.Uptime)"
    
    Write-Host "`n=== LECTEURS DVD ==="
    Get-VMDvdDrive -VM $vm | ForEach-Object {
        $path = if ($_.Path) { $_.Path } else { "(vide)" }
        Write-Host "  Controller $($_.ControllerNumber):$($_.ControllerLocation) = $path"
    }
    
    Write-Host "`n=== BOOT ORDER ==="
    $firmware = Get-VMFirmware -VM $vm
    $first = $firmware.BootOrder | Select-Object -First 1
    Write-Host "  Premier: $($first.BootType) - $($first.Device)"
    
    Write-Host "`n=== GUEST SERVICES ==="
    Get-VMIntegrationService -VM $vm | Where-Object { $_.Name -like "*invit*" -or $_.Name -like "*Guest*" } | ForEach-Object {
        Write-Host "  $($_.Name): Enabled=$($_.Enabled)"
    }
    
    Write-Host "`n=== IP ADDRESSES ==="
    $nic = Get-VMNetworkAdapter -VM $vm
    Write-Host "  $($nic.IPAddresses -join ', ')"
    '''
    
    result = run_ps(script)
    print(result['stdout'])
    return True


def test_copy_file_to_vm():
    """Test de copie de fichier vers la VM via Guest Services."""
    print("\n" + "="*60)
    print("TEST: Copie de fichier via Guest Services")
    print("="*60)
    
    script = '''
    $vm = Get-VM -Name "WinSrv2022-Test"
    
    # Créer un fichier temporaire
    $tempFile = "C:\\temp_test_guest_services.txt"
    "Test Guest Services - $(Get-Date)" | Out-File $tempFile -Encoding UTF8
    
    try {
        # Copier vers la VM
        Copy-VMFile -VM $vm -SourcePath $tempFile -DestinationPath "C:\\test_from_host.txt" -CreateFullPath -FileSource Host -Force
        Write-Host "SUCCESS: Fichier copie vers la VM"
        $success = $true
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)"
        $success = $false
    }
    
    # Nettoyer
    Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
    
    if ($success) {
        # Vérifier que le fichier existe dans la VM via PowerShell Direct
        $cred = New-Object System.Management.Automation.PSCredential("Administrateur", (ConvertTo-SecureString "Admin123!" -AsPlainText -Force))
        $exists = Invoke-Command -VMName "WinSrv2022-Test" -Credential $cred -ScriptBlock {
            Test-Path "C:\\test_from_host.txt"
        }
        Write-Host "Fichier existe dans VM: $exists"
    }
    '''
    
    result = run_ps(script)
    print(result['stdout'])
    if result['stderr'] and 'CLIXML' not in result['stderr']:
        print(f"STDERR: {result['stderr']}")
    return 'SUCCESS' in result['stdout']


def test_powershell_direct_info():
    """Test PowerShell Direct pour obtenir infos système."""
    print("\n" + "="*60)
    print("TEST: Informations système via PowerShell Direct")
    print("="*60)
    
    script = '''
    $cred = New-Object System.Management.Automation.PSCredential("Administrateur", (ConvertTo-SecureString "Admin123!" -AsPlainText -Force))
    
    $info = Invoke-Command -VMName "WinSrv2022-Test" -Credential $cred -ScriptBlock {
        @{
            Hostname = $env:COMPUTERNAME
            OS = (Get-WmiObject Win32_OperatingSystem).Caption
            Architecture = $env:PROCESSOR_ARCHITECTURE
            Memory = [math]::Round((Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)
            CPU = (Get-WmiObject Win32_Processor).Name
            Disk = [math]::Round((Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='C:'").Size / 1GB, 2)
            DiskFree = [math]::Round((Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='C:'").FreeSpace / 1GB, 2)
            Uptime = ((Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime).ToString()
            Services = (Get-Service | Where-Object { $_.Status -eq "Running" }).Count
            WinRM = (Get-Service WinRM).Status
            RDP = (Get-ItemProperty "HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server").fDenyTSConnections -eq 0
        }
    }
    
    Write-Host "Hostname: $($info.Hostname)"
    Write-Host "OS: $($info.OS)"
    Write-Host "Architecture: $($info.Architecture)"
    Write-Host "Memory: $($info.Memory) GB"
    Write-Host "CPU: $($info.CPU)"
    Write-Host "Disk C: $($info.Disk) GB (Free: $($info.DiskFree) GB)"
    Write-Host "Uptime: $($info.Uptime)"
    Write-Host "Services actifs: $($info.Services)"
    Write-Host "WinRM: $($info.WinRM)"
    Write-Host "RDP: $(if ($info.RDP) { 'Enabled' } else { 'Disabled' })"
    '''
    
    result = run_ps(script)
    print(result['stdout'])
    return 'Hostname:' in result['stdout']


def main():
    print("="*60)
    print("VM AUTOMATION - TESTS POST-INSTALLATION")
    print("="*60)
    print("VM cible: WinSrv2022-Test")
    print("Hyperviseur: 10.250.0.20")
    
    results = {
        'vm_status': test_vm_status(),
        'guest_services_copy': test_copy_file_to_vm(),
        'powershell_direct': test_powershell_direct_info(),
    }
    
    print("\n" + "="*60)
    print("RÉSUMÉ DES TESTS")
    print("="*60)
    
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test}: {status}")
    
    all_passed = all(results.values())
    print(f"\nRésultat global: {'✅ TOUS LES TESTS PASSENT' if all_passed else '⚠️  CERTAINS TESTS ONT ÉCHOUÉ'}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
