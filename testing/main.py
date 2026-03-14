# import Streamlit for UI
import streamlit as st
import streamlit.components.v1 as components

# import os and requests for Firebase REST auth calls
import os
import requests
import tomllib

# import system utilities for subprocesses
import sys
import subprocess

# import Path for file path handling
from pathlib import Path

# import individual game modules
import maze_app
import madlibs_app
import home_page
import c4_app
import hangman

# Ensure root-level modules (like tts.py) are importable when running from testing/.
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from tts import speak as _tts_speak
    from tts import speak_interrupt as _tts_speak_interrupt
except Exception:
    def _tts_speak(text: str):
        print(text)

    def _tts_speak_interrupt(text: str):
        print(text)


PAGE_OPTIONS = [
    ("Home", "home_page"),
    ("Hangman", "hangman"),
    ("Maze Game", "maze_app"),
    ("Mad Libs", "madlibs_app"),
    ("Connect 4", "c4"),
    ("Apples to Apples", "apples"),
    ("Battleship", "battleship"),
]

PAGE_LABEL_TO_KEY = {label: key for label, key in PAGE_OPTIONS}
PAGE_KEY_TO_LABEL = {key: label for label, key in PAGE_OPTIONS}


def _is_usable_api_key(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    placeholders = {
        "REPLACE_WITH_FIREBASE_WEB_API_KEY",
        "YOUR_FIREBASE_WEB_API_KEY",
        "YOUR_API_KEY",
    }
    if normalized in placeholders:
        return False
    if normalized.startswith("<") and normalized.endswith(">"):
        return False
    return True


def _announce(text: str, interrupt: bool = True, force: bool = False) -> None:
    """Speak and log an announcement for built-in accessibility narration."""
    if not st.session_state.get("voice_enabled", True):
        return

    if not force and st.session_state.get("last_spoken_text") == text:
        return

    st.session_state["last_spoken_text"] = text
    log = st.session_state.get("speech_log", [])
    log.append(text)
    st.session_state["speech_log"] = log[-8:]

    try:
        if interrupt:
            _tts_speak_interrupt(text)
        else:
            _tts_speak(text)
    except Exception:
        pass


def _announce_once(event_key: str, text: str, interrupt: bool = True) -> None:
    if st.session_state.get("last_announce_event") == event_key:
        return
    st.session_state["last_announce_event"] = event_key
    _announce(text, interrupt=interrupt)


def _reset_auth_state() -> None:
    st.session_state.auth = {
        "is_authenticated": False,
        "email": "",
        "id_token": "",
        "refresh_token": "",
        "local_id": "",
    }


def _current_page_context() -> str:
    page_key = st.session_state.get("page", "home_page")
    page_label = PAGE_KEY_TO_LABEL.get(page_key, "Home")
    if page_key == "battleship":
        return (
            f"You are on {page_label}. Start server, then launch client. "
            "Use Tab to move through controls."
        )
    return f"You are on {page_label}. Use navigation controls to switch pages or launch game actions."


def _announce_login_mode_change() -> None:
    mode = st.session_state.get("auth_mode", "Sign In")
    _announce(f"Login action selected: {mode}.", interrupt=True, force=True)


def _announce_nav_selection_change() -> None:
    label = st.session_state.get("nav_selected_label", "Home")
    _announce(f"Navigation selected: {label}. Activate Open selected page to go there.", interrupt=True, force=True)


def _render_focus_announcer(enabled: bool) -> None:
        """Browser-side focus speech for Tab navigation labels."""
        enabled_js = "true" if enabled else "false"
        components.html(
                f"""
                <script>
                    (function() {{
                        const enabled = {enabled_js};
                        if (window.__hwFocusAnnouncerInstalled) {{
                            window.__hwFocusAnnouncerEnabled = enabled;
                            return;
                        }}

                        window.__hwFocusAnnouncerInstalled = true;
                        window.__hwFocusAnnouncerEnabled = enabled;
                        window.__hwLastFocusText = "";
                        window.__hwLastFocusTime = 0;

                        function cleanText(s) {{
                              return (s || "").replace(/\\s+/g, " ").trim();
                        }}

                        function labelFor(el) {{
                            if (!el) return "";
                            const ariaLabel = cleanText(el.getAttribute("aria-label"));
                            if (ariaLabel) return ariaLabel;

                            const ariaLabelledBy = el.getAttribute("aria-labelledby");
                            if (ariaLabelledBy) {{
                                const node = document.getElementById(ariaLabelledBy);
                                const txt = cleanText(node && node.textContent);
                                if (txt) return txt;
                            }}

                            const placeholder = cleanText(el.getAttribute("placeholder"));
                            if (placeholder) return placeholder;

                            const title = cleanText(el.getAttribute("title"));
                            if (title) return title;

                            const id = el.getAttribute("id");
                            if (id) {{
                                const label = document.querySelector('label[for="' + CSS.escape(id) + '"]');
                                const txt = cleanText(label && label.textContent);
                                if (txt) return txt;
                            }}

                            const text = cleanText(el.textContent);
                            if (text) return text;

                            const name = cleanText(el.getAttribute("name"));
                            if (name) return name;

                            return cleanText(el.tagName || "control").toLowerCase();
                        }}

                        function typeFor(el) {{
                            if (!el) return "";
                            const role = el.getAttribute("role");
                            if (role) return role;
                            const tag = (el.tagName || "").toLowerCase();
                            if (tag === "input") {{
                                return (el.getAttribute("type") || "input").toLowerCase();
                            }}
                            return tag;
                        }}

                        function speak(text) {{
                            if (!window.__hwFocusAnnouncerEnabled || !text) return;
                            if (!("speechSynthesis" in window)) return;

                            const now = Date.now();
                            if (window.__hwLastFocusText === text && now - window.__hwLastFocusTime < 500) return;
                            window.__hwLastFocusText = text;
                            window.__hwLastFocusTime = now;

                            try {{
                                window.speechSynthesis.cancel();
                                const u = new SpeechSynthesisUtterance(text);
                                u.rate = 1.0;
                                u.pitch = 1.0;
                                window.speechSynthesis.speak(u);
                            }} catch (e) {{}}
                        }}

                        document.addEventListener("focusin", function(evt) {{
                            if (!window.__hwFocusAnnouncerEnabled) return;
                            const el = evt.target;
                            const label = labelFor(el);
                            const kind = typeFor(el);
                            const msg = kind ? `${{label}}, ${{kind}}` : label;
                            speak(msg);
                        }}, true);
                    }})();
                </script>
                """,
                height=0,
        )


def _render_accessibility_sidebar(is_authenticated: bool) -> None:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Audio Accessibility")
    st.sidebar.checkbox("Enable voice announcements", key="voice_enabled")
    st.sidebar.checkbox("Enable Tab focus voice", key="focus_voice_enabled")
    st.sidebar.caption("Tab focus voice uses browser speech to read focused controls.")

    if st.sidebar.button("Repeat last message"):
        last = st.session_state.get("last_spoken_text")
        if last:
            _announce(last, interrupt=True, force=True)

    if st.sidebar.button("Where am I?"):
        _announce(_current_page_context(), interrupt=True, force=True)

    if st.sidebar.button("Help"):
        if is_authenticated:
            _announce(
                "Keyboard tips. Use Tab and Shift Tab to move focus. Enter or Space to activate. "
                "Use Next page and Previous page in navigation, then Open selected page.",
                interrupt=True,
                force=True,
            )
        else:
            _announce(
                "Login screen. Tab to Email, Password, and Sign In or Create Account. "
                "After signing in, use sidebar navigation.",
                interrupt=True,
                force=True,
            )

    log = st.session_state.get("speech_log", [])
    if log:
        st.sidebar.caption("Recent announcements")
        for line in log[-3:]:
            st.sidebar.write(f"- {line}")


def _get_firebase_api_key() -> str | None:
    """Resolve Firebase API key from Streamlit secrets or environment."""
    try:
        if "firebase_api_key" in st.secrets:
            key = st.secrets["firebase_api_key"]
            if _is_usable_api_key(key):
                return key.strip()
    except Exception:
        pass

    env_key = os.environ.get("FIREBASE_API_KEY")
    if _is_usable_api_key(env_key):
        return env_key.strip()

    # Fallback for local runs where Streamlit may be started from `testing/`.
    candidate_files = [
        Path(__file__).resolve().parent / ".streamlit" / "secrets.toml",
        Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml",
    ]
    for secret_file in candidate_files:
        try:
            if secret_file.exists():
                data = tomllib.loads(secret_file.read_text(encoding="utf-8"))
                key = data.get("firebase_api_key")
                if _is_usable_api_key(key):
                    return key.strip()
        except Exception:
            continue

    return None


def _firebase_auth_request(endpoint: str, payload: dict) -> tuple[bool, dict]:
    api_key = _get_firebase_api_key()
    if not api_key:
        return False, {"error": {"message": "MISSING_FIREBASE_API_KEY"}}

    url = f"https://identitytoolkit.googleapis.com/v1/{endpoint}?key={api_key}"
    try:
        response = requests.post(url, json=payload, timeout=12)
        data = response.json()
    except Exception as exc:
        return False, {"error": {"message": f"NETWORK_ERROR: {exc}"}}

    return response.ok, data


def _map_firebase_error(error_message: str) -> str:
    known = {
        "EMAIL_EXISTS": "That email is already registered.",
        "EMAIL_NOT_FOUND": "No account found for that email.",
        "INVALID_PASSWORD": "Incorrect password.",
        "USER_DISABLED": "This account has been disabled.",
        "INVALID_EMAIL": "Please enter a valid email address.",
        "CREDENTIAL_TOO_OLD_LOGIN_AGAIN": "Please sign in again before deleting your account.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Try again later.",
        "MISSING_FIREBASE_API_KEY": "Firebase API key is missing. Add it in Streamlit secrets.",
    }
    return known.get(error_message, f"Auth failed: {error_message}")


def _create_account(email: str, password: str) -> tuple[bool, str, dict]:
    ok, data = _firebase_auth_request(
        "accounts:signUp",
        {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        },
    )
    if ok:
        return True, "Account created successfully.", data
    message = data.get("error", {}).get("message", "UNKNOWN_ERROR")
    return False, _map_firebase_error(message), {}


def _sign_in(email: str, password: str) -> tuple[bool, str, dict]:
    ok, data = _firebase_auth_request(
        "accounts:signInWithPassword",
        {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        },
    )
    if ok:
        return True, "Signed in successfully.", data
    message = data.get("error", {}).get("message", "UNKNOWN_ERROR")
    return False, _map_firebase_error(message), {}


def _delete_account(id_token: str) -> tuple[bool, str]:
    ok, data = _firebase_auth_request("accounts:delete", {"idToken": id_token})
    if ok:
        return True, "Your account has been deleted."
    message = data.get("error", {}).get("message", "UNKNOWN_ERROR")
    return False, _map_firebase_error(message)

# Display main title of game space
st.title("HelloWorld - An Accessible Game Space")

# Initialize auth state
if "auth" not in st.session_state:
    _reset_auth_state()

# Initialize navigation state
if "page" not in st.session_state:
    st.session_state.page = "home_page"

if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = True

if "focus_voice_enabled" not in st.session_state:
    st.session_state.focus_voice_enabled = True

if "speech_log" not in st.session_state:
    st.session_state.speech_log = []

if "last_spoken_text" not in st.session_state:
    st.session_state.last_spoken_text = ""

if "last_announce_event" not in st.session_state:
    st.session_state.last_announce_event = ""

if "nav_index" not in st.session_state:
    st.session_state.nav_index = 0

if "nav_selected_label" not in st.session_state:
    st.session_state.nav_selected_label = PAGE_KEY_TO_LABEL.get(st.session_state.page, "Home")

# Auth gate for the whole GameSpace
auth = st.session_state.auth
api_key_present = bool(_get_firebase_api_key())

if not api_key_present:
    st.error("Firebase is not configured yet.")
    st.info(
        "Add firebase_api_key to Streamlit secrets or set FIREBASE_API_KEY in your environment, then refresh."
    )
    _render_accessibility_sidebar(is_authenticated=False)
    _announce_once(
        "firebase-missing",
        "Firebase is not configured. Add a Firebase API key in Streamlit secrets and refresh.",
        interrupt=True,
    )
    _render_focus_announcer(enabled=st.session_state.focus_voice_enabled)
    st.stop()

if not auth["is_authenticated"]:
    st.subheader("Sign In to Continue")
    st.caption("Use your Firebase Authentication email/password account.")

    _announce_once(
        "login-screen",
        "Login screen. Enter email and password, then activate Sign In or Create Account.",
        interrupt=True,
    )

    mode = st.radio(
        "Choose action",
        ["Sign In", "Create Account"],
        horizontal=True,
        key="auth_mode",
        on_change=_announce_login_mode_change,
    )
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Read login controls"):
        _announce(
            "Login controls: Choose action, Email field, Password field, then activate the selected action button.",
            interrupt=True,
            force=True,
        )

    if st.button(mode):
        if not email or not password:
            st.error("Email and password are required.")
        elif len(password) < 6:
            st.error("Password must be at least 6 characters.")
        else:
            if mode == "Create Account":
                ok, message, data = _create_account(email, password)
            else:
                ok, message, data = _sign_in(email, password)

            if ok:
                st.session_state.auth = {
                    "is_authenticated": True,
                    "email": data.get("email", email),
                    "id_token": data.get("idToken", ""),
                    "refresh_token": data.get("refreshToken", ""),
                    "local_id": data.get("localId", ""),
                }
                st.success(message)
                _announce("Signed in successfully. Welcome to HelloWorld GameSpace.", interrupt=True, force=True)
                st.rerun()
            else:
                st.error(message)
                _announce(message, interrupt=True, force=True)

    _render_accessibility_sidebar(is_authenticated=False)
    _render_focus_announcer(enabled=st.session_state.focus_voice_enabled)
    st.stop()

st.sidebar.success(f"Signed in as {auth['email']}")
if st.sidebar.button("Sign Out"):
    _reset_auth_state()
    _announce("Signed out.", interrupt=True, force=True)
    st.rerun()

st.sidebar.title("Navigation")
st.sidebar.caption("Tip: Streamlit does not expose button focus events on Tab, so use selector changes and Open selected page for spoken navigation.")

if st.sidebar.button("Previous page"):
    st.session_state.nav_index = (st.session_state.nav_index - 1) % len(PAGE_OPTIONS)
    selected_label = PAGE_OPTIONS[st.session_state.nav_index][0]
    _announce(f"Selected {selected_label}.", interrupt=True, force=True)

if st.sidebar.button("Next page"):
    st.session_state.nav_index = (st.session_state.nav_index + 1) % len(PAGE_OPTIONS)
    selected_label = PAGE_OPTIONS[st.session_state.nav_index][0]
    _announce(f"Selected {selected_label}.", interrupt=True, force=True)

selected_label = st.sidebar.selectbox(
    "Page selector",
    [label for label, _ in PAGE_OPTIONS],
    key="nav_selected_label",
    on_change=_announce_nav_selection_change,
)
st.session_state.nav_index = [label for label, _ in PAGE_OPTIONS].index(selected_label)

if st.sidebar.button("Open selected page"):
    st.session_state.page = PAGE_LABEL_TO_KEY[selected_label]
    _announce(f"Opening {selected_label}.", interrupt=True, force=True)
    st.rerun()

_render_accessibility_sidebar(is_authenticated=True)
_render_focus_announcer(enabled=st.session_state.focus_voice_enabled)

with st.sidebar.expander("Danger Zone", expanded=False):
    st.warning("Delete Account permanently removes your Firebase login.")
    confirm_delete = st.checkbox("I understand this cannot be undone")
    if st.button("Delete Account", type="primary"):
        if not confirm_delete:
            st.error("Please confirm before deleting your account.")
        elif not auth.get("id_token"):
            st.error("Missing auth token. Sign in again and retry.")
        else:
            deleted, message = _delete_account(auth["id_token"])
            if deleted:
                _reset_auth_state()
                st.success(message)
                _announce(message, interrupt=False, force=True)
                st.rerun()
            else:
                st.error(message)
                _announce(message, interrupt=True, force=True)

page_label = PAGE_KEY_TO_LABEL.get(st.session_state.page, "Home")
_announce_once(
    f"page-{st.session_state.page}",
    f"{page_label} page. {_current_page_context()}",
    interrupt=True,
)

# load correct page based on session state and show content
if st.session_state.page == "home_page":
    home_page.show_home()

elif st.session_state.page == "maze_app":
    maze_app.show_maze()

elif st.session_state.page == "madlibs_app":
    madlibs_app.show_madlibs()

elif st.session_state.page == "c4":
    c4_app.show_c4()

elif st.session_state.page == "apples":
    st.write("### Apples to Apples")
    st.write("Use the sidebar fields and arrow keys to play. (Streamlit handles focus.)")
    apples_path = Path(__file__).resolve().parents[0] / "apples" / "apples_app.py"
    try:
        import runpy
        runpy.run_path(str(apples_path), run_name="__main__")
    except Exception as e:
        st.error(f"Failed to launch Apples to Apples: {e}")

elif st.session_state.page == "battleship":
    st.write("### Battleship")
    st.write("Start the local server, then launch the client. Use keyboard arrow keys and Enter.")
    _announce_once(
        "battleship-help",
        "Battleship launcher. Start server first, then launch client.",
        interrupt=True,
    )

    battleship_dir = Path(__file__).resolve().parents[0] / "Battleship"
    server_path = battleship_dir / "server.py"
    client_path = battleship_dir / "client.py"

    def _find_free_port() -> int:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    server_proc = st.session_state.get("battleship_server")
    server_port = st.session_state.get("battleship_port")
    if server_proc and server_proc.poll() is None:
        st.success(f"Server is running on port {server_port}")
        if st.button("Stop server"):
            server_proc.terminate()
            st.session_state["battleship_server"] = None
            st.session_state["battleship_port"] = None
            _announce("Battleship server stopped.", interrupt=True, force=True)
    else:
        if st.button("Start server"):
            port = _find_free_port()
            st.session_state["battleship_port"] = port
            st.session_state["battleship_server"] = subprocess.Popen(
                [sys.executable, str(server_path), "--port", str(port)]
            )
            _announce(f"Battleship server started on port {port}.", interrupt=True, force=True)

    if st.button("Launch client"):
        if server_proc and server_proc.poll() is None and server_port:
            subprocess.Popen(
                [sys.executable, str(client_path), "--port", str(server_port)]
            )
            _announce("Launching Battleship client.", interrupt=True, force=True)
        else:
            st.error("Start the Battleship server first before launching the client.")
            _announce(
                "Cannot launch client. Start the Battleship server first.",
                interrupt=True,
                force=True,
            )

elif st.session_state.page == "hangman":
    hangman.show_hangman()
