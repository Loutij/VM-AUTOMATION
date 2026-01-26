# Installation Automatique Windows - Guide Technique

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  ISO Windows Original (5 GB)                 │
│                 Stocké UNE FOIS sur l'hyperviseur           │
│                 Partagé par toutes les VMs                   │
│                 Ex: C:\HyperV\ISOs\WinSrv2022_FR.iso        │
└─────────────────────────────────────────────────────────────┘
                              +
┌─────────────────────────────────────────────────────────────┐
│                  ISO OEMDRV (~400 KB)                        │
│                 Généré DYNAMIQUEMENT par déploiement        │
│                 Contient uniquement autounattend.xml        │
│                 Label obligatoire: "OEMDRV"                  │
└─────────────────────────────────────────────────────────────┘
```

## Pourquoi OEMDRV ?

Windows Setup recherche automatiquement `autounattend.xml` dans cet ordre :
1. Registre (HKLM)
2. Disquette (non supporté Gen2)
3. **Lecteur amovible avec label "OEMDRV"** ← Notre méthode
4. Média d'installation (DVD Windows)
5. Dossier \Sources du média

## Génération de l'ISO OEMDRV

### Depuis Linux (genisoimage)

```bash
# 1. Créer le dossier avec autounattend.xml
mkdir -p /tmp/oemdrv_content
cp autounattend.xml /tmp/oemdrv_content/

# 2. Créer l'ISO avec le label OEMDRV (OBLIGATOIRE)
genisoimage -V "OEMDRV" -J -r -o /tmp/oemdrv.iso /tmp/oemdrv_content/

# Résultat: ~374 KB
```

### Depuis Windows (oscdimg - nécessite Windows ADK)

```powershell
# Si Windows ADK installé
$oscdimg = "C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\oscdimg.exe"
& $oscdimg -l"OEMDRV" -j1 C:\temp\oemdrv_content C:\HyperV\ISOs\oemdrv.iso
```

## Configuration VM Hyper-V

### PowerShell - Configurer les 2 DVDs

```powershell
$VMName = "MaVM"
$WinISO = "C:\HyperV\ISOs\WinSrv2022_FR.iso"
$OemISO = "C:\HyperV\ISOs\oemdrv.iso"

# Supprimer DVDs existants
Get-VMDvdDrive -VMName $VMName | Remove-VMDvdDrive

# Ajouter DVD 1: Windows (boot)
Add-VMDvdDrive -VMName $VMName -ControllerNumber 0 -ControllerLocation 1 -Path $WinISO

# Ajouter DVD 2: OEMDRV (autounattend)
Add-VMDvdDrive -VMName $VMName -ControllerNumber 0 -ControllerLocation 2 -Path $OemISO

# Configurer boot sur DVD Windows
$dvd = Get-VMDvdDrive -VMName $VMName | Where-Object { $_.Path -like "*WinSrv*" }
Set-VMFirmware -VMName $VMName -FirstBootDevice $dvd
```

### Problème "Press any key to boot from CD or DVD"

Windows attend une touche au boot. Solution : envoyer des touches via WMI.

```powershell
$vm = Get-WmiObject -Namespace "root\virtualization\v2" -Class "Msvm_ComputerSystem" | 
      Where-Object { $_.ElementName -eq $VMName }
$keyboard = $vm.GetRelated("Msvm_Keyboard")

# Envoyer Enter (scancode 0x1C down, 0x9C up) en boucle
for ($i = 0; $i -lt 30; $i++) {
    $keyboard.TypeScancodes(@(0x1C, 0x9C)) | Out-Null
    Start-Sleep -Milliseconds 500
}
```

## Template autounattend.xml (Windows Server 2022)

```xml
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend" 
          xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">

<!-- Phase WindowsPE: Partitionnement + Sélection image -->
<settings pass="windowsPE">
  <component name="Microsoft-Windows-International-Core-WinPE" 
             processorArchitecture="amd64" 
             publicKeyToken="31bf3856ad364e35" 
             language="neutral" versionScope="nonSxS">
    <SetupUILanguage><UILanguage>fr-FR</UILanguage></SetupUILanguage>
    <InputLocale>fr-FR</InputLocale>
    <SystemLocale>fr-FR</SystemLocale>
    <UILanguage>fr-FR</UILanguage>
    <UserLocale>fr-FR</UserLocale>
  </component>
  
  <component name="Microsoft-Windows-Setup" 
             processorArchitecture="amd64" 
             publicKeyToken="31bf3856ad364e35" 
             language="neutral" versionScope="nonSxS">
    
    <!-- Partitionnement GPT/UEFI -->
    <DiskConfiguration>
      <Disk wcm:action="add">
        <DiskID>0</DiskID>
        <WillWipeDisk>true</WillWipeDisk>
        <CreatePartitions>
          <CreatePartition wcm:action="add">
            <Order>1</Order><Size>300</Size><Type>EFI</Type>
          </CreatePartition>
          <CreatePartition wcm:action="add">
            <Order>2</Order><Size>128</Size><Type>MSR</Type>
          </CreatePartition>
          <CreatePartition wcm:action="add">
            <Order>3</Order><Extend>true</Extend><Type>Primary</Type>
          </CreatePartition>
        </CreatePartitions>
        <ModifyPartitions>
          <ModifyPartition wcm:action="add">
            <Order>1</Order><PartitionID>1</PartitionID>
            <Format>FAT32</Format><Label>System</Label>
          </ModifyPartition>
          <ModifyPartition wcm:action="add">
            <Order>2</Order><PartitionID>2</PartitionID>
          </ModifyPartition>
          <ModifyPartition wcm:action="add">
            <Order>3</Order><PartitionID>3</PartitionID>
            <Format>NTFS</Format><Label>Windows</Label><Letter>C</Letter>
          </ModifyPartition>
        </ModifyPartitions>
      </Disk>
    </DiskConfiguration>
    
    <!-- Sélection image par INDEX (pas par nom!) -->
    <!-- Index 1: Standard Core, Index 2: Standard Desktop -->
    <!-- Index 3: Datacenter Core, Index 4: Datacenter Desktop -->
    <ImageInstall>
      <OSImage>
        <InstallFrom>
          <MetaData wcm:action="add">
            <Key>/IMAGE/INDEX</Key>
            <Value>2</Value>  <!-- Standard avec GUI -->
          </MetaData>
        </InstallFrom>
        <InstallTo>
          <DiskID>0</DiskID>
          <PartitionID>3</PartitionID>
        </InstallTo>
      </OSImage>
    </ImageInstall>
    
    <UserData>
      <AcceptEula>true</AcceptEula>
      <FullName>Admin</FullName>
      <Organization>{{ organization }}</Organization>
    </UserData>
  </component>
</settings>

<!-- Phase Specialize: Nom machine, timezone -->
<settings pass="specialize">
  <component name="Microsoft-Windows-Shell-Setup" 
             processorArchitecture="amd64" 
             publicKeyToken="31bf3856ad364e35" 
             language="neutral" versionScope="nonSxS">
    <ComputerName>{{ hostname }}</ComputerName>
    <TimeZone>Romance Standard Time</TimeZone>
  </component>
</settings>

<!-- Phase OOBE: Mot de passe admin, autologon -->
<settings pass="oobeSystem">
  <component name="Microsoft-Windows-Shell-Setup" 
             processorArchitecture="amd64" 
             publicKeyToken="31bf3856ad364e35" 
             language="neutral" versionScope="nonSxS">
    <OOBE>
      <HideEULAPage>true</HideEULAPage>
      <HideLocalAccountScreen>true</HideLocalAccountScreen>
      <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>
      <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
      <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
      <ProtectYourPC>3</ProtectYourPC>
    </OOBE>
    <UserAccounts>
      <AdministratorPassword>
        <Value>{{ admin_password }}</Value>
        <PlainText>true</PlainText>
      </AdministratorPassword>
    </UserAccounts>
    <AutoLogon>
      <Enabled>true</Enabled>
      <Username>Administrateur</Username>
      <Password>
        <Value>{{ admin_password }}</Value>
        <PlainText>true</PlainText>
      </Password>
      <LogonCount>3</LogonCount>
    </AutoLogon>
  </component>
</settings>
</unattend>
```

## Workflow Déploiement Complet

```
1. Interface Web: User configure hostname, IP, password, etc.
                           │
                           ▼
2. Backend: Rendre template Jinja2 → autounattend.xml
                           │
                           ▼
3. Backend: Créer ISO OEMDRV (genisoimage, ~374 KB)
                           │
                           ▼
4. Backend: Transférer ISO OEMDRV vers Hyper-V (SMB)
                           │
                           ▼
5. Backend: Créer VM + attacher 2 DVDs (WinRM/PowerShell)
            - DVD 1: ISO Windows (partagé)
            - DVD 2: ISO OEMDRV (unique à cette VM)
                           │
                           ▼
6. Backend: Démarrer VM + envoyer touche Enter (WMI)
                           │
                           ▼
7. Windows: Installation 100% automatique (~15 min)
                           │
                           ▼
8. Backend: Détecter fin installation via Heartbeat
                           │
                           ▼
9. Backend: Post-config via WinRM (si nécessaire)
```

## Monitoring Installation

### Détecter si Windows est démarré

```powershell
$hb = Get-VMIntegrationService -VMName $VMName | 
      Where-Object { $_.Name -eq "Heartbeat" }

if ($hb.PrimaryStatusDescription -eq "OK") {
    Write-Output "Windows démarré et opérationnel"
}
```

### Capturer screenshot VM (debug)

```powershell
$vm = Get-WmiObject -Namespace "root\virtualization\v2" -Class "Msvm_ComputerSystem" | 
      Where-Object { $_.ElementName -eq $VMName }
$vmms = Get-WmiObject -Namespace "root\virtualization\v2" -Class "Msvm_VirtualSystemManagementService"
$result = $vmms.GetVirtualSystemThumbnailImage($vm, 640, 480)

# $result.ImageData contient l'image en format RGB565 brut
```

## Fichiers Importants

| Fichier | Description |
|---------|-------------|
| `src/domain/template_engine.py` | Génération autounattend.xml via Jinja2 |
| `templates/unattend/windows_server_2022.xml` | Template de base |
| `src/integrations/hypervisors/hyperv_client.py` | Client Hyper-V |
| `src/common/powershell.py` | Exécution PowerShell via WinRM |

## Erreurs Courantes

| Erreur | Cause | Solution |
|--------|-------|----------|
| "Press any key to boot" bloqué | Aucune touche envoyée | Envoyer Enter via WMI TypeScancodes |
| autounattend.xml non détecté | Label ISO != "OEMDRV" | Recréer ISO avec `-V "OEMDRV"` |
| "The boot loader failed" | ISO corrompu ou mauvais format | Vérifier ISO avec `file` et bootloader EFI |
| Sélection d'image demandée | Mauvais nom d'image | Utiliser `/IMAGE/INDEX` au lieu de `/IMAGE/NAME` |
