param(
    [string]$Version = "dev"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ReleaseRoot = Join-Path $ProjectRoot "release"
$PortableRoot = Join-Path $ReleaseRoot "NovelForge-Portable"
$ZipPath = Join-Path $ReleaseRoot ("NovelForge-windows-portable-{0}.zip" -f $Version)
$BuildLogPath = Join-Path $ReleaseRoot ("build_release-{0}.log" -f $Version)
$LauncherSpecRoot = Join-Path $ProjectRoot "dist"
$LauncherSpecPath = Join-Path $ProjectRoot "NovelForge.spec"
$BundledVenv = Join-Path $ProjectRoot ".venv"
$BundledPython = Join-Path $BundledVenv "Scripts\python.exe"
$StreamlitConfigRoot = Join-Path $ProjectRoot ".streamlit"

if (-not (Test-Path -LiteralPath $ReleaseRoot)) {
    New-Item -ItemType Directory -Path $ReleaseRoot | Out-Null
}

if (Test-Path -LiteralPath $BuildLogPath) {
    Remove-Item -LiteralPath $BuildLogPath -Force
}

Start-Transcript -LiteralPath $BuildLogPath | Out-Null

try {

function Assert-PathExists {
    param(
        [string]$LiteralPath,
        [string]$Message
    )

    if (-not (Test-Path -LiteralPath $LiteralPath)) {
        throw $Message
    }
}

Assert-PathExists -LiteralPath $ProjectRoot -Message "Project root not found."
Assert-PathExists -LiteralPath $BundledVenv -Message "Missing .venv. Create it first with 'python -m venv .venv'."
Assert-PathExists -LiteralPath $BundledPython -Message "Missing .venv\Scripts\python.exe. Install dependencies before building."
Assert-PathExists -LiteralPath $LauncherSpecPath -Message "Missing NovelForge.spec."

& $BundledPython -m pip install pyinstaller
if (-not $?) {
    throw "Failed to install PyInstaller into .venv."
}

& $BundledPython -m PyInstaller --noconfirm --clean $LauncherSpecPath
if (-not $?) {
    throw "PyInstaller build failed."
}

if (Test-Path -LiteralPath $PortableRoot) {
    Remove-Item -LiteralPath $PortableRoot -Recurse -Force
}
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
New-Item -ItemType Directory -Path $PortableRoot | Out-Null

$filesToCopy = @(
    "app.py",
    "llm.py",
    "memory.py",
    "merge.py",
    "retrieval.py",
    "schemas.py",
    "prompts.py",
    "skills.py",
    "project_manager.py",
    "launcher.py",
    "NovelForge.spec",
    "requirements.txt",
    ".env.example",
    "VERSION",
    "README.md",
    "README.en.md",
    "project.md"
)

foreach ($relativePath in $filesToCopy) {
    $sourcePath = Join-Path $ProjectRoot $relativePath
    Assert-PathExists -LiteralPath $sourcePath -Message "Missing required file: $relativePath"
    Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $PortableRoot $relativePath)
}

Copy-Item -LiteralPath (Join-Path $LauncherSpecRoot "NovelForge.exe") -Destination (Join-Path $PortableRoot "NovelForge.exe")
Copy-Item -LiteralPath $BundledVenv -Destination (Join-Path $PortableRoot ".venv") -Recurse

if (Test-Path -LiteralPath $StreamlitConfigRoot) {
    Copy-Item -LiteralPath $StreamlitConfigRoot -Destination (Join-Path $PortableRoot ".streamlit") -Recurse
}

$dataRoot = Join-Path $PortableRoot "data"
New-Item -ItemType Directory -Path $dataRoot | Out-Null
New-Item -ItemType Directory -Path (Join-Path $dataRoot "projects") | Out-Null

$usageNote = @(
    "NovelForge Portable",
    "",
    "1. Extract this archive to a writable folder such as D:\Apps\NovelForge\",
    "2. Do not place it under Program Files or other administrator-protected folders.",
    "3. Launch NovelForge.exe to start the local web app.",
    "4. The browser should open a local NovelForge page automatically, starting with http://127.0.0.1:8501.",
    "5. Use the in-app 模型配置 page to set your endpoint and API key.",
    "6. If port 8501 is occupied, the launcher may fall back to another nearby local port.",
    "",
    "User data stays in the local data/ folder and the .env file in this directory.",
    "If startup fails, check launcher.log in this directory."
)

Set-Content -LiteralPath (Join-Path $PortableRoot "USAGE.txt") -Value $usageNote -Encoding UTF8

Compress-Archive -LiteralPath $PortableRoot -DestinationPath $ZipPath -Force

"Portable release created: $ZipPath"
"Build log saved to: $BuildLogPath"
}
finally {
    Stop-Transcript | Out-Null
}
