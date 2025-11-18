@echo off
cd /d "%~dp0"
echo.
echo =================================================
echo  AUTO-SYNC IS NOW RUNNING - DO NOT CLOSE THIS WINDOW
echo  Watching folder: %cd%
echo =================================================
echo.

:: This line is the only thing that changed – we call git-push.bat with its full path
python -m watchgod ".\git-push.bat" .

echo.
echo Watcher stopped or crashed.
pause