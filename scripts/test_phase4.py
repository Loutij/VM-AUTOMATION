#!/usr/bin/env python3
"""Test des fonctionnalités Phase 4 - Post-Installation."""

import winrm
import json

# Connexion à Hyper-V
session = winrm.Session(
    'http://10.250.0.20:5985/wsman',
    auth=('administrateur', '1Lapins,'),
    transport='ntlm'
)

VM_NAME = "WinSrv2022-Test"
VM_CREDS = ("Administrateur", "Admin123!")


def run_in_vm(script: str, timeout: int = 120) -> dict:
    """Exécute un script dans la VM via PowerShell Direct."""
    ps_script = f'''
    $cred = New-Object System.Management.Automation.PSCredential("{VM_CREDS[0]}", (ConvertTo-SecureString "{VM_CREDS[1]}" -AsPlainText -Force))
    Invoke-Command -VMName "{VM_NAME}" -Credential $cred -ScriptBlock {{
        {script}
    }}
    '''
    result = session.run_ps(ps_script)
    return {
        'stdout': result.std_out.decode('cp1252', errors='replace'),
        'stderr': result.std_err.decode('cp1252', errors='replace') if result.std_err else None,
        'status_code': result.status_code
    }


def test_check_windows_updates():
    """Test: Vérifier les mises à jour Windows disponibles."""
    print("\n" + "="*60)
    print("TEST: Vérification Windows Update")
    print("="*60)
    
    script = '''
    $UpdateSession = New-Object -ComObject Microsoft.Update.Session
    $UpdateSearcher = $UpdateSession.CreateUpdateSearcher()
    
    Write-Host "Recherche des mises a jour..."
    $SearchResult = $UpdateSearcher.Search("IsInstalled=0 and Type='Software'")
    
    Write-Host "Mises a jour disponibles: $($SearchResult.Updates.Count)"
    
    if ($SearchResult.Updates.Count -gt 0) {
        Write-Host "`nListe des mises a jour:"
        $SearchResult.Updates | Select-Object -First 5 | ForEach-Object {
            Write-Host "  - $($_.Title)"
        }
        if ($SearchResult.Updates.Count -gt 5) {
            Write-Host "  ... et $($SearchResult.Updates.Count - 5) autres"
        }
    }
    '''
    
    result = run_in_vm(script, timeout=180)
    print(result['stdout'])
    return 'Recherche des mises a jour' in result['stdout']


def test_configure_service():
    """Test: Configurer un service Windows."""
    print("\n" + "="*60)
    print("TEST: Configuration service Windows Update")
    print("="*60)
    
    script = '''
    # Configurer Windows Update en démarrage automatique
    $svc = Get-Service wuauserv
    Write-Host "Avant: Status=$($svc.Status), StartType=$($svc.StartType)"
    
    Set-Service -Name wuauserv -StartupType Automatic
    Start-Service wuauserv -ErrorAction SilentlyContinue
    
    $svc = Get-Service wuauserv
    Write-Host "Apres: Status=$($svc.Status), StartType=$($svc.StartType)"
    '''
    
    result = run_in_vm(script)
    print(result['stdout'])
    return 'StartType=Automatic' in result['stdout']


def test_install_ssh():
    """Test: Installer OpenSSH Server."""
    print("\n" + "="*60)
    print("TEST: Installation OpenSSH Server")
    print("="*60)
    
    script = '''
    # Vérifier si déjà installé
    $sshd = Get-Service sshd -ErrorAction SilentlyContinue
    
    if ($sshd) {
        Write-Host "OpenSSH Server deja installe"
        Write-Host "Status: $($sshd.Status)"
        Write-Host "StartType: $($sshd.StartType)"
    } else {
        Write-Host "Installation OpenSSH Server..."
        
        # Vérifier la capacité disponible
        $capability = Get-WindowsCapability -Online | Where-Object { $_.Name -like "OpenSSH.Server*" }
        Write-Host "Capability: $($capability.Name) - State: $($capability.State)"
        
        if ($capability.State -ne "Installed") {
            Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
            Write-Host "Installation terminee"
        }
        
        Set-Service -Name sshd -StartupType Automatic
        Start-Service sshd
        
        $sshd = Get-Service sshd
        Write-Host "Status: $($sshd.Status)"
    }
    
    # Vérifier le firewall
    $rule = Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue
    if ($rule) {
        Write-Host "Firewall rule: Existe (Enabled=$($rule.Enabled))"
    } else {
        New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
        Write-Host "Firewall rule: Creee"
    }
    '''
    
    result = run_in_vm(script, timeout=300)
    print(result['stdout'])
    return 'Status: Running' in result['stdout'] or 'deja installe' in result['stdout']


def test_password_policy():
    """Test: Vérifier les politiques de mot de passe."""
    print("\n" + "="*60)
    print("TEST: Politiques de mot de passe")
    print("="*60)
    
    script = '''
    Write-Host "=== Politiques actuelles ==="
    net accounts
    '''
    
    result = run_in_vm(script)
    print(result['stdout'])
    return 'Minimum password length' in result['stdout'] or 'longueur' in result['stdout'].lower()


def test_firewall_status():
    """Test: Vérifier l'état du firewall."""
    print("\n" + "="*60)
    print("TEST: État du firewall Windows")
    print("="*60)
    
    script = '''
    Write-Host "=== Profils Firewall ==="
    Get-NetFirewallProfile | ForEach-Object {
        Write-Host "$($_.Name): Enabled=$($_.Enabled)"
    }
    
    Write-Host "`n=== Regles entrantes actives (port specifique) ==="
    Get-NetFirewallRule -Direction Inbound -Enabled True | 
        Get-NetFirewallPortFilter | 
        Where-Object { $_.LocalPort -ne "Any" } | 
        Select-Object -First 10 | ForEach-Object {
            $rule = Get-NetFirewallRule -AssociatedNetFirewallPortFilter $_
            Write-Host "  $($rule.DisplayName): Port $($_.LocalPort)/$($_.Protocol)"
        }
    '''
    
    result = run_in_vm(script)
    print(result['stdout'])
    return 'Enabled=True' in result['stdout']


def test_system_info():
    """Test: Récupérer les informations système."""
    print("\n" + "="*60)
    print("TEST: Informations système complètes")
    print("="*60)
    
    script = '''
    $os = Get-WmiObject Win32_OperatingSystem
    $cs = Get-WmiObject Win32_ComputerSystem
    $cpu = Get-WmiObject Win32_Processor
    $disk = Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='C:'"
    
    Write-Host "Hostname: $env:COMPUTERNAME"
    Write-Host "OS: $($os.Caption)"
    Write-Host "Version: $($os.Version)"
    Write-Host "Domain: $($cs.Domain)"
    Write-Host "PartOfDomain: $($cs.PartOfDomain)"
    Write-Host "Memory: $([math]::Round($cs.TotalPhysicalMemory / 1GB, 2)) GB"
    Write-Host "CPU: $($cpu.Name)"
    Write-Host "Disk C: $([math]::Round($disk.Size / 1GB, 2)) GB (Free: $([math]::Round($disk.FreeSpace / 1GB, 2)) GB)"
    Write-Host "Uptime: $((Get-Date) - $os.ConvertToDateTime($os.LastBootUpTime))"
    
    # Services importants
    Write-Host "`n=== Services ==="
    @("wuauserv", "WinRM", "sshd", "TermService") | ForEach-Object {
        $svc = Get-Service $_ -ErrorAction SilentlyContinue
        if ($svc) {
            Write-Host "  $($_): $($svc.Status)"
        } else {
            Write-Host "  $($_): Non installe"
        }
    }
    
    # Vérifier si reboot nécessaire
    $pendingReboot = Test-Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired"
    Write-Host "`nReboot requis: $pendingReboot"
    '''
    
    result = run_in_vm(script, timeout=60)
    print(result['stdout'])
    return 'Hostname:' in result['stdout']


def main():
    print("="*60)
    print("VM AUTOMATION - TESTS PHASE 4 (POST-INSTALLATION)")
    print("="*60)
    print(f"VM cible: {VM_NAME}")
    print("Hyperviseur: 10.250.0.20")
    
    results = {
        'system_info': test_system_info(),
        'windows_update': test_check_windows_updates(),
        'configure_service': test_configure_service(),
        'ssh_install': test_install_ssh(),
        'password_policy': test_password_policy(),
        'firewall_status': test_firewall_status(),
    }
    
    print("\n" + "="*60)
    print("RÉSUMÉ DES TESTS PHASE 4")
    print("="*60)
    
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test}: {status}")
    
    passed_count = sum(results.values())
    total_count = len(results)
    
    print(f"\nRésultat: {passed_count}/{total_count} tests passés")
    
    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    exit(main())
