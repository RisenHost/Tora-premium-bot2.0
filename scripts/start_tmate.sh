#!/usr/bin/env bash
set -euo pipefail

SOCK="/tmp/tmate.sock"
OUT="/tmp/tmate-ssh.txt"

# Start detached tmate session (ignore if already running)
tmate -S "$SOCK" new-session -d || true

# Wait up to 60s for tmate ready
for i in {1..60}; do
  if tmate -S "$SOCK" display -p '#{tmate_ssh}' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Write SSH and Web links to file
{
  echo "SSH: $(tmate -S "$SOCK" display -p '#{tmate_ssh}')"
  echo "Web: $(tmate -S "$SOCK" display -p '#{tmate_web}')"
} > "$OUT" || true

# Keep printing the file periodically so logs show session info and container stays alive
while true; do
  [ -f "$OUT" ] && cat "$OUT" || true
  sleep 120
done
