#!/usr/bin/env bash
set -euo pipefail

SOCK="/tmp/tmate.sock"
OUT="/tmp/tmate-ssh.txt"

# start a detached tmate session
tmate -S "$SOCK" new-session -d || true

# wait up to 60s for tmate to be ready
for i in {1..60}; do
  if tmate -S "$SOCK" display -p '#{tmate_ssh}' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# write both ssh and web links (tmate may return several lines)
{
  echo "SSH: $(tmate -S "$SOCK" display -p '#{tmate_ssh}')"
  echo "Web: $(tmate -S "$SOCK" display -p '#{tmate_web}')"
} > "$OUT" || true

# keep printing the file periodically so `docker logs` shows it, and container stays alive
while true; do
  [ -f "$OUT" ] && cat "$OUT" || true
  sleep 120
done
