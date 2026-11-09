# Copy new and changed telemetry files to Google Drive for desktop.
# Run every five minutes with Windows Task Scheduler.

$Source = 'C:\Users\Nortek1000\Desktop\ADCP\adcp-data\raw\telemetry\live'
$Destination = 'G:\My Drive\hval'
$CheckSeconds = 1

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    throw "Source folder not found: $Source"
}
if (-not (Test-Path -LiteralPath $Destination -PathType Container)) {
    throw "Google Drive folder not found: $Destination"
}

# Only copy files whose size and modification time stay unchanged during the check.
$initial = @{}
Get-ChildItem -LiteralPath $Source -File -Recurse | ForEach-Object {
    $initial[$_.FullName] = @($_.Length, $_.LastWriteTimeUtc.Ticks)
}
Start-Sleep -Seconds $CheckSeconds

$sourceRoot = $Source.TrimEnd('\') + '\'
$copied = 0
$skipped = 0
$failed = 0

foreach ($path in $initial.Keys) {
    try {
        $file = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
        $was = $initial[$path]

        if ($null -eq $file -or $file.Length -ne $was[0] -or
            $file.LastWriteTimeUtc.Ticks -ne $was[1]) {
            $skipped++
            continue
        }

        $relativePath = $path.Substring($sourceRoot.Length)
        $targetPath = Join-Path $Destination $relativePath
        $target = Get-Item -LiteralPath $targetPath -ErrorAction SilentlyContinue

        if ($null -ne $target -and $target.Length -eq $file.Length -and
            [Math]::Abs(($target.LastWriteTimeUtc - $file.LastWriteTimeUtc).TotalSeconds) -le 2) {
            $skipped++
            continue
        }

        $targetDirectory = Split-Path -Parent $targetPath
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null

        & robocopy.exe ($file.DirectoryName) $targetDirectory ($file.Name) /FFT /R:2 /W:5 /NP /NFL /NDL /NJH /NJS
        $code = $LASTEXITCODE

        if ($code -ge 8) {
            Write-Warning "Copy failed: $relativePath (Robocopy code $code)"
            $failed++
        } elseif ($code -band 1) {
            Write-Host "Backed up: $relativePath"
            $copied++
        } else {
            $skipped++
        }

        $after = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
        if ($null -ne $after -and ($after.Length -ne $was[0] -or
            $after.LastWriteTimeUtc.Ticks -ne $was[1])) {
            Write-Warning "Changed during backup; will recheck next run: $relativePath"
        }
    } catch {
        Write-Warning "Backup error for $($path): $_"
        $failed++
    }
}

Write-Host "Backup complete: $copied copied, $skipped skipped, $failed failed."
if ($failed -gt 0) { exit 1 }
