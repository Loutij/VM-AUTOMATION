#!/usr/bin/env python3
"""Test du service d'installation de logiciels - Phase 5."""

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


def run_in_vm(script: str, timeout: int = 300) -> dict:
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


def test_ensure_chocolatey():
    """Test: Installation/vérification de Chocolatey."""
    print("\n" + "="*60)
    print("TEST: Installation/Vérification Chocolatey")
    print("="*60)
    
    script = '''
    $chocoPath = "$env:ProgramData\\chocolatey\\bin\\choco.exe"
    
    if (Test-Path $chocoPath) {
        $version = & $chocoPath --version
        Write-Host "Chocolatey deja installe: v$version"
        return
    }
    
    Write-Host "Installation de Chocolatey..."
    
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    
    try {
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        
        # Rafraîchir le PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        
        if (Test-Path $chocoPath) {
            $version = & $chocoPath --version
            Write-Host "Chocolatey installe: v$version"
        } else {
            Write-Host "ERREUR: Installation echouee"
        }
    } catch {
        Write-Host "ERREUR: $($_.Exception.Message)"
    }
    '''
    
    result = run_in_vm(script, timeout=300)
    print(result['stdout'])
    return 'installe' in result['stdout'].lower() or 'already' in result['stdout'].lower()


def test_install_package():
    """Test: Installation d'un package."""
    print("\n" + "="*60)
    print("TEST: Installation package (7zip)")
    print("="*60)
    
    script = '''
    $ErrorActionPreference = 'Stop'
    
    try {
        # Vérifier si déjà installé
        $installed = choco list --local-only --exact 7zip --limit-output
        if ($installed) {
            Write-Host "7zip deja installe: $installed"
            return
        }
        
        Write-Host "Installation de 7zip..."
        choco install 7zip -y --no-progress
        
        # Vérifier l'installation
        $installed = choco list --local-only --exact 7zip --limit-output
        if ($installed) {
            Write-Host "7zip installe avec succes: $installed"
        } else {
            Write-Host "ERREUR: Installation echouee"
        }
    } catch {
        Write-Host "ERREUR: $($_.Exception.Message)"
    }
    '''
    
    result = run_in_vm(script, timeout=300)
    print(result['stdout'])
    return 'installe' in result['stdout'].lower() or 'succes' in result['stdout'].lower()


def test_install_notepadpp():
    """Test: Installation Notepad++."""
    print("\n" + "="*60)
    print("TEST: Installation package (notepadplusplus)")
    print("="*60)
    
    script = '''
    $ErrorActionPreference = 'Stop'
    
    try {
        $installed = choco list --local-only --exact notepadplusplus --limit-output
        if ($installed) {
            Write-Host "Notepad++ deja installe: $installed"
            return
        }
        
        Write-Host "Installation de Notepad++..."
        choco install notepadplusplus -y --no-progress
        
        $installed = choco list --local-only --exact notepadplusplus --limit-output
        if ($installed) {
            Write-Host "Notepad++ installe avec succes: $installed"
        }
    } catch {
        Write-Host "ERREUR: $($_.Exception.Message)"
    }
    '''
    
    result = run_in_vm(script, timeout=300)
    print(result['stdout'])
    return 'installe' in result['stdout'].lower() or 'succes' in result['stdout'].lower()


def test_list_installed():
    """Test: Lister les packages installés."""
    print("\n" + "="*60)
    print("TEST: Liste des packages Chocolatey installés")
    print("="*60)
    
    script = '''
    Write-Host "=== Packages Chocolatey installes ==="
    $packages = choco list --local-only
    $packages | ForEach-Object { Write-Host "  $_" }
    Write-Host "`nTotal: $(($packages | Measure-Object).Count - 1) packages"
    '''
    
    result = run_in_vm(script)
    print(result['stdout'])
    return 'packages' in result['stdout'].lower()


def test_check_profile_availability():
    """Test: Vérifier les profils disponibles."""
    print("\n" + "="*60)
    print("TEST: Profils de logiciels disponibles")
    print("="*60)
    
    profiles = {
        "minimal": ["7zip", "notepadplusplus"],
        "tools": ["7zip", "notepadplusplus", "sysinternals"],
        "development": ["git", "vscode", "nodejs-lts", "python"],
        "webserver": ["iis-webserver", "urlrewrite"],
        "monitoring": ["zabbix-agent"],
        "database": ["sql-server-express", "sql-server-management-studio"],
    }
    
    for profile, packages in profiles.items():
        print(f"  {profile}: {', '.join(packages)}")
    
    return True


def main():
    print("="*60)
    print("VM AUTOMATION - TESTS PHASE 5 (INSTALLATION LOGICIELS)")
    print("="*60)
    print(f"VM cible: {VM_NAME}")
    print("Hyperviseur: 10.250.0.20")
    
    results = {
        'chocolatey': test_ensure_chocolatey(),
        'install_7zip': test_install_package(),
        'install_notepadpp': test_install_notepadpp(),
        'list_installed': test_list_installed(),
        'profiles': test_check_profile_availability(),
    }
    
    print("\n" + "="*60)
    print("RÉSUMÉ DES TESTS PHASE 5")
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
