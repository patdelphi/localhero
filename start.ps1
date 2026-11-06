# 程序说明：本地一键启动脚本，按开发/生产配置档运行，可强制离线模拟模式。
[CmdletBinding()]
param(
    [ValidateSet("dev", "prod")]
    [string]$Profile = "dev",
    [switch]$Offline,
    [switch]$Online,
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$DatabasePath = "data/games.db",
    [string]$BindHost = "127.0.0.1",
    [switch]$Install,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Offline -and $Online) {
    throw "不能同时指定 -Offline 与 -Online"
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    if (-not $Install) {
        throw "缺少 .venv。请先运行：.\start.ps1 -Install（会创建虚拟环境并安装依赖）"
    }
    Write-Host "创建虚拟环境..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败" }
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "安装依赖失败" }
}

# 开发档默认离线，避免开发时意外产生外部请求；生产档默认按 .env 配置。
$offlineMode = if ($Profile -eq "dev") { -not $Online.IsPresent } else { $Offline.IsPresent }

$dbPath = if ([System.IO.Path]::IsPathRooted($DatabasePath)) {
    $DatabasePath
} else {
    Join-Path $PSScriptRoot $DatabasePath
}
$dbDirectory = Split-Path -Parent $dbPath
if ($dbDirectory -and -not (Test-Path $dbDirectory)) {
    New-Item -ItemType Directory -Path $dbDirectory | Out-Null
}

$env:GREY_ZONE_DB = $dbPath
$env:GREY_ZONE_OFFLINE = if ($offlineMode) { "1" } else { "0" }
$env:GREY_ZONE_LOG_DIR = Join-Path $PSScriptRoot "data\logs"
if (-not $env:GREY_ZONE_LOG_LEVEL) {
    $env:GREY_ZONE_LOG_LEVEL = if ($Profile -eq "dev") { "DEBUG" } else { "INFO" }
}

$modeLabel = if ($offlineMode) { "离线模拟" } else { "在线 Provider（读取 .env）" }
$url = "http://${BindHost}:$Port/"
Write-Host "配置档：$Profile"
Write-Host "模型模式：$modeLabel"
Write-Host "存档：$dbPath"
Write-Host "访问：$url"

if ($OpenBrowser) {
    Start-Process $url
}

& $venvPython -m uvicorn app.main:app --host $BindHost --port $Port
