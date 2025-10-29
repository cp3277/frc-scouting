# FRC QR Scouting App

description: >
  A lightweight, local-first scouting system for FIRST Robotics Competition (FRC).
  Scouts record match data, generate QR codes, and send results to a hub device for aggregation.
  Designed for offline use and later data analysis.

overview:
  - Scouts open the local web page (frontend/scouting_form.html) on a phone or tablet.
  - They record scoring actions using a reef image and simple count fields.
  - The page encodes data into a QR code for scanning.
  - A hub device scans or imports the QR to aggregate match data.
  - Collected data is stored for later analysis or export.

structure:
  frc-qr-scouting-app/
    frontend/
      scouting_form.html   # Main UI for data entry and QR generation
    hub/
      main.py              # Backend for data collection
    data/                  # Stored scouting data
    requirements.txt
    README.md
    .gitignore

features:
  - Interactive reef image for scoring input by level
  - Barge algae and processor count tracking
  - QR code generation for fast offline data transfer
  - Offline-first design for competition environments
  - Hub for data aggregation and export

setup:
  - Clone repository:
      git clone https://github.com/cp3277/frc-qr-scouting-app.git
      cd frc-qr-scouting-app

  - Create and activate virtual environment:
      python -m venv venv
      .\venv\Scripts\activate        # Windows
      source venv/bin/activate       # macOS/Linux

  - Install dependencies:
      pip install -r requirements.txt

  - Run frontend:
      Open frontend/scouting_form.html in a browser
      (Optional: use VS Code Live Server for auto-reload)

  - Run backend hub:
      python hub/main.py

tech_stack:
  frontend: HTML, CSS, JavaScript
  backend: Python (Flask or FastAPI)
  storage: JSON, CSV, or SQLite
  qr_handling: JavaScript (frontend), Python (backend)
  version_control: Git

gitignore:
  - venv/
  - __pycache__/
  - data/
  - reef.png
  - reef_base64.txt

development_notes:
  - Primary environment: VS Code on Windows
  - GitHub Copilot assists with:
      - HTML/JS interactivity
      - Flask endpoints for data handling
      - Data formatting and QR parsing logic
  - Focus on maintainability and offline compatibility
