#!/usr/bin/env bash
set -euo pipefail

SOCK="/tmp/tmate.sock"
OUT="/tmp/tmate-ssh.txt"

# start a detached tmate session if not already
tmate -S "$SOCK" new-session -d || true

# wait up to 60 seconds for tmate to be ready
for i in $(seq 1 60); do
  if tmate -S "$SOCK" display -p '#{tmate_ssh}' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# write ssh and web links
{
  echo "SSH: $(tmate -S "$SOCK" display -p '#{tmate_ssh}' 2>/dev/null || true)"
  echo "Web: $(tmate -S "$SOCK" display -p '#{tmate_web}' 2>/dev/null || true)"
} > "$OUT" || true

# Keep logging the file so docker logs show it and container doesn't exit
while true; do
  if [ -f "$OUT" ]; then
    cat "$OUT"
  fi
  sleep 30
done
