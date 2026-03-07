---
# Contributing to Gamearr 🎮

First off, thank you for considering contributing to Gamearr! It's people like you who will help make this the definitive PVR for video games.

By contributing to this project, you agree to abide by our code of conduct and license your contributions under the **GPL-3.0 License**.
---

## 🛠️ Getting Started

### Development Environment

Gamearr is built with **Python 3.12 (FastAPI)** and **Vanilla JavaScript**.

1. **Fork the repo** and clone it locally.
2. **Setup a Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Configure Environment**: Copy `.env.example` to `.env` and fill in your IGDB keys and TSV sources.
4. **Run in Dev Mode**:
   ```bash
   python -m backend.main
   ```

---

## 📐 Development Standards

To maintain the "Arr Identity," please follow these core logic rules:

### 1. Filesystem Safety (The Golden Rule)

Gamearr must work on everything from high-end Linux workstations to sensitive Windows SMB shares.

- **ASCII Only:** All filenames and folders must be stripped of non-ASCII characters.
- **Safe Naming:** Use `backend.downloader.get_safe_name()` for any filesystem operations.

### 2. Logging

- **No `print()`:** Use the centralized logger: `from backend.logger import logger`.
- **Throttling:** Do not spam the logs in loops. If reporting progress, use a time-based throttle (e.g., every 2 seconds).

### 3. API & UI

- **Modularity:** Keep the backend logic in the `backend/` modules. `main.py` should only handle routing.
- **Vanilla JS:** We avoid heavy frameworks (React/Vue) to keep the frontend fast and light.
- **API Security:** All new endpoints must be added to the `api_router` to ensure they are protected by the `X-Api-Key` dependency.

---

## 📬 How to Submit Changes

1. **Check Discussions:** Before starting a major feature (like a new platform or downloader), open a thread in **GitHub Discussions** to ensure it aligns with the roadmap.
2. **Branching:** Create a feature branch (`git checkout -b feature/AmazingFeature`).
3. **Commit Messages:** Use clear, descriptive messages (e.g., `[FEAT]: Add PS2 Metadata Support`).
4. **Pull Requests:**
   - Ensure your code is linted and tested.
   - Use the provided PR template.
   - Be prepared for a code review!

---

## 🎮 Adding New Platforms

If you are adding a new console platform, ensure you provide:

- A reliable TSV or API data source.
- Standardized Title ID parsing logic.
- Metadata mapping for IGDB categories.

---

## ⚖️ A Note on Legalities

Gamearr is a research and management tool. **Do not** submit code that includes hardcoded links to copyrighted content, internal proprietary decryption keys, or any materials that would violate the project's neutral "Parser/Manager" status.

---
