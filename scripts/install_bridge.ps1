$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$downloadDir = Join-Path $projectRoot 'tools/downloads'
New-Item -ItemType Directory -Force $downloadDir | Out-Null

function Install-PortableArchive {
    param([string]$Name, [string]$Url, [string]$Sha256, [string]$Destination, [string]$Marker)
    $archive = Join-Path $downloadDir $Name
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $archive
    }
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    if ($actual -ne $Sha256) { throw "Checksum mismatch for $Name" }
    $target = Join-Path $projectRoot $Destination
    if (-not (Test-Path -LiteralPath (Join-Path $target $Marker))) {
        New-Item -ItemType Directory -Force $target | Out-Null
        & tar -xf $archive -C $target
        if ($LASTEXITCODE -ne 0) { throw "Extraction failed for $Name" }
    }
}

Install-PortableArchive -Name 'magezero-xmage-v0.2.0-alpha.zip' `
    -Url 'https://github.com/WillWroble/MageZero/releases/download/v0.2.0-alpha/magezero-xmage-v0.2.0-alpha.zip' `
    -Sha256 'c0242f186c312db81d0240d1e7479ce0f4306523ebec11d92d616a4f289926a3' `
    -Destination 'tools/magezero' -Marker 'xmage/lib/mage-1.4.58.jar'

Install-PortableArchive -Name 'jdk21.zip' `
    -Url 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip' `
    -Sha256 'f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e' `
    -Destination 'tools/jdk' -Marker 'jdk-21.0.12.1+1/bin/javac.exe'

Install-PortableArchive -Name 'forge-2.0.15.tar.bz2' `
    -Url 'https://github.com/Card-Forge/forge/releases/download/forge-2.0.15/forge-installer-2.0.15.tar.bz2' `
    -Sha256 '4468f182b60f6ca62d89697baa208981085af744f116781af751c611826db600' `
    -Destination 'tools/forge' -Marker 'forge-gui-desktop-2.0.15-jar-with-dependencies.jar'

$venvPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & python -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
& $venvPython -m pip install -e $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed' }
Write-Output 'XMage bridge dependencies installed locally.'
