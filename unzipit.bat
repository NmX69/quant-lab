@echo off
setlocal

REM === CONFIG: EDIT THIS IF YOUR PROJECT PATH IS DIFFERENT ===
set "PROJECT_DIR=C:\Users\neonm\Desktop\Python\quant-lab"
REM ===========================================================

set "ZIP_NAME=update_bundle.zip"
set "DOWNLOAD_DIR=%USERPROFILE%\Downloads"
set "ZIP_PATH=%DOWNLOAD_DIR%\%ZIP_NAME%"

echo Looking for "%ZIP_PATH%" ...

if not exist "%ZIP_PATH%" (
    echo.
    echo ERROR: "%ZIP_NAME%" not found in "%DOWNLOAD_DIR%".
    echo Make sure you've downloaded the file and it is named exactly "%ZIP_NAME%".
    echo.
    pause
    exit /b 1
)

echo Found "%ZIP_NAME%".
echo Project directory: "%PROJECT_DIR%"
echo.

if not exist "%PROJECT_DIR%" (
    echo ERROR: Project directory does not exist:
    echo   "%PROJECT_DIR%"
    echo.
    pause
    exit /b 1
)

echo Unzipping into project directory...
echo (Existing files with the same name will be overwritten.)

powershell -Command "Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%PROJECT_DIR%' -Force"

if errorlevel 1 (
    echo.
    echo ERROR: Expand-Archive failed.
    echo.
    pause
    exit /b 1
)

echo.
echo Done! Files from "%ZIP_NAME%" have been extracted into:
echo   "%PROJECT_DIR%"
echo.
pause
endlocal
