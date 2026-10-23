<#
.SYNOPSIS
    Builds Astrielle Ring for Skyrim SE/AE and packages it.

.DESCRIPTION
    Measures the ring's fit on the index finger of the hands the game uses (XP32 skeletons, CBBE 3BA female hands and
    the vanilla male hands), builds the worn and ground models with Blender and PyNifly, paints the textures and
    converts them to BC7 with mipmaps (ring 4096 x 2048, gem 2048 x 2048), and generates "[Tinesh] Astrielle Ring.esp"
    with Mutagen. The result is packed as a complete, MO2-installable archive "Astrielle Ring - <version>.zip" in
    -Packages. The vanilla meshes it reads (male hands and the Gold Sapphire Ring, for its frame and shader settings)
    are extracted from the game archives into -Work and reused.
    With -Install the package replaces the contents of the Mod Organizer 2 mod folder (meta.ini is kept); MO2 must be
    closed.

.EXAMPLE
    .\build.ps1 -Install
#>
param(
    [string] $Version = "1.0",
    [string] $Work = "$PSScriptRoot\cache",
    [string] $Out = "$PSScriptRoot\out",
    [string] $Packages = "$PSScriptRoot\dist",
    [string] $Game = "C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition",
    [string] $Mods = "$env:LOCALAPPDATA\ModOrganizer\Skyrim Special Edition\mods",
    [string] $Skeletons = "$Mods\[FRAMEWORK] XP32 Maximum Skeleton Special Extended (XPMSSE)\meshes\actors\character",
    [string] $FemaleHands = "$Mods\[BODY] CBBE 3BA (3BBB)\meshes\actors\character\character assets\femalehands_1.nif",
    [string] $ModFolder = "$Mods\[RING] Astrielle Ring",
    [string] $Blender = "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
    [string] $Texconv = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\texconv.exe",
    [string] $SevenZip = "C:\Program Files\Vortex\resources\app.asar.unpacked\node_modules\7z-bin\win32\7z.exe",
    [switch] $SkipMeshes,
    [switch] $SkipTextures,
    [switch] $Install
)
$ErrorActionPreference = "Continue"
$tools = "$PSScriptRoot\tools"
$plugin = "[Tinesh] Astrielle Ring.esp"
$meshes = Join-Path $Out "meshes"
$textures = Join-Path $Out "textures\Tinesh\AstrielleRing"
$report = Join-Path $Out "meshes_report.json"

$vanilla = Join-Path $Work "refs"
$needed = @("meshes\actors\character\character assets\malehands_1.nif",
    "meshes\actors\character\character assets\malehands_0.nif",
    "meshes\armor\amuletsandrings\goldringsapphire_1.nif", "meshes\armor\amuletsandrings\goldringsapphirego.nif")
$missing = $needed | Where-Object { -not (Test-Path (Join-Path $vanilla $_)) }
if ($missing) { python "$tools\lib\bsa_get.py" "$Game\Data\Skyrim - Meshes0.bsa" $vanilla @missing | Out-Null }
$missing = $needed | Where-Object { -not (Test-Path (Join-Path $vanilla $_)) }
if ($missing) { throw "Vanilla meshes not found: $($missing -join ', ')" }
foreach ($path in @("$Skeletons\character assets female\skeleton_female.nif", "$Skeletons\character assets\skeleton.nif", $FemaleHands)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Not found: $path" }
}

if (-not $SkipMeshes) {
    New-Item -ItemType Directory -Force $Out | Out-Null
    if (Test-Path -LiteralPath $meshes) { Remove-Item -LiteralPath $meshes -Recurse -Force }
    $fit = Join-Path $Out "fit.json"
    $hands = Join-Path $vanilla "meshes\actors\character\character assets"
    python "$tools\finger_fit.py" $fit "$Skeletons\character assets female\skeleton_female.nif" `
        "$Skeletons\character assets\skeleton.nif" $FemaleHands "$hands\malehands_1.nif" "$hands\malehands_0.nif" |
        Select-String -Pattern "FIT|Error|Traceback"
    if ($LASTEXITCODE) { throw "Finger fit failed" }
    & $Blender --background --factory-startup --python "$tools\build_meshes.py" -- $meshes `
        (Join-Path $vanilla "meshes\armor\amuletsandrings") $fit | Select-String -Pattern "Error|Traceback"
    if (-not (Test-Path $report)) { throw "Mesh build failed" }
}

if (-not $SkipTextures) {
    $png = Join-Path $Work "png"
    $dds = Join-Path $Work "dds"
    New-Item -ItemType Directory -Force $png, $dds, $textures | Out-Null
    python "$tools\make_textures.py" $png
    if ($LASTEXITCODE) { throw "Texture painting failed" }
    python "$tools\lib\normal_from_height.py" "$png\ring_h.png" "$dds\AstrielleRing_n.dds" --height luma `
        --strength 12.0 --blur 3.2 --spec metal | Out-Null
    if ($LASTEXITCODE) { throw "Normal map failed" }
    python -c "from PIL import Image; Image.new('RGBA', (256, 256), (128, 128, 255, 204)).save(r'$dds\AstrielleGem_n.png')"
    $sources = @{ "ring_d" = "AstrielleRing_d"; "ring_m" = "AstrielleRing_m"; "gem_d" = "AstrielleGem_d"; "gem_m" = "AstrielleGem_m" }
    foreach ($name in $sources.Keys) {
        Copy-Item "$png\$name.png" "$dds\$($sources[$name]).png"
        & $Texconv -nologo -f BC7_UNORM -m 0 -y -o $textures "$dds\$($sources[$name]).png" | Out-Null
        if ($LASTEXITCODE) { throw "texconv failed: $name" }
    }
    & $Texconv -nologo -f BC7_UNORM -y -o $textures "$dds\AstrielleRing_n.dds" | Out-Null
    & $Texconv -nologo -f BC7_UNORM -m 0 -y -o $textures "$dds\AstrielleGem_n.png" | Out-Null
    if ($LASTEXITCODE) { throw "texconv failed: normal maps" }
}

dotnet run -c Release --project "$PSScriptRoot\plugin" -- "$Game\Data\Skyrim.esm" (Join-Path $Out "plugin") $report $Version
if ($LASTEXITCODE) { throw "Plugin generation failed" }

$stage = Join-Path $Out "package"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
$stageMeshes = Join-Path $stage "meshes\Tinesh\AstrielleRing"
$stageTextures = Join-Path $stage "textures\Tinesh\AstrielleRing"
New-Item -ItemType Directory -Force $stageMeshes, $stageTextures | Out-Null
Copy-Item -LiteralPath (Join-Path $Out "plugin\$plugin") -Destination $stage
foreach ($name in @("AstrielleRingF_1", "AstrielleRing_1", "AstrielleRing_0", "AstrielleRingGO")) {
    Copy-Item -LiteralPath (Join-Path $meshes "$name.nif") -Destination $stageMeshes
}
foreach ($name in @("AstrielleRing_d", "AstrielleRing_n", "AstrielleRing_m", "AstrielleGem_d", "AstrielleGem_n", "AstrielleGem_m")) {
    Copy-Item -LiteralPath (Join-Path $textures "$name.dds") -Destination $stageTextures
}

New-Item -ItemType Directory -Force $Packages | Out-Null
$package = Join-Path $Packages "Astrielle Ring - $Version.zip"
if (Test-Path -LiteralPath $package) { Remove-Item -LiteralPath $package -Force }
& $SevenZip a -tzip -mx=9 $package "$stage\*" | Out-Null
if ($LASTEXITCODE) { throw "Packaging failed" }
"{0}  {1:N1} MB" -f $package, ((Get-Item -LiteralPath $package).Length / 1MB)

if ($Install) {
    if (Get-Process ModOrganizer -ErrorAction SilentlyContinue) { throw "Close Mod Organizer 2 before installing." }
    New-Item -ItemType Directory -Force -Path $ModFolder | Out-Null
    Get-ChildItem -LiteralPath $ModFolder | Where-Object { $_.Name -ne "meta.ini" } | Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $stage | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $ModFolder -Recurse -Force }
    Write-Host "Installed to $ModFolder"
}
