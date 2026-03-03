# Apples to Apples Game (w/ text to speech)
import sqlite3
import time
import secrets
import json
import random
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import os

data = os.path.join(os.path.dirname(__file__), "apples_min.db")
hand_size = 10
refresh_rate = 700

# Making the decks of cards: green = prompts, red = answers
green_base = [
    "The worst thing to say on a first date:",
    "The most awkward family tradition:",
    "My secret superpower is...",
    "What keeps me up at night?",
    "A terrible name for a restaurant:",
    "The fastest way to ruin a party:",
    "A thing you should never bring to a wedding:",
    "A surprising reason to call 911:",
    "A weird thing to collect:",
    "A phrase that should never be on a t-shirt:",
]

adj = [
    "haunted","tiny","gigantic","mysterious","unreasonably confident","overly dramatic","cursed","sparkly",
    "noisy","invisible","self-aware","gluten-free","sad","legendary","suspicious","extremely polite",
    "ancient","futuristic","sticky","chaotic","friendly","aggressively helpful","melancholy","radioactive"
]

noun = [
    "microwave","toaster","pigeon","raccoon","spoon","calculator","group chat","sock","email thread",
    "rubber duck","elevator","vacuum","meme","cactus","hamster","printer","Wi-Fi router","doorbell",
    "traffic cone","treadmill","calendar invite","laptop","spaghetti","stapler","thermostat"
]

verb = [
    "that only works when you cry",
    "that judges you silently",
    "that demands compliments",
    "that whispers spoilers",
    "that starts a union",
    "that writes apology emails",
    "that insists it's your manager",
    "that resets your personality",
]

def build_red_deck() -> list[str]:
    # combining adj, noun, and verb to make more cards
    deck = []
    for a in adj:
        for n in noun:
            deck.append(f"A {a} {n}.")
    for a in adj:
        for n in noun:
            for v in verb:
                deck.append(f"A {a} {n} {v}.")
    # some pre-set cards
    deck += [
        "Existing.",
        "Centaurs.",
        "Passive-aggressive notes.",
        "A perfectly timed Wi-Fi outage.",
        "Saying “per my last email” out loud.",
        "Wearing socks in the shower.",
        "An inspirational tattoo misspelling.",
        "Glitter spaghetti.",
        "A tiny violin playing just for you.",
    ]
    return deck

def build_green_deck() -> list[str]:
    # combining templates of cards
    prompts = []
    for base in green_base:
        prompts.append(base)
        prompts.append(base + " (be honest)")
        prompts.append(base + " (say it like a robot)")
        prompts.append(base + " (in one word)")
    return prompts

green = build_green_deck()
red = build_red_deck()

def conn():
    c = sqlite3.connect(data, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    return c


def init():
    c = conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS games(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT UNIQUE,
          phase TEXT,
          round_num INTEGER,
          judge_pid INTEGER,
          green TEXT,
          rev INTEGER DEFAULT 0,
          points_to_win INTEGER DEFAULT 5,
          last_msg TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS players(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          game_id INTEGER,
          name TEXT,
          token TEXT,
          score INTEGER DEFAULT 0,
          UNIQUE(game_id, name),
          UNIQUE(game_id, token)
        );
        CREATE TABLE IF NOT EXISTS hands(
          game_id INTEGER,
          pid INTEGER,
          cards TEXT,
          PRIMARY KEY(game_id, pid)
        );
        CREATE TABLE IF NOT EXISTS subs(
          game_id INTEGER,
          round_num INTEGER,
          pid INTEGER,
          card TEXT,
          PRIMARY KEY(game_id, round_num, pid)
        );
        """
    )
    c.commit()
    c.close()


def bump(c, gid, msg=""):
    c.execute("UPDATE games SET rev = rev + 1, last_msg=? WHERE id=?", (msg, gid))


def game_by_code(code):
    c = conn()
    g = c.execute("SELECT * FROM games WHERE code=?", (code,)).fetchone()
    c.close()
    return dict(g) if g else None


def players(gid):
    c = conn()
    rows = c.execute("SELECT * FROM players WHERE game_id=? ORDER BY id", (gid,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def my_player(gid, token):
    if not token:
        return None
    c = conn()
    r = c.execute("SELECT * FROM players WHERE game_id=? AND token=?", (gid, token)).fetchone()
    c.close()
    return dict(r) if r else None


def get_hand(gid, pid):
    c = conn()
    r = c.execute("SELECT cards FROM hands WHERE game_id=? AND pid=?", (gid, pid)).fetchone()
    c.close()
    return json.loads(r["cards"]) if r and r["cards"] else []


def set_hand(c, gid, pid, cards):
    c.execute(
        "INSERT OR REPLACE INTO hands(game_id, pid, cards) VALUES (?,?,?)",
        (gid, pid, json.dumps(cards, ensure_ascii=False)),
    )


def draw_cards(deck, n):
    out = []
    for _ in range(n):
        if not deck:
            break
        out.append(deck.pop())
    return out


def ensure_decks(ss):
    ss.setdefault("green_deck", random.sample(green, k=len(green)))
    ss.setdefault("red_deck", random.sample(red, k=len(red)))


def create_game(points_to_win=5):
    c = conn()
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    c.execute(
        "INSERT INTO games(code, phase, round_num, judge_pid, green, points_to_win) VALUES (?,?,?,?,?,?)",
        (code, "lobby", 1, None, "", int(points_to_win)),
    )
    gid = c.execute("SELECT id FROM games WHERE code=?", (code,)).fetchone()["id"]
    c.commit()
    c.close()
    return code


def join_game(code, name):
    g = game_by_code(code)
    if not g:
        raise ValueError("Invalid game code.")
    if g["phase"] != "lobby":
        raise ValueError("Game already started.")
    token = secrets.token_urlsafe(12)
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    c.execute("INSERT INTO players(game_id, name, token) VALUES (?,?,?)", (g["id"], name, token))
    pid = c.execute("SELECT id FROM players WHERE game_id=? AND token=?", (g["id"], token)).fetchone()["id"]
    set_hand(c, g["id"], pid, [])
    bump(c, g["id"], f"{name} joined.")
    c.commit()
    c.close()
    return token


def start_game(gid):
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    ps = c.execute("SELECT id,name FROM players WHERE game_id=? ORDER BY id", (gid,)).fetchall()
    if len(ps) < 2:
        c.rollback()
        c.close()
        raise ValueError("Need at least 2 players.")

    judge = int(ps[0]["id"])
    green = random.choice(green)

    # Big shuffled deck, deal WITHOUT replacement so every player gets 10
    deck = red[:]
    random.shuffle(deck)

    need_total = len(ps) * hand_size
    if len(deck) < need_total:
        # Extremely unlikely now, but keep it safe:
        # If somehow not enough, allow repeats.
        deck = random.choices(red, k=need_total)

    for p in ps:
        hand = draw_cards(deck, hand_size)  # pops from deck
        set_hand(c, gid, int(p["id"]), hand)

    c.execute(
        "UPDATE games SET phase='selecting', judge_pid=?, green=?, round_num=1 WHERE id=?",
        (judge, green, gid),
    )
    bump(c, gid, "Game started. Selecting phase.")
    c.commit()
    c.close()

def submit_card(gid, round_num, pid, judge_pid, card):
    if pid == judge_pid:
        raise ValueError("Judge cannot submit.")
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    # phase check
    g = c.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
    if g["phase"] != "selecting":
        c.rollback(); c.close()
        raise ValueError("Not selecting.")
    # ensure card in hand
    hand = json.loads(c.execute("SELECT cards FROM hands WHERE game_id=? AND pid=?", (gid, pid)).fetchone()["cards"])
    if card not in hand:
        c.rollback(); c.close()
        raise ValueError("Card not in hand.")
    c.execute("INSERT INTO subs(game_id, round_num, pid, card) VALUES (?,?,?,?)", (gid, round_num, pid, card))
    hand.remove(card)
    set_hand(c, gid, pid, hand)
    bump(c, gid, "Card submitted.")
    # if all non-judges submitted -> judging
    total = c.execute("SELECT COUNT(*) n FROM players WHERE game_id=?", (gid,)).fetchone()["n"]
    subs = c.execute("SELECT COUNT(*) n FROM subs WHERE game_id=? AND round_num=?", (gid, round_num)).fetchone()["n"]
    # judge doesn't submit
    if subs >= total - 1:
        c.execute("UPDATE games SET phase='judging' WHERE id=?", (gid,))
        bump(c, gid, "All submissions received. Judging phase.")
    c.commit()
    c.close()


def judge_pick(gid, round_num, judge_pid, winning_card):
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    g = c.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
    if g["phase"] != "judging":
        c.rollback(); c.close()
        raise ValueError("Not judging.")
    if int(g["judge_pid"]) != int(judge_pid):
        c.rollback(); c.close()
        raise ValueError("Only judge can pick.")

    row = c.execute(
        "SELECT pid FROM subs WHERE game_id=? AND round_num=? AND card=?",
        (gid, round_num, winning_card),
    ).fetchone()
    if not row:
        c.rollback(); c.close()
        raise ValueError("Invalid winner.")
    winner_pid = int(row["pid"])
    c.execute("UPDATE players SET score=score+1 WHERE game_id=? AND id=?", (gid, winner_pid))

    # check win
    pts = int(g["points_to_win"])
    w = c.execute("SELECT name,score FROM players WHERE game_id=? AND id=?", (gid, winner_pid)).fetchone()
    if int(w["score"]) >= pts:
        c.execute("UPDATE games SET phase='game_over' WHERE id=?", (gid,))
        bump(c, gid, f"{w['name']} wins! Game over.")
        c.commit(); c.close()
        return

    # rotate judge
    pids = [int(r["id"]) for r in c.execute("SELECT id FROM players WHERE game_id=? ORDER BY id", (gid,)).fetchall()]
    i = pids.index(int(judge_pid))
    next_judge = pids[(i + 1) % len(pids)]

    # give new prompt + deal back to 10 cards
    green = random.choice(green)
    for pid in pids:
        hand = json.loads(c.execute("SELECT cards FROM hands WHERE game_id=? AND pid=?", (gid, pid)).fetchone()["cards"])
        need = max(0, hand_size - len(hand))
        tmp = red[:]
        random.shuffle(tmp)
        hand.extend(draw_cards(tmp, need))
        set_hand(c, gid, pid, hand)

    c.execute(
        "UPDATE games SET phase='selecting', round_num=round_num+1, judge_pid=?, green=? WHERE id=?",
        (next_judge, green, gid),
    )
    bump(c, gid, f"Round winner: {w['name']}. New round selecting.")
    c.commit()
    c.close()


def inject_keyboard_tts():
    st.components.v1.html(
        """
<script>
(function(){
  if (window.__kbtts_installed) return;
  window.__kbtts_installed = true;

  function speak(text){
    try{
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      window.speechSynthesis.speak(u);
    }catch(e){}
  }

  function isInSidebar(el){
    try{
      return !!(el && el.closest && el.closest('[data-testid="stSidebar"]'));
    }catch(e){ return false; }
  }

  function labelFor(el){
    try{
      const id = el.getAttribute('id');
      if (id){
        const lab = parent.document.querySelector(`label[for="${id}"]`);
        if (lab && lab.innerText) return lab.innerText.trim();
      }
      const wrap = el.closest('div');
      if (wrap){
        const lab2 = wrap.querySelector('label');
        if (lab2 && lab2.innerText) return lab2.innerText.trim();
      }
    }catch(e){}
    return "";
  }

  function sidebarInputs(){
    const sb = parent.document.querySelector('[data-testid="stSidebar"]');
    if (!sb) return [];
    const els = Array.from(sb.querySelectorAll('input, textarea'));
    return els.filter(e => e.offsetParent !== null);
  }

  function mainButtons(){
    // stAppViewContainer includes sidebar too; exclude sidebar subtree
    const app = parent.document.querySelector('[data-testid="stAppViewContainer"]') || parent.document.body;
    const sb = parent.document.querySelector('[data-testid="stSidebar"]');
    const btns = Array.from(app.querySelectorAll('button')).filter(b => b.offsetParent !== null);
    if (!sb) return btns;
    return btns.filter(b => !sb.contains(b));
  }

  let idx = 0;
  let mode = "main"; // "sidebar" or "main"

  function currentList(){
    return (mode === "sidebar") ? sidebarInputs() : mainButtons();
  }

  function setModeFromActive(){
    const ae = parent.document.activeElement;
    mode = isInSidebar(ae) ? "sidebar" : "main";
  }

  function speakFocused(el){
    if (!el) return;
    if (el.tagName === "BUTTON"){
      const t = (el.innerText || el.ariaLabel || "button").trim();
      if (t) speak(t);
    } else if (el.tagName === "INPUT" || el.tagName === "TEXTAREA"){
      const t = (labelFor(el) || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "input").trim();
      if (t) speak(t);
    }
  }

  function focusAt(i){
    setModeFromActive();
    const els = currentList();
    if (!els.length) return;
    idx = (i + els.length) % els.length;
    els[idx].focus();
    speakFocused(els[idx]);
  }

  parent.document.addEventListener('keydown', function(e){
    const k = e.key;
    if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter'].includes(k)) return;

    setModeFromActive();
    const els = currentList();
    if (!els.length) return;

    // In sidebar mode: DO NOT hijack Enter (lets user type + prevents sidebar collapsing behavior)
    if (mode === "sidebar" && k === "Enter") return;

    e.preventDefault(); e.stopPropagation();

    if (k === 'ArrowRight' || k === 'ArrowDown') focusAt(idx + 1);
    if (k === 'ArrowLeft'  || k === 'ArrowUp')   focusAt(idx - 1);

    // In main mode: Enter clicks the focused button
    if (mode === "main" && k === 'Enter'){
      const el = els[idx];
      if (el && el.tagName === 'BUTTON') el.click();
    }
  }, true);

  parent.document.addEventListener('focusin', function(e){
    setModeFromActive();
    // reset index so arrows start from current focus in the active list
    const els = currentList();
    const t = e.target;
    const j = els.indexOf(t);
    if (j >= 0) idx = j;
    speakFocused(t);
  }, true);

})();
</script>
        """,
        height=0,
    )

# ---------------- UI ----------------
init()
st.set_page_config(page_title="Apples-to-Apples", layout="wide", initial_sidebar_state="expanded")

st_autorefresh(interval=refresh_rate, key="refresh")
inject_keyboard_tts()

ss = st.session_state
ss.setdefault("code", "")
ss.setdefault("token", "")
ss.setdefault("name", "")
ss.setdefault("selected", None)

st.title("Apples-to-Apples")

with st.sidebar:
    st.header("Create / Join")
    if st.button("Create game"):
        ss["code"] = create_game(points_to_win=5)
        ss["token"] = ""
        ss["name"] = ""
        ss["selected"] = None

    ss["code"] = st.text_input("Game code", ss["code"]).strip().upper()
    ss["name"] = st.text_input("Your name", ss["name"]).strip()

    if st.button("Join", disabled=not (ss["code"] and ss["name"])):
        try:
            ss["token"] = join_game(ss["code"], ss["name"])
        except Exception as e:
            st.error(str(e))

g = game_by_code(ss["code"]) if ss["code"] else None
if not g:
    st.info("Create a game or enter a code to join.")
    st.stop()

gid = int(g["id"])
ps = players(gid)
me = my_player(gid, ss["token"]) if ss["token"] else None
judge_name = next((p["name"] for p in ps if g["judge_pid"] and int(p["id"]) == int(g["judge_pid"])), "—")

# Status summary (always visible)
st.markdown(
    f"""
**Status**
- Code: `{g['code']}`
- Phase: **{g['phase']}**
- Round: **{g['round_num']}**
- Judge: **{judge_name}**
- Prompt: **{g['green'] or '(none)'}**
- Last update: {g['last_msg']}
"""
)

# Scoreboard
st.subheader("Players")
for p in ps:
    tag = " (Judge)" if g["judge_pid"] and int(p["id"]) == int(g["judge_pid"]) else ""
    you = " (You)" if me and int(p["id"]) == int(me["id"]) else ""
    st.write(f"- {p['name']}{tag}{you}: {p['score']}")

# Start game
if g["phase"] == "lobby":
    if st.button("Start Game", type="primary", disabled=len(ps) < 2):
        try:
            start_game(gid)
        except Exception as e:
            st.error(str(e))
    st.stop()

if not me:
    st.warning("Join to play")
    st.stop()

is_judge = bool(g["judge_pid"]) and int(me["id"]) == int(g["judge_pid"])
round_num = int(g["round_num"])

# Selecting
if g["phase"] == "selecting":
    if is_judge:
        st.info("You are the judge. Wait for submissions.")
    else:
        st.subheader("Your hand (10)")
        hand = get_hand(gid, int(me["id"]))
        if not hand:
            st.info("No cards.")
        else:
            # show as simple buttons (arrow keys can focus these without Tab)
            cols = st.columns(5)
            for i, card in enumerate(hand[:hand_size]):
                with cols[i % 5]:
                    if st.button(f"Card {i+1}: {card}", key=f"c-{i}-{card}"):
                        ss["selected"] = card

        st.subheader("Selected")
        st.write(ss["selected"] or "(none)")

        if st.button("Confirm & Submit", type="primary", disabled=not ss["selected"]):
            try:
                submit_card(gid, round_num, int(me["id"]), int(g["judge_pid"]), ss["selected"])
                ss["selected"] = None
            except Exception as e:
                st.error(str(e))

# Judging
elif g["phase"] == "judging":
    if not is_judge:
        st.info("Waiting for judge to pick a winner.")
    else:
        st.subheader("Anonymous submissions")
        c = conn()
        subs = c.execute("SELECT card FROM subs WHERE game_id=? AND round_num=?", (gid, round_num)).fetchall()
        c.close()
        cards = [r["card"] for r in subs]
        random.shuffle(cards)
        if not cards:
            st.info("No submissions yet.")
        else:
            choice = st.radio("Pick winning card", cards, index=0)
            if st.button("Confirm Winner", type="primary"):
                try:
                    judge_pick(gid, round_num, int(me["id"]), choice)
                except Exception as e:
                    st.error(str(e))

elif g["phase"] == "game_over":
    st.success("Game over!")