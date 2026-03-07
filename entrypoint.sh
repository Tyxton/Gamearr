#!/bin/bash
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "--- Initializing Gamearr Permissions ---"
echo "User ID: $PUID"
echo "Group ID: $PGID"

# create group if it doesn't exist
if ! getent group gamearr >/dev/null; then
    groupadd -g "$PGID" gamearr
fi

# create user if not exists
if ! getent passwd gamearr >/dev/null; then
    useradd -u "$PUID" -g "$PGID" -m -s /bin/bash gamearr
fi

mkdir -p /app/data /library /downloads
chown -R gamearr:gamearr /app/data /library /downloads

# set umask so new files created are readable by host
# 002 allkows group write
umask 002

echo "--- Starting Gamearr Service ---"
exec gosu gamearr python3 main.py
