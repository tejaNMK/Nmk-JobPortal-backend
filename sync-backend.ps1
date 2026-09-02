$Source = "D:\Projects\NMK_Job_Portal\JobPortalBackend\nmk-jobportal-backend\nmk-jobportal-userservice"
$Destination = "D:\Projects\NMK_Job_Portal\nmk-jobportal-backend-secondary"

Write-Host "Starting synchronization..."
Write-Host ""
Write-Host "Source      : $Source"
Write-Host "Destination : $Destination"
Write-Host ""

robocopy $Source $Destination /MIR /XD "$Source\.git" "$Destination\.git" /XF "$Destination\.gitignore" "sync-backend.ps1"

if ($LASTEXITCODE -le 7) {
    Write-Host ""
    Write-Host "Synchronization completed successfully."
} else {
    Write-Host ""
    Write-Host "Synchronization failed. Robocopy exit code: $LASTEXITCODE"
}