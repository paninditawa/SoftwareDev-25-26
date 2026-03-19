# HelloWorld GameSpace

Accessible collection of mini-games with a desktop-first launcher, account sign-in, and spoken announcements.

New contributors can follow the short setup guide in `CONTRIBUTING.md`.

Keyboard controls: Up/Down arrows (or Shift+Tab/Tab) to navigate, Left/Right arrows to switch between menus and actions, F1 for help, F2 to repeat the last message, F7 for current context, and Enter or Space to activate.

## Quick Start (Windows PowerShell)

Run these from repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python launch_gamespace.py
```

Sign-in is ready to use out of the box. Just clone, install, and run.

## Run The Launcher

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

### 5) Run the desktop app

```bash
python launch_gamespace.py
```

## Features

- Keyboard-first navigation.
- Spoken focus/context announcements.
- Account sign-in, sign-up, and sign-out.
- Launch support for Hangman, Maze, Mad Libs, Escape Room, Connect 4, Apples to Apples, and Battleship.

## Accessibility Notes

- The launcher + games use high-contrast text and larger default type so labels stay readable on classroom projectors and smaller laptops.
- Important states should not rely only on color. Several games now add text or symbol markers like YOU, EXIT, 1 or 2, and X or O.
- The project is still keyboard-first. If a screen becomes hard to read, the spoken announcements remain the backup way to confirm focus and state.
- The current visual baseline follows Microsoft guidance for keyboard access, visible focus, non-color-only state, and readable text contrast.

## Troubleshooting Quick Notes

- If sign-in fails, make sure you have an internet connection and try again.
- If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

- If pygame fails on macOS, install SDL packages:

```bash
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf pkg-config
```

## Voice Input Setup (Hangman, Mad Libs, Escape Room)

Voice input is cross-platform (Windows, macOS, Linux), but each machine must have:

- SpeechRecognition installed.
- PyAudio installed.
- Microphone permissions enabled for desktop apps.
- A working default input device selected before launching the game.

Install voice dependencies:

```bash
python -m pip install -r requirements.txt
```

If your environment is older and missing voice deps, install directly:

```bash
python -m pip install SpeechRecognition PyAudio
```

If PyAudio fails to build on macOS/Linux, install PortAudio first:

```bash
# macOS (Homebrew)
brew install portaudio

# Ubuntu/Debian
sudo apt-get install portaudio19-dev python3-pyaudio
```

Quick microphone check:

```bash
python -c "import speech_recognition as sr; print(len(sr.Microphone.list_microphone_names()))"
```

Expected result: a number greater than 0.

## Common Voice Issues

- "Voice input unavailable": Usually missing SpeechRecognition/PyAudio, blocked microphone permission, or no default mic selected.
- Spoken letters not recognized well in Hangman: Speak a single letter clearly (for example "B" or "bee"). NATO words like "bravo" and "charlie" are also supported.
- Works on one computer but not another: confirm both are using the same virtual environment and both ran pip install -r requirements.txt.

## Recommended Python Version

Python 3.11 or 3.12 is recommended for easiest cross-platform wheel support, especially for PyAudio.


