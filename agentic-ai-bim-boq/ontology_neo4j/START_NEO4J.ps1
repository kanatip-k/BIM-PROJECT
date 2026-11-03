param([string]$JavaHome = 'C:\Program Files\Java\jdk-25')
$ErrorActionPreference = 'Stop'
$neoHome = Join-Path $PSScriptRoot 'runtime\neo4j-community-2026.10.1'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\java.exe'))) { throw 'Set -JavaHome to an installed Java 21 or 25 JDK.' }
if (-not (Test-Path -LiteralPath (Join-Path $neoHome 'bin\neo4j.bat'))) { throw 'Neo4j runtime missing; see README_TH.md.' }
$env:JAVA_HOME = $JavaHome
$env:PYTHONIOENCODING = 'utf-8'
function Test-BoltPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect('127.0.0.1',17687,$null,$null)
        if (-not $pending.AsyncWaitHandle.WaitOne(1000)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Close() }
}
$existing = Test-BoltPort
if (-not $existing) {
    $process = Start-Process -FilePath (Join-Path $neoHome 'bin\neo4j.bat') -ArgumentList 'console' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'runtime\console.log') -RedirectStandardError (Join-Path $PSScriptRoot 'runtime\console-error.log')
    $process.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime\launcher.pid') -Encoding ascii
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-BoltPort) { break }
    }
}
# Verify credentials AND imported graph; an occupied port alone is not success.
& $python -c "import sys; sys.path.insert(0,sys.argv[1]); from core import GraphStore; d=GraphStore(); s=d.snapshot(); print('Neo4j ready. Ontology version: '+s['version']); d.close()" $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw 'Neo4j verification failed. Inspect runtime logs and connection.local.json.' }
Write-Host 'Browser: http://127.0.0.1:17474/ ; Bolt: bolt://127.0.0.1:17687'
