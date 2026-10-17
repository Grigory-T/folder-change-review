# Build-time download only. The finished application never runs this script.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$pin = Get-Content -LiteralPath "$PSScriptRoot\python-distribution.json" -Raw | ConvertFrom-Json
$cache = Join-Path $root '.build'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
$archive = Join-Path $cache 'python-build.tar.gz'
if (-not (Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -Uri $pin.url -OutFile $archive -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $pin.sha256) {
    throw 'Python archive checksum mismatch. Remove .build\python-build.tar.gz and retry.'
}
# Always extract verified inputs afresh; never reuse an arbitrary installed Python.
$destination = Join-Path $root '.build-python'
if (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination -Recurse -Force }
New-Item -ItemType Directory -Path $destination | Out-Null
& tar.exe -xzf $archive -C $destination --strip-components 1
if ($LASTEXITCODE -ne 0) { throw 'Python archive extraction failed.' }
& "$destination\python.exe" -I -c "import sys; assert sys.version_info[:3] == (3,13,16); assert sys.maxsize > 2**32"
if ($LASTEXITCODE -ne 0) { throw 'Unexpected Python version/architecture.' }
