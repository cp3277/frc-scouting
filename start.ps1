param(
  [string]$DatabaseUrl = $null,
  [string]$GroqApiKey = $null,
  [switch]$InstallDependencies
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "start.ps1: running from $ScriptDir"

# Ensure Python is available
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
  Write-Error "Python not found in PATH. Please install Python 3.8+ and retry."
  exit 1
}

# Create venv if missing
$venvPath = Join-Path $ScriptDir 'venv'
if (-not (Test-Path $venvPath)) {
  Write-Host "Creating virtual environment at $venvPath..."
  & python -m venv $venvPath
}

# Activate venv
$activate = Join-Path $venvPath 'Scripts\Activate.ps1'
if (Test-Path $activate) {
  Write-Host "Activating virtual environment..."
  & $activate
} else {
  Write-Warning "Could not find activation script at $activate. Continuing without venv activated."
}

# Load .env file if present
$envFile = Join-Path $ScriptDir '.env'
if (Test-Path $envFile) {
  Write-Host "Loading environment variables from .env"
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#')) {
      $parts = $line -split '=', 2
      if ($parts.Count -eq 2) {
        $key = $parts[0].Trim()
        $val = $parts[1].Trim().Trim('"')
        Set-Item -Path "env:$key" -Value $val
      }
    }
  }
}

# Override with parameters if provided
if ($DatabaseUrl) { $env:DATABASE_URL = $DatabaseUrl; Write-Host "DATABASE_URL set from parameter." }
if ($GroqApiKey)   { $env:GROQ_API_KEY = $GroqApiKey; Write-Host "GROQ_API_KEY set from parameter." }

# Optionally install dependencies
if ($InstallDependencies) {
  if (Test-Path (Join-Path $ScriptDir 'requirements.txt')) {
    Write-Host "Installing Python dependencies from requirements.txt..."
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
  } else {
    Write-Warning "requirements.txt not found in $ScriptDir"
  }
}

# Warn about ngrok (app may attempt to start it)
if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
  Write-Warning "ngrok not found in PATH. Public tunneling will not be available unless you install ngrok."
}

Write-Host "Starting Flask app (hub/main.py)..."
Set-Location (Join-Path $ScriptDir 'hub')

# Launch the app (run in foreground so logs are visible)
& python -u main.py
