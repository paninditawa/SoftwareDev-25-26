# Contributing (Simple)

## Quick Start

1. Clone and open the repo.
2. Create and activate a virtual environment.
3. Install dependencies.
4. Run the desktop launcher.

Use these commands from repo root.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python launch_gamespace.py
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python launch_gamespace.py
```

Sign-in works out of the box after cloning. No extra setup needed.

## Before You Commit

1. Run the app and make sure your change works.
2. Do not commit secrets.
3. Keep changes small and focused.

## Secrets

- `supabase_project.py` contains the shared anon key — this is intentionally committed and safe to share.
- Never add or commit any Supabase service role key.
- `config.py` and `testing/config.py` are gitignored for local overrides.

