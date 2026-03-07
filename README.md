# Gamearr (v0.4.47)

**Gamearr** is the definitive Video Game PVR for the `*arr` ecosystem. It automates the discovery, metadata collection, and management of you video game library with a focus on ease of use and the classic `*arr` aesthetic.

![GitHub License](https://img.shields.io/badge/license-GPL--3.0-green)
![Python Version](https://img.shields.io/badge/python-3.12-blue)
![Docker Ready](https://img.shields.io/badge/docker-ready-emerald)

---

## Features

- **Modern UI:** Built to match the reliability and intuition of Sonarr/Radarr.
- **Smart Scout:** Automated metadata fetching via IGDB (Covers, Summaries, and Ratings).
- **Multi-Platform Support:** Currently supporting PSX, PSP, and PSVita via NoPayStation (TSV).
- **Filesystem Safety:** Strict ASCII-only naming conventions for maximum compatibility with NAS/SMB shares.
- **Bulk Operations:** Monitor, Unmonitor, and Refresh your library in seconds.
- **Docker-First:** Native support for PUID/PGID to ensure seamless NAS permission management.

---

## Quick Start (Docker Compose)

The easiest way to run Gamearr is via Docker Compose.

```yaml
services:
  gamearr:
    build: .
    container_name: gamearr
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
      - IGDB_CLIENT_ID=YOUR_IGDB_ID_HERE
      - IGDB_CLIENT_SECRET=YOUR_IGDB_SECRET_HERE
      - GAME_SOURCE_VITA=your_tsv_link
      - GAME_SOURCE_PSP=your_tsv_link
      - GAME_SOURCE_PSX=your_tsv_link
    volumes:
      - ./config:/app/data # Database and Logs
      - /path/to/downloads:/downloads # Incomplete downloads
      - /path/to/games:/library # Your Game Library
    ports:
      - 8000:8000
    restart: unless-stopped
```

---

## SETUP: IGDB Metadata

Gamearr uses the IGDB API for high-quality game art.

1. Go to the [Twitch Developer Portal](https://dev/twitch.tv/console).
2. Register a New Application (Category: "Other").
3. Obtain your **Client ID** and **Client Secret**.
4. Add them to your environment variables.

---

## Legal Disclaimer

**Gamearr is for educational and library management purposes only.**
Gamearr is a metadata aggregator and filesystem manager. It does not host, provide, or distribute any copyrighted content. The developers of Gamearr are not responsible for how users choose to utilize the tool. Users are encouraged to support game developers by purchasing titles they enjoy.

---

## Contributing

Gamearr is an open-source project. If you'd like to contribute:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

**License:** Distributed under the [GPL-3.0 License](LICENSE).

---

## Environment Template

**File:** `.env.example`

```bash
# --- Gamearr Configuration ---
PORT=8000
TZ=UTC

# --- Permissions ---
PUID=1000
PGID=1000

# --- Source Manifests (TSV URLs) ---
# Provide URLs for your preferred TSV data sources.
# Standard NPS TSV links can be placed here.
GAME_SOURCE_VITA=
GAME_SOURCE_PSP=
GAME_SOURCE_PSX=

# --- Metadta (Twitch Developer Portal) ---
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=

# --- Paths (inside the container) ---
DB_PATH=/app/data/gamearr.db
INCOMPLETE_DIR=/downloads
LIBRARY_DIR=/library
```

---

## Feature Roadmap

Gamearr is currently in **Active Alpha (v0.4.x)**. Our goal is to reach parity with the core features of the \*arr stack while respecting the unique requirements of video game preservation.

| Version  | Focus                | Key Objectives                                                                                                    |
| :------- | :------------------- | :---------------------------------------------------------------------------------------------------------------- |
| **v0.5** | **Connectivity**     | **NAS Integration:** Direct support for FTP, SMB, and NFS mounting for "Seedbox-to-Home" workflows. ARM Support!               |
| **v0.6** | **Expansion**        | **Platform Parity:** Adding support for full platform metadata and discovery.                                     |
| **v0.7** | **Advanced Sources** | **\*Nab:** Integration with **Torznab** (Torrents) and **Newznab** (Usenet) for a truly automated PVR experience. |
| **v0.8** | **Intelligence**     | **Import Lists:** Auto-sync your library based on Steam Wishlists, IGDB Collections, or Metacritic top-charts.    |
| **v0.9** | **Refinement**       | **Auditing:** Automated file-integrity checks and "Media Info" style game version detection.                      |
| **v1.0** | **Full Release**     | Stable API, full documentation, and "One-Click" community app-store templates (Unraid/TrueNAS/Docker)             |

Want a specific feature or platform? Open an Issue or join the discussion!

---

**Licenses:**

- [GNU GPL v3](LICENSE)
- Copyright 2026
