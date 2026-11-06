@echo off
rem Program note: forward arguments to the PowerShell one-click launcher.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
