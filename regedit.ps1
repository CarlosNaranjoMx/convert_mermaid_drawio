$scriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$pythonLauncher = 'C:\Users\carlosmx\AppData\Local\Microsoft\WindowsApps\py.exe'
$script = Join-Path $scriptDir 'convert_mmd_draw.py'
$command = 'powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -Command "& ''{0}'' -3 ''{1}'' ''%1''"' -f $pythonLauncher, $script

$root = [Microsoft.Win32.Registry]::CurrentUser

# Menú contextual para directorios
$dirKey = $root.CreateSubKey('Software\\Classes\\Directory\\shell\\ConvertMermaidDraw')
$dirKey.SetValue('', 'Convertir Mermaid a draw.io', [Microsoft.Win32.RegistryValueKind]::String)
$dirKey.SetValue('Icon', $pythonLauncher, [Microsoft.Win32.RegistryValueKind]::String)
$dirKey.Close()

$dirCmdKey = $root.CreateSubKey('Software\\Classes\\Directory\\shell\\ConvertMermaidDraw\\command')
$dirCmdKey.SetValue('', $command, [Microsoft.Win32.RegistryValueKind]::String)
$dirCmdKey.Close()

# Menú contextual para archivos .mmd
$mmdKey = $root.CreateSubKey('Software\\Classes\\.mmd\\shell\\ConvertMermaidDraw')
$mmdKey.SetValue('', 'Convertir Mermaid a draw.io', [Microsoft.Win32.RegistryValueKind]::String)
$mmdKey.SetValue('Icon', $pythonLauncher, [Microsoft.Win32.RegistryValueKind]::String)
$mmdKey.Close()

$mmdCmdKey = $root.CreateSubKey('Software\\Classes\\.mmd\\shell\\ConvertMermaidDraw\\command')
$mmdCmdKey.SetValue('', $command, [Microsoft.Win32.RegistryValueKind]::String)
$mmdCmdKey.Close()

Write-Host "Menú contextual agregado para carpetas y archivos .mmd." -ForegroundColor Green
Write-Host "Si no lo ves de inmediato, cierra y vuelve a abrir el Explorador de Windows." -ForegroundColor Yellow
