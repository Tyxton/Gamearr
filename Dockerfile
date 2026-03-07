# BUILD DEPENDENCIES
FROM python:3.12-slim AS builder

# INSTALL BUILD DEPENDENCIES
RUN apt-get update && apt-get install -y \
	curl \
	gcc \
	make \
	libc6-dev \
	&& rm -rf /var/lib/apt/lists/*

# INSTALL PKG2ZIP
RUN curl -L https://github.com/mmozeiko/pkg2zip/archive/refs/tags/v1.8.tar.gz | tar xz \
	&& cd pkg2zip-1.8 \
	&& make CFLAGS="-O2 -Wno-error=format-truncation" \
	&& cp pkg2zip /usr/local/bin/

# FINAL PRODUCTION IMAGE
FROM python:3.12-slim

# INSTALL RUNTIME DEPENDENCIES
RUN apt-get update && apt-get install -y \
    aria2 \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# COPY THE PKG2ZIP BINARY FROM THE BUILDER
COPY --from=builder /usr/local/bin/pkg2zip /usr/local/bin/pkg2zip

# SETUP WORKSPACE
WORKDIR /app

# INSTALL PYTHON DEPENDENCIES
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# COPY PROJECT FILES
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY entrypoint.sh .
COPY main.py .

# ENVIRONMENT DEFAULTS
# Can be overriden in your docker-compose, .env, or stack.env
ENV INCOMPLETE_DIR=/downloads \
    LIBRARY_DIR=/library \
    DB_PATH=/app/data/gamearr.db \
    PORT=8000 \
    PUID=1000 \
    PGID=1000 \
    PYTHONUNBUFFERED=1

# ENSURE ENTRYPOINT EXEC
RUN chmod +x /app/entrypoint.sh && \
    mkdir -p /downloads /library /app/data

EXPOSE 8000

# LAUNCH PROCESSES
ENTRYPOINT ["/app/entrypoint.sh"]
