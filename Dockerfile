FROM python:3.12-slim

# INSTALL DEPENDENCIES
# aria2 for downloads and the build tools for pkg2zip extraction
RUN apt-get update && apt-get install -y \
	aria2 \
	curl \
	gcc \
	make \
	libc6-dev \
	&& rm -rf /var/lib/apt/lists/*

# INSTALL PKG2ZIP
# Download an compile the latest source to ensure compatibility
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
ENV INCOMPLETE_DIR=/downloads
ENV LIBRARY_DIR=/library
ENV DB_PATH=/app/data/gamearr.db

# CREATE VOLUME POINTS
RUN mkdir -p /downloads /library /app/data
VOLUME ["/app/data", "/downloads", "/library"]

# COPY ENTRYPOINT
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN chmod -R 755 /app

# LAUNCH PROCESSES
ENTRYPOINT ["/app/entrypoint.sh"]
