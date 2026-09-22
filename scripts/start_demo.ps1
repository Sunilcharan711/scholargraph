# Starts the local, single-user SQLite demo. Run from PowerShell; no Docker needed.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$uvPath = if ($uvCommand) { $uvCommand.Source } else { Join-Path $env:USERPROFILE '.local/bin/uv.exe' }
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$nodePath = if ($nodeCommand) { $nodeCommand.Source } else { Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' }
if (!(Test-Path -LiteralPath $uvPath) -or !(Test-Path -LiteralPath $nodePath)) { throw 'Install uv and Node.js 22+ first. See docs/demo.md.' }
$env:PATH = (Split-Path $nodePath -Parent) + [IO.Path]::PathSeparator + $env:PATH
if (!(Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force data | Out-Null
& $uvPath sync --project backend --locked
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($npmCommand) { & $npmCommand.Source ci --prefix frontend }
elseif (Test-Path data/tools/package/bin/npm-cli.js) { & $nodePath data/tools/package/bin/npm-cli.js ci --prefix frontend }
else { throw 'Install Node.js with npm, then rerun this script.' }
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
Push-Location frontend
try { & $nodePath node_modules/next/dist/bin/next build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } }
finally { Pop-Location }
function IsReady([string]$url) { try { $null = Invoke-RestMethod $url -TimeoutSec 2; return $true } catch { return $false } }
$started = @()
if (!(IsReady 'http://127.0.0.1:11434/api/tags')) {
    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    $ollamaPath = if ($ollamaCommand) { $ollamaCommand.Source } else { Join-Path $projectRoot 'data/tools/ollama/ollama.exe' }
    if (Test-Path -LiteralPath $ollamaPath) {
        $env:OLLAMA_HOST = '127.0.0.1:11434'
        if (!$ollamaCommand) { $env:OLLAMA_MODELS = Join-Path $projectRoot 'data/ollama-models' }
        $started += Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput "$projectRoot/data/ollama.stdout.log" -RedirectStandardError "$projectRoot/data/ollama.stderr.log"
    } else { Write-Warning 'Ollama is missing. Search will work; install Ollama and pull the configured model for answers.' }
}
if (!(IsReady 'http://127.0.0.1:8000/api/health')) {
    $started += Start-Process -FilePath "$projectRoot/backend/.venv/Scripts/python.exe" -ArgumentList 'scripts/run_demo.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$projectRoot/data/demo-api.stdout.log" -RedirectStandardError "$projectRoot/data/demo-api.stderr.log"
}
if (!(IsReady 'http://127.0.0.1:3000/api/health')) {
    $started += Start-Process -FilePath $nodePath -ArgumentList 'node_modules/next/dist/bin/next start --hostname 127.0.0.1' -WorkingDirectory "$projectRoot/frontend" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$projectRoot/data/demo-web.stdout.log" -RedirectStandardError "$projectRoot/data/demo-web.stderr.log"
}
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if (IsReady 'http://127.0.0.1:3000/api/health') { break }
    Start-Sleep -Seconds 1
}
if (!(IsReady 'http://127.0.0.1:3000/api/health')) { throw 'Demo did not become ready. Inspect data/demo-*.stderr.log.' }
$started | Select-Object Id, ProcessName | Format-Table
Write-Host 'ScholarGraph is ready at http://127.0.0.1:3000 (SQLite demo).'
Write-Host 'New process IDs are listed above. Use Stop-Process -Id <ID> to stop those processes.'
