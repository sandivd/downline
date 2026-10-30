param([switch]$ChooseBrowser)

# Runs with the Windows built-in PowerShell. No administrator access required.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'
$AppRoot = $PSScriptRoot
$Runtime = Join-Path $AppRoot 'runtime'
$PythonDir = Join-Path $Runtime 'python'
$ToolsDir = Join-Path $Runtime 'tools'
$CacheDir = Join-Path $Runtime 'setup-cache'
$DataDir = Join-Path $env:LOCALAPPDATA 'Downline'
$SetupMutex = New-Object System.Threading.Mutex($false, 'Local\DownlineSetup')
$OwnsMutex = $false

function Fetch-File([string]$Url, [string]$Target) {
    $Partial = "$Target.downloading"
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Partial -TimeoutSec 600
        Move-Item -LiteralPath $Partial -Destination $Target -Force
    } finally {
        Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
    }
}

try {
    $OwnsMutex = $SetupMutex.WaitOne(0)
    if (-not $OwnsMutex) {
        Write-Host 'Downline setup is already running. Please wait for that window.'
        exit 0
    }
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Downline requires 64-bit Windows 10 or 11.' }
    New-Item -ItemType Directory -Force -Path $Runtime, $ToolsDir, $CacheDir, $DataDir | Out-Null
    $Python = Join-Path $PythonDir 'pythonw.exe'
    $Dlp = Join-Path $ToolsDir 'yt-dlp.exe'
    $Ffmpeg = Join-Path $ToolsDir 'ffmpeg.exe'
    $Ffprobe = Join-Path $ToolsDir 'ffprobe.exe'
    $Deno = Join-Path $ToolsDir 'deno.exe'
    $NeedsSetup = (-not (Test-Path $Python)) -or (-not (Test-Path $Dlp)) -or (-not (Test-Path $Ffmpeg)) -or (-not (Test-Path $Ffprobe)) -or (-not (Test-Path $Deno))
    if ($NeedsSetup) {
        Write-Host ''
        Write-Host '  downline.' -ForegroundColor Yellow
        Write-Host '  Setting up your local video downloader.'
        Write-Host '  First launch downloads Python, yt-dlp, FFmpeg and Deno.'
        Write-Host '  This may take a few minutes. No administrator access needed.'
        Write-Host ''
    }
    if (-not (Test-Path $Python)) {
        Write-Host '  [1/4] Preparing the app runtime...'
        $PythonZip = Join-Path $CacheDir 'python.zip'
        # Pin the hash for this exact filename. The release page also links
        # an 'embed-amd64' variant with a different hash. Source of this pin:
        # https://www.python.org/ftp/python/3.13.17/windows-3.13.17.json
        $ExpectedPythonHash = '0ba1ee4bfcbdc3a559d27e2e9ce76d04a7839947a23f46375872c755c0d463b8'
        $PythonZipValid = (Test-Path -LiteralPath $PythonZip) -and ((Get-FileHash -LiteralPath $PythonZip -Algorithm SHA256).Hash.ToLowerInvariant() -eq $ExpectedPythonHash)
        if (-not $PythonZipValid) {
            Fetch-File 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-embeddable-amd64.zip' $PythonZip
        }
        $ActualPythonHash = (Get-FileHash -LiteralPath $PythonZip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualPythonHash -ne $ExpectedPythonHash) {
            Remove-Item -LiteralPath $PythonZip -Force -ErrorAction SilentlyContinue
            throw ("The Python download failed verification and was removed. Run the launcher again. Expected: $ExpectedPythonHash; received: $ActualPythonHash")
        }
        $PythonStage = Join-Path $CacheDir 'python-stage'
        Remove-Item -LiteralPath $PythonStage -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -LiteralPath $PythonZip -DestinationPath $PythonStage -Force
        Remove-Item -LiteralPath $PythonDir -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $PythonStage -Destination $PythonDir
        Remove-Item -LiteralPath $PythonZip -Force
    }
    if (-not (Test-Path $Dlp)) {
        Write-Host '  [2/4] Getting the download engine...'
        $DlpStage = Join-Path $CacheDir 'yt-dlp.exe'
        $Sums = Join-Path $CacheDir 'SHA2-256SUMS'
        Fetch-File 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' $DlpStage
        Fetch-File 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS' $Sums
        $ChecksumLine = Get-Content -LiteralPath $Sums | Where-Object { $_ -match '^([a-fA-F0-9]{64})\s+\*?yt-dlp\.exe$' } | Select-Object -First 1
        if (-not $ChecksumLine) { throw 'The download engine checksum was missing. Try again later.' }
        $ExpectedDlpHash = ($ChecksumLine -split '\s+')[0]
        if ((Get-FileHash -LiteralPath $DlpStage -Algorithm SHA256).Hash.ToLower() -ne $ExpectedDlpHash.ToLower()) { throw 'The download engine checksum did not match. Try again.' }
        Move-Item -LiteralPath $DlpStage -Destination $Dlp -Force
    }
    if ((-not (Test-Path $Ffmpeg)) -or (-not (Test-Path $Ffprobe))) {
        Write-Host '  [3/4] Adding video and audio processing (largest download)...'
        $FfmpegZip = Join-Path $CacheDir 'ffmpeg.zip'
        $FfmpegStage = Join-Path $CacheDir 'ffmpeg-stage'
        Fetch-File 'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' $FfmpegZip
        Expand-Archive -LiteralPath $FfmpegZip -DestinationPath $FfmpegStage -Force
        foreach ($BinaryName in @('ffmpeg.exe', 'ffprobe.exe')) {
            $Found = Get-ChildItem -LiteralPath $FfmpegStage -Filter $BinaryName -Recurse | Select-Object -First 1
            if (-not $Found) { throw "The FFmpeg download did not contain $BinaryName." }
            Copy-Item -LiteralPath $Found.FullName -Destination (Join-Path $ToolsDir $BinaryName) -Force
        }
        # Preserve the binary distribution's notices alongside its tools.
        Get-ChildItem -LiteralPath $FfmpegStage -Recurse -File | Where-Object { $_.Name -match '^(LICENSE|COPYING|README)' } | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $ToolsDir $_.Name) -Force
        }
        Remove-Item -LiteralPath $FfmpegStage -Recurse -Force
        Remove-Item -LiteralPath $FfmpegZip -Force
    }
    if (-not (Test-Path $Deno)) {
        Write-Host '  [4/4] Adding YouTube support...'
        $DenoZip = Join-Path $CacheDir 'deno.zip'
        $DenoStage = Join-Path $CacheDir 'deno-stage'
        Fetch-File 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' $DenoZip
        Expand-Archive -LiteralPath $DenoZip -DestinationPath $DenoStage -Force
        $DenoBinary = Join-Path $DenoStage 'deno.exe'
        if (-not (Test-Path $DenoBinary)) { throw 'The JavaScript runtime download was incomplete.' }
        Move-Item -LiteralPath $DenoBinary -Destination $Deno -Force
        Remove-Item -LiteralPath $DenoStage -Recurse -Force
        Remove-Item -LiteralPath $DenoZip -Force
    }
    # Validate setup before opening the application. Failed files are removed so
    # the next launch can repair them rather than repeatedly using broken files.
    foreach ($Tool in @($Dlp, $Ffmpeg, $Ffprobe, $Deno)) {
        $VersionArg = if ($Tool -match 'ff(mpeg|probe)\.exe$') { '-version' } else { '--version' }
        & $Tool $VersionArg *> $null
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -LiteralPath $Tool -Force -ErrorAction SilentlyContinue
            throw "A download tool could not start. Reopen the launcher to repair it: $Tool"
        }
    }
    $PythonConsole = Join-Path $PythonDir 'python.exe'
    & $PythonConsole -c 'import http.server, ssl, subprocess, pathlib' *> $null
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $PythonDir -Recurse -Force -ErrorAction SilentlyContinue
        throw 'The app runtime could not start. Reopen the launcher to repair it.'
    }
    Write-Host '  Opening Downline...'
    $AppScript = Join-Path $AppRoot 'launch.pyw'
    $LaunchArgs = @('"' + $AppScript + '"')
    if ($ChooseBrowser) { $LaunchArgs += '--choose-browser' }
    Start-Process -FilePath $Python -ArgumentList $LaunchArgs -WorkingDirectory $AppRoot | Out-Null
} catch {
    Write-Host ''
    Write-Host ('  ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host '  Check your internet connection and try the launcher again.'
    exit 1
} finally {
    if ($OwnsMutex) { $SetupMutex.ReleaseMutex() }
    $SetupMutex.Dispose()
}
