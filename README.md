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