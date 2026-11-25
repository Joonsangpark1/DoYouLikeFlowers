@echo off
rem Every session: attach robot/cameras to WSL and open Ubuntu. For HIL-SERL demos: start_session.bat -Mode hil
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\start_session.ps1" %*
