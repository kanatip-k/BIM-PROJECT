# ==================================================
#  run_export.ps1
#  ถอดข้อมูลจากไฟล์ Navisworks ใน data/ -> data/export/
# ==================================================

$Root        = $PSScriptRoot
$DataDir     = Join-Path $Root "data"
$ExportDir   = Join-Path $Root "data\export"
$RunnerExe   = Join-Path $Root "navisworks-headless-exporter\dist\NavisHeadlessRunner.exe"
$NavisDir    = "D:\Navisworks Manage 2027"

# ตรวจว่ามี Runner ไหม
if (-not (Test-Path $RunnerExe)) {
    Write-Host ""
    Write-Host "ERROR: ไม่พบ NavisHeadlessRunner.exe ที่:" -ForegroundColor Red
    Write-Host "  $RunnerExe" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# ตรวจว่ามี Navisworks ไหม
if (-not (Test-Path (Join-Path $NavisDir "roamer.exe"))) {
    Write-Host ""
    Write-Host "ERROR: ไม่พบ Navisworks ที่: $NavisDir" -ForegroundColor Red
    Write-Host "แก้ตัวแปร `$NavisDir ในไฟล์ run_export.ps1 ให้ตรงกับที่ติดตั้ง" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# หาไฟล์โมเดลใน data/
$Models = Get-ChildItem -Path $DataDir -File -Include "*.nwd","*.nwf","*.nwc" -ErrorAction SilentlyContinue

if ($Models.Count -eq 0) {
    Write-Host ""
    Write-Host "ไม่พบไฟล์ .nwd / .nwf / .nwc ในโฟลเดอร์ data\" -ForegroundColor Yellow
    Write-Host "วางไฟล์โมเดลไว้ที่: $DataDir" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# ถ้ามีหลายไฟล์ ให้เลือก
if ($Models.Count -eq 1) {
    $Selected = $Models[0]
} else {
    Write-Host ""
    Write-Host "พบไฟล์โมเดลหลายไฟล์ กรุณาเลือก:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $Models.Count; $i++) {
        Write-Host "  [$($i + 1)] $($Models[$i].Name)"
    }
    Write-Host ""
    $Choice = Read-Host "พิมพ์หมายเลข (1-$($Models.Count))"
    $Index = [int]$Choice - 1
    if ($Index -lt 0 -or $Index -ge $Models.Count) {
        Write-Host "เลือกไม่ถูกต้อง" -ForegroundColor Red
        exit 1
    }
    $Selected = $Models[$Index]
}

# สร้าง output path
New-Item -ItemType Directory -Path $ExportDir -Force | Out-Null
$BaseName   = [System.IO.Path]::GetFileNameWithoutExtension($Selected.Name)
$OutputJson = Join-Path $ExportDir "$BaseName.json"
$StatusJson = Join-Path $ExportDir "$BaseName.status.json"

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " เริ่มถอดข้อมูล" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " โมเดล : $($Selected.FullName)"
Write-Host " Output : $OutputJson"
Write-Host " Status : $StatusJson"
Write-Host " Navisworks: $NavisDir"
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Navisworks กำลังเปิดแบบ NoGui... (อาจใช้เวลา 1-3 นาที)" -ForegroundColor Yellow
Write-Host ""

$StartTime = Get-Date

& $RunnerExe `
    $Selected.FullName `
    $OutputJson `
    $NavisDir `
    (Join-Path $Root "navisworks-headless-exporter\dist\NavisHeadlessExporter.dll") `
    $StatusJson

$ExitCode = $LASTEXITCODE
$Elapsed  = (Get-Date) - $StartTime

Write-Host ""
if ($ExitCode -eq 0 -and (Test-Path $OutputJson)) {
    $SizeMB = [math]::Round((Get-Item $OutputJson).Length / 1MB, 1)
    Write-Host "===================================================" -ForegroundColor Green
    Write-Host " สำเร็จ! ใช้เวลา $([math]::Round($Elapsed.TotalSeconds)) วินาที" -ForegroundColor Green
    Write-Host " ไฟล์ JSON : $OutputJson ($SizeMB MB)" -ForegroundColor Green
    Write-Host "===================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "ขั้นตอนต่อไป:" -ForegroundColor Cyan
    Write-Host "  รัน .\start.ps1  แล้วเปิด http://127.0.0.1:8000"
    Write-Host "  กด Refresh from MCP บน Dashboard"
    Write-Host ""
} else {
    Write-Host "===================================================" -ForegroundColor Red
    Write-Host " เกิดข้อผิดพลาด (exit code: $ExitCode)" -ForegroundColor Red
    Write-Host " ดูรายละเอียดที่: $StatusJson" -ForegroundColor Red
    Write-Host "===================================================" -ForegroundColor Red
    Write-Host ""
    if (Test-Path $StatusJson) {
        Write-Host "Status file:" -ForegroundColor Yellow
        Get-Content $StatusJson
    }
    exit $ExitCode
}
