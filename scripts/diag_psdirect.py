#!/usr/bin/env python3
"""Diagnose PowerShell Direct connectivity to win11 VM on Hyper-V host."""

import winrm
import sys

HOST = "10.250.0.20"
USER = "administrateur"
PASSWORD = "1Lapins,"

def run_ps(session, label, script, timeout=60):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    try:
        result = session.run_ps(script)
        stdout = result.std_out.decode('utf-8', errors='replace').strip()
        stderr = result.std_err.decode('utf-8', errors='replace').strip()
        if stdout:
            print(f"STDOUT:\n{stdout}")
        if stderr:
            print(f"STDERR:\n{stderr}")
        if result.status_code != 0:
            print(f"EXIT CODE: {result.status_code}")
        if not stdout and not stderr:
            print("(no output)")
    except Exception as e:
        print(f"ERROR: {e}")

def main():
    print(f"Connecting to {HOST} as {USER}...")
    session = winrm.Session(
        f"http://{HOST}:5985/wsman",
        auth=(USER, PASSWORD),
        transport="ntlm",
        server_cert_validation="ignore",
        operation_timeout_sec=120,
        read_timeout_sec=130,
    )

    # Test connection
    run_ps(session, "Test Connection", "Write-Output 'Connected OK'")

    # 1. Check VM integration services
    run_ps(session, "VM Integration Services", r"""
Get-VM -Name 'win11' | Get-VMIntegrationService | Format-Table Name, Enabled, PrimaryStatusDescription -AutoSize
""")

    # 2. Check VM heartbeat and state
    run_ps(session, "VM State & Heartbeat", r"""
Get-VM -Name 'win11' | Select-Object Name, State, Heartbeat, Version | Format-List
""")

    # 3. PowerShell Direct with otoroot
    run_ps(session, "PowerShell Direct (otoroot)", r"""
$cred = New-Object System.Management.Automation.PSCredential('otoroot', (ConvertTo-SecureString 'tooroto' -AsPlainText -Force))
try {
    Invoke-Command -VMName 'win11' -Credential $cred -ScriptBlock { hostname } -ErrorAction Stop
    Write-Output "PowerShell Direct: SUCCESS"
} catch {
    Write-Output "PowerShell Direct FAILED: $_"
}
""", timeout=120)

    # 4. PowerShell Direct with Administrateur
    run_ps(session, "PowerShell Direct (Administrateur)", r"""
$cred2 = New-Object System.Management.Automation.PSCredential('Administrateur', (ConvertTo-SecureString 'tooroto' -AsPlainText -Force))
try {
    Invoke-Command -VMName 'win11' -Credential $cred2 -ScriptBlock { hostname } -ErrorAction Stop
    Write-Output "PowerShell Direct (Administrateur): SUCCESS"
} catch {
    Write-Output "PowerShell Direct (Administrateur) FAILED: $_"
}
""", timeout=120)

    # 5. Guest Service Interface (French name)
    run_ps(session, "Guest Service Interface (FR)", r"""
$svc = Get-VM -Name 'win11' | Get-VMIntegrationService -Name 'Interface de service invité' -ErrorAction SilentlyContinue
if ($svc) { $svc | Format-List } else { Write-Output 'Service not found by French name' }
""")

    # 6. Guest Service Interface (English name)
    run_ps(session, "Guest Service Interface (EN)", r"""
$svc = Get-VM -Name 'win11' | Get-VMIntegrationService -Name 'Guest Service Interface' -ErrorAction SilentlyContinue
if ($svc) { $svc | Format-List } else { Write-Output 'Service not found by English name' }
""")

    # 7. Extra: check if VM is gen2 and check network
    run_ps(session, "VM Generation & Network", r"""
Get-VM -Name 'win11' | Select-Object Name, Generation, DynamicMemoryEnabled, MemoryAssigned | Format-List
Get-VMNetworkAdapter -VMName 'win11' | Select-Object Name, SwitchName, IPAddresses, Status | Format-List
""")

    print(f"\n{'='*60}")
    print("  Diagnostics complete.")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
