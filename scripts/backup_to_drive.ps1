# Back up stable Nortek telemetry files to a Google Drive for desktop folder.
# Run every five minutes using Windows Task Scheduler.

$Source = 'C:\Users\Nortek1000\Documents\Nortek\Deployment\Online'
$Destination = 'G:\My Drive\hval'
$StableMinutes = 0
$CheckSeconds = 1

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    throw "Source folder not found: $Source"
}
if (-not (Test-Path -LiteralPath $Destination -PathType Container)) {
    throw "Google Drive folder not found: $Destination (check the drive letter and sign-in)"
}

# Record file sizes and modification times, then check again after a short pause.
$initial = @{}
Get-ChildItem -LiteralPath $Source -Filter 'Terminal_*.txt' -File | ForEach-Object {
    $initial[$_.FullName] = @($_.Length, $_.LastWriteTimeUtc.Ticks)
}

Start-Sleep -Seconds $CheckSeconds

$copied = 0
$skipped = 0
$failed = 0

foreach ($path in $initial.Keys) {
    $file = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
    if ($null -eq $file) { $skipped++; continue }

    $was = $initial[$path]
    $stable = ($file.Length -eq $was[0]) -and ($file.LastWriteTimeUtc.Ticks -eq $was[1])
    $oldEnough = $file.LastWriteTimeUtc -le (Get-Date).ToUniversalTime().AddMinutes(-$StableMinutes)
    if (-not ($stable -and $oldEnough)) {
        Write-Host "Still changing or recently modified: $($file.Name)"
	$skipped++
        continue
    }

    # Avoid starting Robocopy for files already backed up.
    $destinationFile = Get-Item -LiteralPath (Join-Path $Destination $file.Name) -ErrorAction SilentlyContinue
    if ($null -ne $destinationFile -and
        $destinationFile.Length -eq $file.Length -and
        [Math]::Abs(($destinationFile.LastWriteTimeUtc - $file.LastWriteTimeUtc).TotalSeconds) -le 2) {
	Write-Host "Already backed up: $($file.Name)"
        $skipped++
        continue
    }

    # Robocopy additionally skips matching files and preserves their timestamps.
    & robocopy.exe $Source $Destination $file.Name /FFT /R:2 /W:5 /NP /NFL /NDL /NJH /NJS
    $code = $LASTEXITCODE

    if ($code -ge 8) {
        Write-Warning "Copy failed: $($file.Name) (Robocopy exit code $code)"
        $failed++
    } elseif ($code -band 1) {
        Write-Host "Copied new/changed file: $($file.Name)"
        $copied++
    } else {
        $skipped++
    }

    # If the instrument updated this file while it was being copied,
    # the next scheduled run will copy the changed version again.
    $after = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
    if ($null -ne $after -and (
        $after.Length -ne $file.Length -or
        $after.LastWriteTimeUtc.Ticks -ne $file.LastWriteTimeUtc.Ticks
    )) {
        Write-Warning "Source changed during backup; will recheck next run: $($file.Name)"
    }
}

Write-Host "Backup complete: $copied copied, $skipped skipped, $failed failed."
if ($failed -gt 0) { exit 1 }
