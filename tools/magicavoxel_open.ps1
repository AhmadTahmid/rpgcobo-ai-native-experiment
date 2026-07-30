Using Module  .\gettool.psm1

param(
    [string]$Arg1
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Output "SK-OUTPUT popen_start"

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$TOOL_DIR = "..\work\MagicaVoxel"
$TOOL_URL = "https://github.com/ephtracy/ephtracy.github.io/releases/download/0.99.7/MagicaVoxel-0.99.7.2-win64.zip"
$INNER_DIR = "\MagicaVoxel-0.99.7.2-win64"

GetTool -TOOL_DIR $TOOL_DIR -TOOL_URL $TOOL_URL -INNER_DIR $INNER_DIR

# junction
if( Test-Path ..\work\MagicaVoxel\vox\3x3x3.vox) {
    Remove-Item -Path ..\work\MagicaVoxel\vox -Recurse -Force
    &cmd /c mklink /j ..\work\MagicaVoxel\vox ..\project\resource\vox
}

Write-Output "SK-OUTPUT popen_launch"

# launch MagicaVoxel
Set-Location -Path $TOOL_DIR
$proc = Start-Process -FilePath ".\MagicaVoxel.exe" -ArgumentList $Arg1 -PassThru
while ($proc.MainWindowHandle -eq 0) {
    Start-Sleep -Milliseconds 20
    $proc.Refresh()
}

Write-Output "SK-OUTPUT popen_done"
