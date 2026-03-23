Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\\Scripts\\python.exe"
$DefaultAdbPath = "D:\\adb\\platform-tools\\adb.exe"

if (-not (Test-Path $VenvPython)) {
    throw "未找到虚拟环境，请先执行 scripts/setup_windows.ps1"
}

if (Test-Path $DefaultAdbPath) {
    & $VenvPython (Join-Path $Root "main.py") run --config (Join-Path $Root "configs\\xianyu_search_demo.yaml") --adb-path $DefaultAdbPath
} else {
    & $VenvPython (Join-Path $Root "main.py") run --config (Join-Path $Root "configs\\xianyu_search_demo.yaml")
}

