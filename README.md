# Discord VPS Creator — `!` commands + tmate only

## Commands
- `!create-vps <@user|username>` → spins up Ubuntu container, starts tmate, DMs link.
- `!kvm-list` → list all VPS with owner and status.
- `!kvm-ssh <container>` → prints tmate link again.
- `!kvm-start|stop|restart|logs <container>`
- `!kvm-destroy <container>` → manual removal (no auto).

## Install & Run
```bash
bash install.sh
python3 bot.py
