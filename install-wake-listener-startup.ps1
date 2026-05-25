$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$starter = Join-Path $root "start-wake-listener.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$starter`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
try {
    Register-ScheduledTask -TaskName "Morice Wake Listener" -Action $action -Trigger $trigger -Principal $principal -Description "Listens for two claps or the Morice magic words." -Force | Out-Null
    Write-Host "Installed startup task: Morice Wake Listener"
} catch {
    $startup = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startup "Morice Wake Listener.lnk"
    $target = Join-Path $root "start-wake-listener.bat"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $root
    $shortcut.WindowStyle = 7
    $shortcut.Description = "Starts the Morice wake listener."
    $shortcut.Save()
    Write-Host "Scheduled task was blocked, so a Startup shortcut was installed: $shortcutPath"
}
