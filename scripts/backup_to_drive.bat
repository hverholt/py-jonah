@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup_to_drive.ps1"
exit /b %ERRORLEVEL%
