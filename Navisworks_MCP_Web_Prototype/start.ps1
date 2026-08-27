# ==================================================
#  start.ps1
#  เปิด JSON Bridge (port 8765) และ Web Dashboard (port 8000)
# ==================================================

$Root      = $PSScriptRoot
$AppDir    = Join-Path $Root "python_app"
$Python    = Join-Path $AppDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host ""
    Write-Host "ERROR: ไม่พบ Python venv ที่: $Python" -ForegroundColor Red
    Write-Host "รัน: cd python_app ; python -m venv .venv ; .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# หาไฟล์ JSON ล่าสุดใน data/export/ โดยอัตโนมัติ
$ExportDir  = Join-Path $Root "data\export"
$JsonFiles  = @()
if (Test-Path $ExportDir) {
    $JsonFiles = @(Get-ChildItem -Path $ExportDir -Filter "*.json" |
                   Where-Object { $_.Name -notlike "*.status.json" } |
                   Sort-Object LastWriteTime -Descending)
}

if ($JsonFiles.Count -eq 0) {
    Write-Host ""
    Write-Host "ไม่พบไฟล์ JSON ใน data\export\" -ForegroundColor Yellow
    Write-Host "รัน .\run_export.ps1 ก่อนเพื่อถอดข้อมูลจากโมเดล" -ForegroundColor Yellow
    Write-Host ""
    $Confirm = Read-Host "ต้องการเปิด Dashboard ต่อโดยไม่มีข้อมูลหรือไม่? (y/N)"
    if ($Confirm -ne "y" -and $Confirm -ne "Y") { exit 0 }
    $JsonPath = ""
} elseif ($JsonFiles.Count -eq 1) {
    $JsonPath = $JsonFiles[0].FullName
    Write-Host ""
    Write-Host "ใช้ไฟล์: $($JsonFiles[0].Name)" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "พบไฟล์ JSON หลายไฟล์ กรุณาเลือก:" -ForegroundColor Cyan
    for ($i = 0; $i -lt [Math]::Min($JsonFiles.Count, 9); $i++) {
        $Age = [math]::Round(((Get-Date) - $JsonFiles[$i].LastWriteTime).TotalMinutes)
        Write-Host "  [$($i + 1)] $($JsonFiles[$i].Name)  ($Age นาทีที่แล้ว)"
    }
    Write-Host ""
    $Choice = Read-Host "พิมพ์หมายเลข (Enter = ใช้ไฟล์ล่าสุด)"
    if ([string]::IsNullOrWhiteSpace($Choice)) {
        $JsonPath = $JsonFiles[0].FullName
    } else {
        $Index = [int]$Choice - 1
        if ($Index -lt 0 -or $Index -ge $JsonFiles.Count) {
            Write-Host "เลือกไม่ถูกต้อง" -ForegroundColor Red; exit 1
        }
        $JsonPath = $JsonFiles[$Index].FullName
    }
    Write-Host "ใช้ไฟล์: $(Split-Path $JsonPath -Leaf)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " เปิดระบบ Navisworks MCP Web Dashboard" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
if ($JsonPath) {
    Write-Host " JSON    : $JsonPath"
}
Write-Host " Bridge  : http://127.0.0.1:8765"
Write-Host " Dashboard: http://127.0.0.1:8000"
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "กด Ctrl+C เพื่อหยุดระบบ" -ForegroundColor Yellow
Write-Host ""

# เปิด JSON Bridge ใน background
$BridgeEnv = [System.Environment]::GetEnvironmentVariables()
if ($JsonPath) {
    $BridgeProcess = Start-Process -FilePath $Python `
        -ArgumentList "-m", "uvicorn", "json_bridge:app", "--host", "127.0.0.1", "--port", "8765" `
        -WorkingDirectory $AppDir `
        -Environment @{ NAVIS_JSON_PATH = $JsonPath } `
        -PassThru -NoNewWindow
} else {
    $BridgeProcess = Start-Process -FilePath $Python `
        -ArgumentList "-m", "uvicorn", "json_bridge:app", "--host", "127.0.0.1", "--port", "8765" `
        -WorkingDirectory $AppDir `
        -PassThru -NoNewWindow
}

Start-Sleep -Seconds 2

# เปิด Web Dashboard ใน foreground (Ctrl+C จะหยุด)
try {
    & $Python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
} finally {
    Write-Host ""
    Write-Host "กำลังปิด JSON Bridge..." -ForegroundColor Yellow
    if ($BridgeProcess -and -not $BridgeProcess.HasExited) {
        $BridgeProcess.Kill()
    }
    Write-Host "ปิดระบบเรียบร้อย" -ForegroundColor Green
}
