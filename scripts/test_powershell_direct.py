#!/usr/bin/env python3
"""Test PowerShell Direct pour exécuter des commandes dans la VM."""

import winrm

# Connexion à Hyper-V (HTTP port 5985)
session = winrm.Session(
    'http://10.250.0.20:5985/wsman',
    auth=('administrateur', '1Lapins,'),
    transport='ntlm'
)

# Script PowerShell - PowerShell Direct
# Utilise Invoke-Command avec -VMName pour exécuter dans la VM
ps_script = '''
$vmName = "WinSrv2022-Test"
$cred = New-Object System.Management.Automation.PSCredential("Administrateur", (ConvertTo-SecureString "Admin123!" -AsPlainText -Force))

Write-Host "=== TEST POWERSHELL DIRECT ==="
Write-Host "Connexion a la VM: $vmName"

try {
    # Tester si PowerShell Direct est disponible
    $result = Invoke-Command -VMName $vmName -Credential $cred -ScriptBlock {
        @{
            Hostname = $env:COMPUTERNAME
            OS = (Get-WmiObject Win32_OperatingSystem).Caption
            Uptime = (Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
            IP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" }).IPAddress
            Services = (Get-Service | Where-Object { $_.Status -eq "Running" }).Count
        }
    } -ErrorAction Stop
    
    Write-Host "`n=== INFORMATIONS VM ==="
    Write-Host "Hostname: $($result.Hostname)"
    Write-Host "OS: $($result.OS)"
    Write-Host "Uptime: $($result.Uptime)"
    Write-Host "IP: $($result.IP -join ', ')"
    Write-Host "Services actifs: $($result.Services)"
    Write-Host "`nPowerShell Direct: OK"
} catch {
    Write-Host "Erreur PowerShell Direct: $_"
    Write-Host "`nEssai avec Test-VMNetworkAdapter..."
    
    # Alternative: vérifier via les adaptateurs réseau
    $vm = Get-VM -Name $vmName
    $nic = Get-VMNetworkAdapter -VM $vm
    Write-Host "IP via Hyper-V: $($nic.IPAddresses -join ', ')"
}
'''

print("Exécution du test PowerShell Direct...")
result = session.run_ps(ps_script)
print(result.std_out.decode('cp1252', errors='replace'))
if result.std_err and 'CLIXML' not in result.std_err.decode('cp1252', errors='replace'):
    print('STDERR:', result.std_err.decode('cp1252', errors='replace'))
