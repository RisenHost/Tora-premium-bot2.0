#!/usr/bin/env bash
set -euo pipefail

SOCK="/tmp/tmate.sock"
OUT="/tmp/tmate-ssh.txt"

# Start a detached tmate session and wait until it's ready
tmate -S "$SOCK" new-session -d || true
for i in {1..60}; do
  if tmate -S "$SOCK" display -p '#{tmate_ssh}' >/dev/null 2>&1; then break; fi
  sleep 1
done

{
  echo "SSH: $(tmate -S "$SOCK" display -p '#{tmate_ssh}')"
  echo "Web: $(tmate -S "$SOCK" display -p '#{tmate_web}')"
} | tee "$OUT"

# Keep container alive and reprint link periodically
while true; do
  [ -f "$OUT" ] && cat "$OUT" || true
  sleep 120
done
