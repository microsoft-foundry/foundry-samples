$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'src\agent'
$wheels = Join-Path $source 'wheelhouse'
$packages = Join-Path $source 'packages'
$feed = 'https://pkgs.dev.azure.com/azure-sdk/public/_packaging/azure-sdk-for-python/pypi/simple/'
$dependencies = Get-Content -LiteralPath (Join-Path $source 'requirements.txt') |
    Where-Object { $_ -and -not $_.StartsWith('--') }

python -m pip download --dest $wheels --no-deps --index-url $feed `
    'azure-ai-agentserver-a2a==1.0.0a20261029006' `
    'azure-ai-agentserver-core==2.3.1a20261029006' --no-input
if ($LASTEXITCODE -ne 0) { throw 'Azure SDK wheel download failed' }

python -m pip download --only-binary=:all: `
    --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 `
    --python-version 3.13 --implementation cp --abi cp313 `
    --dest $wheels --find-links $wheels --index-url 'https://pypi.org/simple/' `
    @dependencies --no-input
if ($LASTEXITCODE -ne 0) { throw 'Linux dependency download failed' }

python -m pip install --target $packages --upgrade --ignore-installed `
    --no-index --find-links $wheels --only-binary=:all: `
    --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 `
    --python-version 3.13 --implementation cp --abi cp313 `
    @dependencies --no-input
if ($LASTEXITCODE -ne 0) { throw 'Linux dependency bundle creation failed' }
