# Restarts the Farm Master public preview: the FastAPI app on 127.0.0.1:8000
# plus a Cloudflare Quick Tunnel to it, then prints the new public link.
# See README "Preview via Cloudflare".
#
#   start-preview.ps1           restart both and print the link
#   start-preview.ps1 -Stop     stop both
#   start-preview.ps1 -Install  also restart the preview at every Windows sign-in
#
# Both run as detached processes (created through WMI, so they outlive the
# shell that started them). Logs, the current link and the preview logins
# live in .preview\ (git-ignored).

param([switch]$Stop, [switch]$Install)

$ErrorActionPreference = "Stop"
$Build = $PSScriptRoot
$State = Join-Path $Build ".preview"
$Port = 8000
New-Item -ItemType Directory -Force $State | Out-Null

function Stop-Preview {
    foreach ($name in "app", "tunnel") {
        $pidFile = Join-Path $State "$name.pid"
        if (Test-Path $pidFile) {
            & taskkill.exe /T /F /PID (Get-Content $pidFile) 2>$null | Out-Null
            Remove-Item $pidFile
        }
    }
    # Anything left over from an earlier run started some other way.
    Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
        Where-Object { $_.CommandLine -match "127\.0\.0\.1:$Port" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        ForEach-Object { Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue } |
        Where-Object { $_.ProcessName -eq "python" } |
        ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
}

function Start-Detached([string]$CommandLine, [string]$PidName) {
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $CommandLine; CurrentDirectory = $Build; ProcessStartupInformation = $startup }
    if ($r.ReturnValue -ne 0) { throw "Could not start $PidName (Win32_Process.Create returned $($r.ReturnValue))." }
    Set-Content (Join-Path $State "$PidName.pid") $r.ProcessId
}

Stop-Preview
if ($Stop) { Write-Host "Farm Master preview stopped."; exit 0 }

if ($Install) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName "FarmMasterPreview" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Registered the FarmMasterPreview sign-in task."
}

$python = (Get-Command python).Source
$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) { $cloudflared = "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe" }
if (-not (Test-Path $cloudflared)) { throw "cloudflared not found. Install it: winget install Cloudflare.cloudflared" }

$pg = Get-Service postgresql-x64-17 -ErrorAction SilentlyContinue
if ($pg -and $pg.Status -ne "Running") { Start-Service postgresql-x64-17 }

# A random JWT signing secret, made once and kept for this machine's previews.
$secretFile = Join-Path $State "secret.env"
if (-not (Test-Path $secretFile)) {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    Set-Content $secretFile ("FARM_MASTER_JWT_SECRET=" + [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")) -Encoding ascii
}

# Migrations, seed data, and strong passwords for every seeded account.
& $python (Join-Path $Build "scripts\preview_accounts.py")
if ($LASTEXITCODE -ne 0) { throw "Preparing the database failed." }

Start-Detached "cmd.exe /c `"`"$Build\scripts\preview-app.cmd`" `"$python`"`"" "app"
$deadline = (Get-Date).AddSeconds(90)
do {
    Start-Sleep -Seconds 1
    try { $ok = (Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { $ok = $false }
} until ($ok -or (Get-Date) -gt $deadline)
if (-not $ok) { throw "The app didn't start. See $State\app.log" }

Start-Detached "cmd.exe /c `"`"$Build\scripts\preview-tunnel.cmd`" `"$cloudflared`"`"" "tunnel"
$logFile = Join-Path $State "tunnel.log"
$deadline = (Get-Date).AddSeconds(60)
$url = $null
do {
    Start-Sleep -Seconds 1
    if (Test-Path $logFile) {
        $m = Select-String -Path $logFile -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
} until ($url -or (Get-Date) -gt $deadline)
if (-not $url) { throw "The tunnel didn't report a link. See $logFile" }

# A new hostname can take a few seconds to resolve.
$deadline = (Get-Date).AddSeconds(60)
do {
    Start-Sleep -Seconds 2
    try { $live = (Invoke-WebRequest "$url/health" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { $live = $false }
} until ($live -or (Get-Date) -gt $deadline)

Set-Content (Join-Path $State "url.txt") $url
Write-Host ""
Write-Host "Farm Master preview is live$(if (-not $live) { ' (still propagating, try again in a minute)' }):"
Write-Host ""
Write-Host $url
Write-Host ""
Write-Host "Logins: $State\credentials.txt"
