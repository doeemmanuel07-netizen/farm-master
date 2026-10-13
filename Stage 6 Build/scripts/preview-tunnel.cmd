@echo off
rem Started by start-preview.ps1: a Cloudflare Quick Tunnel to the local API.
"%~1" tunnel --no-autoupdate --url http://127.0.0.1:8000 > "%~dp0..\.preview\tunnel.log" 2>&1
