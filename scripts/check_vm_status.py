#!/usr/bin/env python3
"""Script pour vérifier l'état de la VM et ses services d'intégration."""

import winrm

# Connexion à Hyper-V (HTTP port 5985)
session = winrm.Session(
    'http://10.250.0.20:5985/wsman',
    auth=('administrateur', '1Lapins,'),
    transport='ntlm'
)

# Script PowerShell
ps_script = '''
$vm = Get-VM -Name "WinSrv2022-Test"
if ($vm) {
    Write-Host "=== ETAT VM ==="
    $vm | Select-Object Name, State, Status, Uptime, CPUUsage, 
        @{N="HeartBeat";E={$_.Heartbeat}}, 
        @{N="MemoryMB";E={[math]::Round($_.MemoryAssigned/1MB)}} | Format-List
    
    Write-Host "`n=== SERVICES D INTEGRATION ==="
    Get-VMIntegrationService -VM $vm | Select-Object Name, Enabled, 
        @{N="Status";E={$_.PrimaryOperationalStatus}} | Format-Table -AutoSize
        
    Write-Host "`n=== ADRESSES IP ==="
    $vm | Get-VMNetworkAdapter | Select-Object IPAddresses | Format-List
} else {
    Write-Host "VM WinSrv2022-Test non trouvee"
}
'''

result = session.run_ps(ps_script)
print(result.std_out.decode('cp1252', errors='replace'))
if result.std_err:
    print('STDERR:', result.std_err.decode('cp1252', errors='replace'))
