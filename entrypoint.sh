#!/bin/bash
# Start the worker in the background
python3 -m backend.worker &

# Start the Web UI/API in the foreground
# (This keeps the container alive)
exec python3 main.py
