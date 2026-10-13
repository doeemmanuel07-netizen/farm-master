#!/usr/bin/env bash
# Restarts the Farm Master public preview (app + Cloudflare Quick Tunnel) and
# prints the new link. Pass --stop to stop it, --install to also restart it at
# every Windows sign-in. The work is done by start-preview.ps1 next to this file.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
args=()
for a in "$@"; do
  case "$a" in
    --stop) args+=(-Stop) ;;
    --install) args+=(-Install) ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$here/start-preview.ps1")" "${args[@]}"
