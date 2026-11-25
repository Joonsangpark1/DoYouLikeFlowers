@echo off
rem Flower robot: one-shot laptop setup (double-click). An administrator window will open.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\install_windows.ps1" %*
