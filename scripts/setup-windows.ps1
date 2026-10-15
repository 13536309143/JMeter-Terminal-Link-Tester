$ErrorActionPreference = 'Stop'
$Bootstrap = Join-Path $PSScriptRoot 'bootstrap.py'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $Bootstrap @args
} else {
    & python $Bootstrap @args
}
exit $LASTEXITCODE
