# HelloWorld GameSpace

Accessible collection of mini-games with a desktop-first launcher, Firebase login, and built-in voice announcements.

New contributors can follow the short setup guide in `CONTRIBUTING.md`.

## Quick Start (Windows PowerShell)

Run these from repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:FIREBASE_API_KEY="YOUR_FIREBASE_WEB_API_KEY"
python launch_gamespace.py
```

## Recommended: Desktop Launcher

The main way to run this project is the desktop app launcher.

### 1) Clone and enter the repo

```bash
git clone <YOUR_REPO_URL>
cd SoftwareDev-Test
```

### 2) Create a virtual environment

```powershell
python -m venv .venv
```

### 3) Activate the environment

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 4) Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5) Configure Firebase API key

The launcher requires Firebase email/password auth.

Choose one option:

Option A: environment variable

```powershell
$env:FIREBASE_API_KEY="YOUR_FIREBASE_WEB_API_KEY"
```

```bash
export FIREBASE_API_KEY="YOUR_FIREBASE_WEB_API_KEY"
```

Option B: local secrets file (do not commit)

```toml
firebase_api_key = "YOUR_FIREBASE_WEB_API_KEY"
```

Place that file at either of these paths:

- .streamlit/secrets.toml
- testing/.streamlit/secrets.toml

### 6) Run the desktop app

```bash
python launch_gamespace.py
```

## Desktop Features

- Keyboard-first navigation.
- Built-in spoken focus/context announcements.
- Firebase account sign-in/sign-up/delete account.
- Launch support for Hangman, Maze, Mad Libs, Connect 4, Apples to Apples, and Battleship.

## Build Windows Executable (Optional)

From repo root in PowerShell:

```powershell
.\build_launcher.ps1 -Clean
```

Output folder:

- dist/HelloWorldGameSpace

Run:

- dist/HelloWorldGameSpace/HelloWorldGameSpace.exe

## Troubleshooting Quick Notes

- If login says Firebase key is missing, set FIREBASE_API_KEY or create one of the secrets files listed above.
- If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

- If pygame fails on macOS, install SDL packages:

```bash
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf pkg-config
```

## Streamlit Launcher (Legacy / Optional)

Streamlit still works for compatibility/testing, but the desktop launcher is the primary experience.

From repo root:

```bash
cd testing
streamlit run main.py
```