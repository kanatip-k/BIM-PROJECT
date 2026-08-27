$ErrorActionPreference = "Stop"

$projectDll = "D:\BIM-PROJECT\Navisworks_MCP_Web_Prototype\navisworks_plugin\NavisMcpBridge.dll"
$installedDll = "D:\Navisworks Manage 2027\Plugins\NavisMcpBridge\NavisMcpBridge.dll"

if (Get-Process -Name "Roamer" -ErrorAction SilentlyContinue) {
    Write-Host "Please close Navisworks before installing the update." -ForegroundColor Yellow
    exit 1
}

Copy-Item -LiteralPath $projectDll -Destination $installedDll -Force
Write-Host "Navis MCP Bridge update installed successfully." -ForegroundColor Green
Write-Host "Open Navisworks and run Add-Ins > Navis MCP Bridge again."
