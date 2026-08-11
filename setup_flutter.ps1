$zipPath = "$env:USERPROFILE\.download_manager\downloads\Compressed\flutter_windows_3.44.9-stable.zip"
$partPath = "$zipPath.part"

Write-Host "Waiting for Flutter download to complete..."
while (Test-Path $partPath) {
    Start-Sleep -Seconds 10
    Write-Host "Still downloading..."
}

if (-not (Test-Path $zipPath)) {
    Write-Host "Error: Download did not complete successfully. Zip file not found at $zipPath"
    exit 1
}

Write-Host "Download complete. Extracting to C:\src\flutter..."
$extractDir = "C:\src"
if (-not (Test-Path $extractDir)) {
    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
}

# The zip contains a "flutter" folder at its root, so extracting it to C:\src will create C:\src\flutter
Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
Write-Host "Extraction complete."

$flutterBin = "C:\src\flutter\bin"

Write-Host "Adding Flutter to User PATH..."
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$flutterBin*") {
    $newPath = $userPath + (if ($userPath.EndsWith(";")) { "" } else { ";" }) + $flutterBin
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host "Flutter added to User PATH."
} else {
    Write-Host "Flutter is already in User PATH."
}

Write-Host "Running flutter doctor..."
# Set the process-level PATH so flutter works in this script
$env:PATH = $env:PATH + ";" + $flutterBin
flutter doctor
Write-Host "Setup complete!"
