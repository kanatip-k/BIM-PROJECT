param(
    [Parameter(Mandatory=$true)][string]$ModelPath,
    [string]$NavisDir = "D:\Navisworks Manage 2027"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$model = (Resolve-Path -LiteralPath $ModelPath).Path
$name = [IO.Path]::GetFileNameWithoutExtension($model)
$output = Join-Path $root ("data\export\" + $name + ".classified-source.json")
$status = Join-Path $root ("data\export\" + $name + ".classified-source.status.json")
$dll = Join-Path $root "navisworks-headless-exporter\dist\NavisMCP.Exporter.dll"
if (Test-Path -LiteralPath $output) { throw "Output already exists; preserve/review it first: $output" }
$started = Get-Date
$argsList = @("-NoGui", "-AddPluginAssembly", ('"' + $dll + '"'),
    "-OpenFile", ('"' + $model + '"'), "-ExecuteAddInPlugin", "NavisMCPExporter.KNTI",
    ('"' + $output + '"'), ('"' + $status + '"'), "-Exit")
$process = Start-Process -FilePath (Join-Path $NavisDir "roamer.exe") -ArgumentList $argsList -WorkingDirectory $NavisDir -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $output)) {
    throw "Navisworks export failed (exit=$($process.ExitCode)); output=$output; status=$status"
}
if ((Get-Item -LiteralPath $output).LastWriteTime -lt $started) { throw "Stale output: $output" }
Write-Output $output

