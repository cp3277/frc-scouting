# FRC QR Scouting App

description: >
  A lightweight, local-first scouting system for FIRST Robotics Competition (FRC).
  Scouts record match data, generate QR codes, and send results to a hub device for aggregation.
  Designed for offline use and later data analysis with AI-powered insights.

overview:
  - Scouts can use two methods to record data:
    1. Desktop/Tablet: Fill out the scouting form (frontend.html) and generate QR codes
    2. Mobile: Scan QR codes directly using the QR scanner page
  - A hub device aggregates all match data into a PostgreSQL database
  - Data is visualized with charts and tables on the data display page
  - AI agent provides natural language insights and analysis
  - All pages are interconnected with easy navigation

structure:
  frc-qr-scouting-app/
    hub/
      main.py              # Flask backend server
      templates/
        frontend.html      # Scouting form with QR code generation
        index.html         # QR scanner page for mobile devices
        data_display.html  # Data visualization and AI query interface
      certs/              # HTTPS certificates (generated locally)
        localhost.pem
        localhost-key.pem
    setup_certs.py        # Certificate generation script
    scout_radioz.sql      # PostgreSQL database schema
    requirements.txt
    README.md

features:
  - **Scouting Form** (/frontend): Desktop-friendly data entry with QR code generation
  - **QR Scanner** (/scanner): Mobile camera-based QR code scanning
  - **Data Display** (/data-display): Interactive charts, data tables, and AI analysis
  - Tracks autonomous, teleop, capabilities, and endgame performance
  - PostgreSQL database for reliable data storage
  - AI-powered natural language queries for match insights
  - Real-time graphs showing fuel scoring and climb statistics
  - Offline-first design for competition environments
  - Cross-page navigation for easy workflow

setup:
  1. Clone repository:
      git clone https://github.com/cp3277/frc-qr-scouting-app.git
      cd frc-qr-scouting-app

  2. Install mkcert (required for HTTPS/camera access):
     Windows (using Chocolatey):
       choco install mkcert
     
     Windows (manual):
       - Download from https://github.com/FiloSottile/mkcert/releases
       - Add the executable to your PATH

  3. Create and activate virtual environment:
     Windows:
       python -m venv venv
       .\venv\Scripts\Activate.ps1

     macOS/Linux:
       python -m venv venv
       source venv/bin/activate

  4. Install dependencies:
       pip install -r requirements.txt

  5. Setup HTTPS certificates:
       python setup_certs.py
     This will:
     - Install local Certificate Authority
     - Generate certificates in ./certs directory
     - Configure Flask to use the certificates
     - Update .gitignore if needed

  6. Setup PostgreSQL database:
     - Install PostgreSQL if not already installed
     - Create a database named 'scout_radioz'
     - Import the schema:
       psql -U postgres -d scout_radioz -f scout_radioz.sql
     - Configure connection in hub/main.py

  7. Run the application:
     Start the backend hub:
       python hub/main.py
     , Chart.js, jsQR
  backend: Python (Flask), psycopg2
  storage: PostgreSQL database
  qr_handling: 
    - Generation: qrcodejs (frontend)
    - Scanning: jsQR (client-side decoding)
  ai: OpenAI API integration for natural language queries
     - Data Display: https://localhost:5000/data-display
     - On other devices: https://<hub-ip>:5000/
       (Accept the security certificate when prompted)

tech_stack:
  frontend: HTML, CSS, JavaScript
  backend: Python (Flask or FastAPI)
  storage: JSON, CSV, or SQLite
  qr_handling: JavaScript (frontend), Python (backend)
  version_control: Git

security_notes:
  https_certificates:
    - Certificates are required for HTTPS and camera access
    - Generated automatically by setup_certs.py using mkcert
pages:
  frontend (Scouting Form):
    - Desktop/tablet-optimized data entry interface
    - Tracks match number, team number, alliance color
    - Records autonomous fuel and climb performance
    - Teleop fuel scoring with quick +1/+5/+8 buttons
    - Robot capabilities checkboxes (turret, trench, defense, passing)
    - Endgame climb selection (L1/L2/L3)
    - Notes field for qualitative observations
    - Generates QR code with all match data
    - Navigate to scanner or data display pages

  scanner (QR Scanner):
    - Mobile-optimized camera interface
    - Client-side QR code decoding using jsQR
    - Real-time scanning with visual feedback
    - Automatic submission to database on successful scan
    - Camera stop/start controls
    - View list of recently scanned data
    - Navigate to scouting form or data display pages

  data_display (Data Display):
    - Interactive data table showing all match records
    - Bar charts for average fuel scoring by team
    - Stacked bar charts for climb point analysis
    - AI query interface for natural language questions
    - Real-time data updates
    - Navigate to scanner or scouting form pages

gitignore:
  - venv/
  - __pycache__/
  - hub/certs/
  - *.pyc
  - .env
  first_time_setup:
    - Run setup_certs.py to generate certificates
    - Accept the certificate in your browser
    - For iOS devices, install the root CA:
      Settings -> General -> About -> Certificate Trust Settings

gitignore:
  - venv/
  - __pycache__/
  - data/
  - reef.png

development_notes:
  - Primary environment: VS Code on Windows
  - GitHub Copilot assists with:
      - HTML/JS interactivity
  - Focus on maintainability and offline compatibility
