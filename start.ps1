$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$libraryPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $libraryPython)) {
    Write-Host '正在建立独立 Python 环境（需要 Python 3.11 或以上）…'
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '建立 Python 环境失败。' }
    & $libraryPython -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络后重试安装命令。' }
}
& $libraryPython -m airworthiness.app
if ($LASTEXITCODE -ne 0) { throw '资源大厅启动失败，请查看上方错误信息。' }
