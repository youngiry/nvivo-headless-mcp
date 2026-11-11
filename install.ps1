param([Parameter(Mandatory=$true)][string]$NvivoInstallDir, [string]$Workspace = "$env:USERPROFILE/NVivoProjects")
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath "$NvivoInstallDir/NVivo.exe")) { throw 'Select the folder containing NVivo.exe' }
$root = $PSScriptRoot
py -3 -m venv "$root/.venv"
if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
& "$root/.venv/Scripts/python.exe" -m pip install -r "$root/requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
New-Item -ItemType Directory -Force -Path $Workspace, "$root/results" | Out-Null
$config = @{mcpServers=@{nvivo_headless=@{command="$root/.venv/Scripts/python.exe";args=@("$root/server.py");env=@{NVIVO_INSTALL_DIR=$NvivoInstallDir;NVIVO_WORKSPACE=$Workspace;NVIVO_AUTHOR='Shalom'}}}}
$config | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$root/config.local.json" -Encoding utf8
Write-Output "MCP configuration: $root/config.local.json"
