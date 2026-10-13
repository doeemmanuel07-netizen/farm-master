@echo off
rem Started by start-preview.ps1: runs the API in public preview mode on
rem 127.0.0.1 only, with the secrets from .preview\secret.env.
setlocal
set "BUILD=%~dp0.."
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%BUILD%\.preview\secret.env") do set "%%A=%%B"
set "FARM_MASTER_PUBLIC_PREVIEW=1"
set "PYTHONUNBUFFERED=1"
cd /d "%BUILD%\backend"
"%~1" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1 --no-server-header --log-level info > "%BUILD%\.preview\app.log" 2>&1
