# SoftwareDev-Test

# Accessible Game Space

## Requirements
- Python 3.10+
- Windows or macOS (TTS supports macOS `say` and `pyttsx3` fallback)

## macOS setup notes

If you're running on macOS, follow these steps before installing Python packages to ensure native libraries (SDL used by `pygame`) are available:

- Install Homebrew if you don't have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

- Install SDL dependencies (may be required for `pygame`):

```bash
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf pkg-config
```

Then create and activate a virtual environment and install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Note: The repo uses `pyttsx3` as a fallback TTS engine. On macOS this may require additional packages like `pyobjc` (pip will usually install what it needs), but if TTS fails you can still use the `say` backend via the `tts` helper.

To run the maze game from the repo root on macOS:

```bash
# Run the Streamlit UI
cd testing
streamlit run main.py

# Or run the maze script directly from repo root
python -m maze_game
```

## Installation
1. Clone the repository
2. Install dependencies:

   pip install -r requirements.txt

## Running the App
From the root folder:

   cd testing
   streamlit run main.py

This will launch the Streamlit interface.  
Use the sidebar to navigate to Connect 4 and click "Launch Game" to open the PyGame window.

## Running the Desktop Launcher

The recommended shell for the accessible GameSpace is now the desktop launcher instead of Streamlit.

From the repo root:

```bash
python launch_gamespace.py
```

The desktop launcher provides:

- Firebase email/password login for the full platform
- Built-in spoken focus announcements without relying on an external screen reader
- Keyboard-first page navigation
- Native desktop support for Hangman, Maze, Mad Libs, Connect 4, Apples to Apples, and Battleship
- Account actions like sign out and delete account

## Building a Windows Executable

From the repo root in PowerShell:

```powershell
./build_launcher.ps1 -Clean
```

This creates a packaged app folder at:

```text
dist/HelloWorldGameSpace/
```

Run the launcher from that folder using:

```text
HelloWorldGameSpace.exe
```

Notes for packaged builds:

- The build uses PyInstaller in one-folder mode so bundled game scripts can be re-launched through the same executable.
- If Firebase auth is needed on another machine, provide either:
   - `.streamlit/secrets.toml` next to the packaged app folder, or
   - the `FIREBASE_API_KEY` environment variable.
- The packaged app includes the pygame game scripts, Battleship files, Apples database, and `tts.py`.

## Firebase Auth Setup (GameSpace Login)

The GameSpace launcher now requires Firebase email/password auth before any game page is accessible.

1. In Firebase Console, create a project and enable Email/Password in Authentication.
2. Copy your Web API Key from Project Settings.
3. Configure one of the following:

Option A: Streamlit secrets (recommended)

Create `.streamlit/secrets.toml` in the repo root:

```toml
firebase_api_key = "YOUR_FIREBASE_WEB_API_KEY"
```

Option B: Environment variable

```bash
# macOS/Linux
export FIREBASE_API_KEY="YOUR_FIREBASE_WEB_API_KEY"

# PowerShell
$env:FIREBASE_API_KEY="YOUR_FIREBASE_WEB_API_KEY"
```

Then run Streamlit as usual:

```bash
cd testing
streamlit run main.py
```

TTS helper
----------

We added a cross-platform helper `tts.py`. Usage:

```
from tts import speak
speak("Hello")
```

Behavior:
- Windows: attempts SAPI (via `win32com`) when available
- macOS: uses the built-in `say` command
- Otherwise: falls back to `pyttsx3` or prints text