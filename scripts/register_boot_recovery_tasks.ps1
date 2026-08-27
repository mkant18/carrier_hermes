# Registers the three boot-recovery scheduled tasks for the 5am daily restart.
# Run elevated (single UAC prompt). Idempotent — re-registering overwrites.
$ErrorActionPreference = "Stop"

# 1) OllamaWslPortproxy — refresh the 127.0.0.1:11434 -> WSL2 portproxy at logon (WSL IP changes each boot)
$proxyScript = @'
$wslIp = (wsl -- hostname -I 2>$null).Trim().Split(" ")[0]
if ($wslIp) {
  netsh interface portproxy delete v4tov4 listenaddress=127.0.0.1 listenport=11434 2>$null
  netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=11434 connectaddress=$wslIp connectport=11434
}
'@
$proxyPath = "C:\Users\micha\carrier_hermes\scripts\refresh_ollama_portproxy.ps1"
Set-Content -Path $proxyPath -Value $proxyScript -Encoding UTF8

$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$proxyPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "micha"
$trigger.Delay = "PT30S"
$principal = New-ScheduledTaskPrincipal -UserId "micha" -RunLevel Highest -LogonType Interactive
Register-ScheduledTask -TaskName "OllamaWslPortproxy" -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Write-Host "OK OllamaWslPortproxy"

# 2) CarrierOmbAutostart — relaunch OpenMausBot at logon (delayed so WSL/portproxy settle first)
$action2  = New-ScheduledTaskAction -Execute "C:\Users\micha\AppData\Local\Programs\openmausbot\OpenMausBot.exe"
$trigger2 = New-ScheduledTaskTrigger -AtLogOn -User "micha"
$trigger2.Delay = "PT90S"
Register-ScheduledTask -TaskName "CarrierOmbAutostart" -Action $action2 -Trigger $trigger2 -Force | Out-Null
Write-Host "OK CarrierOmbAutostart"

# 3) CarrierOllamaWatchdog — restart the fallback watchdog at logon
$action3  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -Command `"Start-Process -WindowStyle Hidden python3 -ArgumentList 'C:\Users\micha\carrier_hermes\scripts\ollama_fallback_watchdog.py','--interval','30'`""
$trigger3 = New-ScheduledTaskTrigger -AtLogOn -User "micha"
$trigger3.Delay = "PT2M"
Register-ScheduledTask -TaskName "CarrierOllamaWatchdog" -Action $action3 -Trigger $trigger3 -Force | Out-Null
Write-Host "OK CarrierOllamaWatchdog"

Write-Host "All three boot-recovery tasks registered."
