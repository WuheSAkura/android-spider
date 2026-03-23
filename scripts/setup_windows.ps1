Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\\Scripts\\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "创建虚拟环境 .venv ..."
    & py -3.11 -m venv (Join-Path $Root ".venv")
}

Write-Host "升级 pip ..."
& $VenvPython -m pip install --upgrade pip

Write-Host "安装依赖 requirements.txt ..."
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")

Write-Host "环境准备完成。"

