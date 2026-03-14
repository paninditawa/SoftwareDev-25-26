# Contributing (Simple)

## Quick Start

1. Clone and open the repo.
2. Create and activate a virtual environment.
3. Install dependencies.
4. Set your Firebase API key.
5. Run the desktop launcher.

Use these commands from repo root.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:FIREBASE_API_KEY="YOUR_FIREBASE_WEB_API_KEY"
python launch_gamespace.py
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export FIREBASE_API_KEY="YOUR_FIREBASE_WEB_API_KEY"
python launch_gamespace.py
```

## Before You Commit

1. Run the app and make sure your change works.
2. Do not commit secrets.
3. Keep changes small and focused.

## Secrets

- Use `.streamlit/secrets.toml` or `testing/.streamlit/secrets.toml` for local keys.
- Keep `REPLACE_WITH_FIREBASE_WEB_API_KEY` in any committed template files.

## Optional Legacy Run (Streamlit)

```bash
cd testing
streamlit run main.py
```
