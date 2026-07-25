# Local-only asset generation tool. NOT part of the shipped site - the site stays
# static HTML/CSS/JS with zero build step and zero runtime dependency on fal.ai.
# Run this by hand whenever a new raster asset is needed, then reference the
# resulting file from assets/images/ in plain img/CSS like any other static image.
#
# Usage:
#   ./generate-image.ps1 -Prompt "..." -OutFile "hero-lantern.png" -Model "fal-ai/flux/dev" -Size "landscape_16_9"
#
# The key is read from the local .env next to this script (gitignored, never committed).

param(
    [Parameter(Mandatory = $true)][string]$Prompt,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string]$Model = "fal-ai/flux/dev",
    [string]$Size = "landscape_16_9",
    [int]$Steps = 28
)

$ErrorActionPreference = "Stop"

$envPath = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $envPath)) {
    throw "No .env found at $envPath - expected a local FAL_KEY=... line (never commit this file)."
}
$falKeyLine = Get-Content $envPath | Where-Object { $_ -match '^FAL_KEY=' }
if (-not $falKeyLine) { throw "FAL_KEY not found in $envPath" }
$falKey = ($falKeyLine -split '=', 2)[1].Trim()

$outDir = Join-Path $PSScriptRoot "..\assets\images"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$outPath = Join-Path $outDir $OutFile

$body = @{
    prompt          = $Prompt
    image_size      = $Size
    num_images      = 1
    num_inference_steps = $Steps
} | ConvertTo-Json

Write-Host "Requesting image from $Model ..."
$response = Invoke-RestMethod -Uri "https://fal.run/$Model" `
    -Method Post `
    -Headers @{ Authorization = "Key $falKey" } `
    -ContentType "application/json" `
    -Body $body

$imageUrl = $response.images[0].url
if (-not $imageUrl) { throw "No image URL in response: $($response | ConvertTo-Json -Depth 10)" }

Write-Host "Downloading to $outPath"
Invoke-WebRequest -Uri $imageUrl -OutFile $outPath

Write-Host "Done: $outPath"
