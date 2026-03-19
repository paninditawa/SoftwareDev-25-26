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

## Accessibility Requirements

Follow Microsoft accessibility guidance when you change UI code.

1. Every interactive control must be reachable and usable from the keyboard.
2. Keep a visible focus indicator. Do not remove or weaken focus borders.
3. Do not use color alone to show state. Add text, symbols, or spoken feedback.
4. Keep visible text at readable sizes and maintain at least a 4.5:1 text contrast ratio.
5. Do not introduce hard-coded low-contrast overrides.
6. Test the launcher with keyboard-only navigation before you commit.

## Secrets

- `supabase_project.py` contains the shared anon key — this is intentionally committed and safe to share.
- Never add or commit any Supabase service role key.
- `config.py` and `games/config.py` are gitignored for local overrides.

