@echo off
set ZIP_NAME=project.zip

echo Zipping project...

REM Remove old zip if it exists
if exist "%ZIP_NAME%" (
    echo Removing old %ZIP_NAME%...
    del "%ZIP_NAME%"
)

REM Create new zip using PowerShell
powershell -Command "Compress-Archive -Path * -DestinationPath '%ZIP_NAME%' -Force -CompressionLevel Optimal"

echo Done!
echo Created: %ZIP_NAME%
pause
