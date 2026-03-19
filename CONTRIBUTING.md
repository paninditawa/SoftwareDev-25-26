# Step-by-step Setup Instructions for Developers (like us)

# General Steps

1. Use "git clone" + <YOUR_REPO_URL> to clone and open the repo.
2. Create and activate a virtual environment.
3. Install required dependencies in requirements.txt
4. Launch the HelloWorld gamespace.

# Actual commands for different operating systems

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

# Before Committing

1. Run the app and make sure your change ACTUALLY works.
2. DO NOT commit secrets.
3. Keep changes small and focused.

# Accessibility Requirements

Follow Microsoft accessibility guidance when you change UI code. 
This section is derived from https://learn.microsoft.com/en-us/windows/apps/design/accessibility/accessibility-overview

1. Every interactive control must be reachable and usable from the keyboard.
2. Do not remove or weaken focus borders.
3. Do not use color alone to show state. Add text, symbols, or spoken feedback.
4. Keep visible text at readable sizes.
5. Do not introduce hard-coded low-contrast overrides.
6. Test the launcher with keyboard-only navigation before you commit.

# Secrets (DO NOT SHARE)

- `supabase_project.py` contains the shared anon key — this is intentionally committed and safe to share.
- Never add or commit any Supabase service role key.
- `config.py` and `games/config.py` are gitignored for local overrides.

