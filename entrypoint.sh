#!/bin/bash
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Adjusting permissions for user $PUID..."

if ! id -u gamearr > /dev/null 2>&1; then
    groupadd -g $PGID gamearr
    useradd -u $PUID -g gamearr -m gamearr
fi

chown -R $PUID:$PGID /app/data /library

(sleep 5 && gosu gamearr python3 -m backend.worker) &
echo "Launching application..."
exec gosu gamearr python3 main.py
