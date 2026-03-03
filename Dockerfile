FROM python:3.12-slim

# INSTALL DEPENDENCIES
RUN apt-get update && apt-get install -y \
	aria2 \
	curl \
	gcc \
	make \
	libc6-dev \
    gosu \
	&& rm -rf /var/lib/apt/lists/*

# INSTALL PKG2ZIP
RUN curl -L https://github.com/mmozeiko/pkg2zip/archive/refs/tags/v1.8.tar.gz | tar xz \
	&& cd pkg2zip-1.8 \
	&& make CFLAGS="-O2 -Wno-error=format-truncation" \
	&& mv pkg2zip /usr/local/bin/ \
	&& cd .. && rm -rf pkg2zip-1.8

# SETUP WORKSPACE
WORKDIR /app

# INSTALL PYTHON DEPENDENCIES
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# COPY PROJECT FILES
COPY . .

# ENVIRONMENT DEFAULTS
# Can be overriden in your docker-compose, .env, or stack.env
ENV INCOMPLETE_DIR=/downloads \
    LIBRARY_DIR=/library \
    DB_PATH=/app/data/gamearr.db \
    PORT=8000 \
    PUID=1000 \
    PGID=1000

# CREATE VOLUME POINTS
RUN mkdir -p /downloads /library /app/data
VOLUME ["/app/data", "/downloads", "/library"]

# ENSURE ENTRYPOINT EXEC
RUN chmod +x /app/entrypoint.sh

# LAUNCH PROCESSES
ENTRYPOINT ["/app/entrypoint.sh"]
