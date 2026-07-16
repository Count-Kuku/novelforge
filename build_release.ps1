param(
    [string]$Version = "dev",
    [Parameter(Mandatory = $true)]
    [string]$RuntimeRoot
)

$ErrorActionPreference = "Stop"

function ConvertTo-NormalizedFullPath {
    param([string]$LiteralPath)

    $fullPath = [System.IO.Path]::GetFullPath($LiteralPath)
    $pathRoot = [System.IO.Path]::GetPathRoot($fullPath)
    if ([string]::Equals($fullPath, $pathRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathRoot
    }
    return $fullPath.TrimEnd([char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar))
}

function Test-PathIsEqualOrDescendant {
    param(
        [string]$LiteralPath,
        [string]$BasePath
    )

    $normalizedPath = ConvertTo-NormalizedFullPath -LiteralPath $LiteralPath
    $normalizedBase = ConvertTo-NormalizedFullPath -LiteralPath $BasePath
    if ([string]::Equals($normalizedPath, $normalizedBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    $basePrefix = $normalizedBase
    if (-not $basePrefix.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $basePrefix += [System.IO.Path]::DirectorySeparatorChar
    }
    return $normalizedPath.StartsWith($basePrefix, [System.StringComparison]::OrdinalIgnoreCase)
}

$ProjectRoot = ConvertTo-NormalizedFullPath -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ReleaseRoot = Join-Path $ProjectRoot "release"
$PortableRoot = Join-Path $ReleaseRoot "NovelForge-Portable"
$ZipPath = Join-Path $ReleaseRoot ("NovelForge-windows-portable-{0}.zip" -f $Version)
$BuildLogPath = Join-Path $ReleaseRoot ("build_release-{0}.log" -f $Version)
$LauncherSpecRoot = Join-Path $ProjectRoot "dist"
$LauncherSpecPath = Join-Path $ProjectRoot "NovelForge.spec"
$BundledVenv = Join-Path $ProjectRoot ".venv"
$BundledPython = Join-Path $BundledVenv "Scripts\python.exe"
$ResolvedRuntimeRoot = if ([System.IO.Path]::IsPathRooted($RuntimeRoot)) {
    ConvertTo-NormalizedFullPath -LiteralPath $RuntimeRoot
} else {
    ConvertTo-NormalizedFullPath -LiteralPath (Join-Path $ProjectRoot $RuntimeRoot)
}
$PortablePython = Join-Path $ResolvedRuntimeRoot "python.exe"
$StreamlitConfigRoot = Join-Path $ProjectRoot ".streamlit"

if (Test-PathIsEqualOrDescendant -LiteralPath $ProjectRoot -BasePath $ResolvedRuntimeRoot) {
    throw "RuntimeRoot must not equal ProjectRoot or be an ancestor of ProjectRoot; copying it would recursively include the project."
}
if (Test-PathIsEqualOrDescendant -LiteralPath $ResolvedRuntimeRoot -BasePath $PortableRoot) {
    throw "RuntimeRoot must not be PortableRoot or a directory inside PortableRoot; the release directory is recreated during the build."
}
if (Test-PathIsEqualOrDescendant -LiteralPath $PortableRoot -BasePath $ResolvedRuntimeRoot) {
    throw "RuntimeRoot must not contain PortableRoot; copying it would recursively include the release destination."
}

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
Assert-PathExists -LiteralPath $ResolvedRuntimeRoot -Message "Missing self-contained Python runtime: $ResolvedRuntimeRoot"
Assert-PathExists -LiteralPath $PortablePython -Message "RuntimeRoot must contain python.exe at its root."
if (Test-Path -LiteralPath (Join-Path $ResolvedRuntimeRoot "pyvenv.cfg")) {
    throw "RuntimeRoot points to a virtual environment. A copied venv is tied to its build machine; provide a self-contained Python distribution instead."
}

& $PortablePython -c "import streamlit, openai, dotenv, pydantic, httpx"
if (-not $?) {
    throw "The self-contained runtime is missing one or more NovelForge dependencies."
}

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
    "asset_guardrails.py",
    "creative_profile_workflows.py",
    "discussion_assets.py",
    "extraction_presets.py",
    "knowledge_entities.py",
    "knowledge_quality.py",
    "knowledge_workflows.py",
    "llm.py",
    "memory.py",
    "merge.py",
    "retrieval.py",
    "retrieval_eval.py",
    "resource_browser.py",
    "schemas.py",
    "setting_knowledge.py",
    "prompts.py",
    "prompt_options.py",
    "skills.py",
    "source_workflows.py",
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

$directoriesToCopy = @(
    "docs",
    "storage",
    "tools",
    "ui"
)

foreach ($relativePath in $directoriesToCopy) {
    $sourcePath = Join-Path $ProjectRoot $relativePath
    Assert-PathExists -LiteralPath $sourcePath -Message "Missing required directory: $relativePath"
    Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $PortableRoot $relativePath) -Recurse
}

Get-ChildItem -LiteralPath $PortableRoot -Recurse -Force -File |
    Where-Object { $_.Name -like "*~*" -or $_.Name -like "*.bak" -or $_.Name -like "*.tmp" } |
    Remove-Item -Force
Get-ChildItem -LiteralPath $PortableRoot -Recurse -Force -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

Copy-Item -LiteralPath (Join-Path $LauncherSpecRoot "NovelForge.exe") -Destination (Join-Path $PortableRoot "NovelForge.exe")
Copy-Item -LiteralPath $ResolvedRuntimeRoot -Destination (Join-Path $PortableRoot ".runtime") -Recurse

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
    "The bundled .runtime directory is a self-contained Python distribution; do not replace it with a copied virtual environment.",
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
