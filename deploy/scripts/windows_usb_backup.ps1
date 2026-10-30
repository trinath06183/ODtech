<#
.SYNOPSIS
    ODtech ERP: Automated USB Backup for Windows
.DESCRIPTION
    Monitors for a specific USB Drive (by Volume Serial Number or Label),
    triggers system backup, copies files, deletes backups older than 30 days,
    displays a completion message, and safely ejects the drive.
#>

param(
    [string]$TargetVolumeSerial = "",   # e.g. "A1B2-C3D4" or "A1B2C3D4"
    [string]$TargetDriveLabel = "ODTECH_BACKUP",
    [string]$BackupSourceDir = "D:\ODtech\Main_work\Deployment\ODtech",
    [int]$RetentionDays = 30
)

Add-Type -AssemblyName System.Windows.Forms

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ODtech USB Automated Backup Listener (Windows)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

function Eject-Drive([string]$DriveLetter) {
    try {
        $shell = New-Object -ComObject Shell.Application
        $drive = $shell.Namespace(17).ParseName($DriveLetter)
        if ($drive) {
            $drive.InvokeVerb("Eject")
            Write-Host "[+] Drive $DriveLetter successfully ejected." -ForegroundColor Green
        }
    } catch {
        Write-Warning "Failed to auto-eject drive $DriveLetter : $_"
    }
}

function Perform-Backup([string]$DriveLetter) {
    $targetPath = "$DriveLetter\odtech_backups"
    if (!(Test-Path $targetPath)) {
        New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
    }

    Write-Host "[*] Triggering backup..." -ForegroundColor Yellow
    $timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
    
    # 1. Run management command if python is present, or archive sqlite database
    if (Test-Path "$BackupSourceDir\manage.py") {
        Push-Location $BackupSourceDir
        try {
            python manage.py backup_db --triggered-by manual
        } catch {
            Write-Warning "Django backup command had warnings: $_"
        }
        Pop-Location
    }

    # 2. Copy latest backup archives or sqlite database
    $localBackupDir = "$BackupSourceDir\backups"
    if (Test-Path $localBackupDir) {
        $latestFiles = Get-ChildItem -Path $localBackupDir | Sort-Object LastWriteTime -Descending | Select-Object -First 3
        foreach ($file in $latestFiles) {
            Write-Host "[+] Copying $($file.Name) to $targetPath..." -ForegroundColor Green
            Copy-Item -Path $file.FullName -Destination $targetPath -Force
        }
    } elseif (Test-Path "$BackupSourceDir\db.sqlite3") {
        $destFile = "$targetPath\db_backup_$timestamp.sqlite3"
        Write-Host "[+] Copying SQLite DB to $destFile..." -ForegroundColor Green
        Copy-Item -Path "$BackupSourceDir\db.sqlite3" -Destination $destFile -Force
    }

    # 3. Delete files older than 30 days on external drive
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $oldFiles = Get-ChildItem -Path $targetPath -File | Where-Object { $_.LastWriteTime -lt $cutoff }
    foreach ($old in $oldFiles) {
        Write-Host "[-] Deleting old backup (> $RetentionDays days): $($old.Name)" -ForegroundColor DarkGray
        Remove-Item -Path $old.FullName -Force
    }

    # 4. Show success notification
    $msg = "ODtech Backup copied successfully!`n`nOld backups older than $RetentionDays days were purged.`nThe drive has been safely ejected."
    Write-Host "[SUCCESS] $msg" -ForegroundColor Green
    
    # Eject drive
    Eject-Drive $DriveLetter

    # Graphical Pop-up
    [System.Windows.Forms.MessageBox]::Show($msg, "Backup Copied Successfully", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
}

# Continuous listener for drive insertion
Write-Host "[*] Listening for target external drive insertion..."
Write-Host "    Target Label: $TargetDriveLabel"
if ($TargetVolumeSerial) {
    Write-Host "    Target Serial: $TargetVolumeSerial"
}

$query = "SELECT * FROM __InstanceCreationEvent WITHIN 2 WHERE TargetInstance ISA 'Win32_LogicalDisk' AND TargetInstance.DriveType = 2"
Register-WmiEvent -Query $query -SourceIdentifier "USBInserted" -Action {
    $drive = $event.SourceEventArgs.NewEvent.TargetInstance
    $driveLetter = $drive.DeviceID
    $volumeName = $drive.VolumeName
    $serial = $drive.VolumeSerialNumber

    Write-Host "[*] Removable drive detected: $driveLetter (Label: '$volumeName', Serial: '$serial')" -ForegroundColor Cyan

    $isMatch = $false
    if ($TargetVolumeSerial -and ($serial -replace '-', '') -eq ($TargetVolumeSerial -replace '-', '')) {
        $isMatch = $true
    } elseif ($TargetDriveLabel -and $volumeName -eq $TargetDriveLabel) {
        $isMatch = $true
    }

    if ($isMatch) {
        Write-Host "[+] MATCHED TARGET DRIVE: $driveLetter. Starting automated backup..." -ForegroundColor Green
        Perform-Backup $driveLetter
    }
} | Out-Null

Write-Host "[+] Monitoring active. Press Ctrl+C to terminate listener."
try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Unregister-Event -SourceIdentifier "USBInserted" -ErrorAction SilentlyContinue
}

