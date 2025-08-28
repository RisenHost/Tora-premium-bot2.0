#!/usr/bin/env bash
set -euo pipefail

SOCKET="/tmp/tmate.sock"
OUTTXT="/tmp/tmate-ssh.txt"

if [ ! -f /etc/ssh/ssh_host_rsa_key ]; then
  ssh-keygen -A
fi

/usr/sbin/sshd -D &
tmate -S "$SOCKET" new-session -d
for i in {1..60}; do
  if tmate -S "$SOCKET" display -p '#{tmate_ssh}' >/dev/null 2>&1; then break; fi
  sleep 1
done

{
  echo "SSH: $(tmate -S "$SOCKET" display -p '#{tmate_ssh}')"
  echo "Web: $(tmate -S "$SOCKET" display -p '#{tmate_web}')"
} | tee "$OUTTXT"

while true; do cat "$OUTTXT"; sleep 120; done
