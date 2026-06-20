import streamlit as st
import pandas as pd
import time, os, json, random, base64
import streamlit.components.v1 as components

# ---------- AGENT STACK IMPORTS ----------
from tools.gemini_tool   import GeminiTool
from tools.memory_tool   import MemoryTool
from tools.evaluation_tool import EvaluationTool
from agents.reading_agent   import ReadingAgent
from agents.quiz_agent      import QuizAgent
from agents.simplify_agent  import SimplifyAgent
from agents.progress_agent  import ProgressAgent, ALL_BADGES
from agents.coordinator     import CoordinatorAgent

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title="JoyVerse AI – Dyslexia Learning Assistant",
    page_icon="🌈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────
# CSS LOADER
# ─────────────────────────────────────────
def load_css():
    if os.path.exists("styles.css"):
        with open("styles.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
load_css()

# ─────────────────────────────────────────
# IMAGE HELPERS
# ─────────────────────────────────────────
def img_to_base64(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

QUIZ_IMAGES = {
    "rocket":   "assets/rocket.png",
    "dinosaur": "assets/dinosaur.png",
    "dolphin":  "assets/dolphin.png",
    "book":     "assets/book.png",
}

# ─────────────────────────────────────────
# SESSION STATE BOOTSTRAP
# ─────────────────────────────────────────
defaults = {
    "logged_in": False,
    "student_name": "",
    "avatar": "🧑‍🚀",
    "gemini_key": "",
    "current_lesson": None,
    "current_topic": "",
    "timer_running": False,
    "timer_start": None,
    "reading_wpm": 0,
    "spelling_word": "",
    "spelling_scrambled": [],
    "spelling_guess": [],
    "mistakes_count": 0,
    "bd_completed": {},
    "quiz_score": None,
    "img_quiz_score": 0,
    "img_quiz_round": 0,
    "img_quiz_answered": False,
    "img_quiz_correct": False,
    "img_quiz_choices": [],
    "img_quiz_target": "",
    "img_quiz_done": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────
# AGENT INITIALISATION (cached per session)
# ─────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def build_agents(api_key):
    gemini  = GeminiTool(api_key or None)
    memory  = MemoryTool()
    reading = ReadingAgent(gemini)
    quiz    = QuizAgent(gemini)
    simp    = SimplifyAgent(gemini)
    prog    = ProgressAgent(memory)
    coord   = CoordinatorAgent(reading, quiz, simp, prog)
    return coord, prog, memory, EvaluationTool()

coord, prog_agent, mem_tool, eval_tool = build_agents(st.session_state.gemini_key)

# ─────────────────────────────────────────
# SYLLABLE HELPER (lightweight inline)
# ─────────────────────────────────────────
VOWELS = set("aeiouyAEIOUY")
def simple_syllables(word):
    import re
    clean = re.sub(r'[^a-zA-Z]', '', word)
    if len(clean) <= 3:
        return [word]
    parts, buf = [], ""
    v_count = 0
    for ch in clean:
        buf += ch
        if ch.lower() in VOWELS:
            v_count += 1
            if v_count == 2 and len(buf) > 3:
                parts.append(buf[:-1])
                buf = buf[-1]
                v_count = 1
    if buf:
        parts.append(buf)
    return parts if len(parts) > 1 else [word]

def make_spans(text, syl=False):
    words = text.split()
    out = []
    for i, w in enumerate(words):
        start = text.find(w, sum(len(x)+1 for x in words[:i]))
        end   = start + len(w)
        if syl:
            syls = simple_syllables(w)
            inner = "".join(
                f'<span class="syl-{(j%2)+1}">{s}</span>'
                for j, s in enumerate(syls)
            )
        else:
            inner = w
        out.append(f'<span class="word-span" id="w-{i}" data-start="{start}" data-end="{end}">{inner}</span>')
    return " ".join(out)

# ─────────────────────────────────────────
# TTS READER HTML
# ─────────────────────────────────────────
def reader_html(text, font, size_scale, spacing, tint, syl, ruler):
    spans = make_spans(text, syl)
    tint_class    = {"Warm Cream":"tint-cream","Soft Peach":"tint-peach","Soft Mint":"tint-mint","Sky Blue":"tint-sky","White":"tint-normal","Dark":"tint-dark"}.get(tint,"tint-cream")
    font_class    = {"Lexend":"font-lexend","Comic Neue":"font-comic","Standard":"font-normal-sys"}.get(font,"font-lexend")
    spacing_class = {"Normal":"spacing-normal","Medium":"spacing-medium","Large":"spacing-large"}.get(spacing,"spacing-medium")
    js_text = text.replace('"','\\"').replace('\n',' ')
    css = open("styles.css").read() if os.path.exists("styles.css") else ""
    ruler_html = "<div id='reading-ruler'></div>" if ruler else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
{css}
body{{margin:0;padding:8px;border-radius:12px;}}
#rc{{font-size:{int(18*size_scale)}px;padding:1.2rem;min-height:160px;cursor:crosshair;position:relative;}}
.word-span{{display:inline-block;margin-right:5px;padding:2px 3px;border-radius:4px;transition:background .1s;}}
.tts-bar{{display:flex;align-items:center;gap:10px;background:rgba(255,255,255,0.4);padding:7px 12px;border-radius:10px;border:1px solid rgba(0,0,0,.05);margin-bottom:10px;}}
.tbtn{{background:#6366F1;color:white;border:none;padding:5px 13px;border-radius:7px;font-weight:600;cursor:pointer;font-family:Lexend,sans-serif;font-size:.8rem;transition:all .2s;}}
.tbtn:hover{{background:#4F46E5;transform:translateY(-1px);}}
.tbtn.stop{{background:#EF4444;}}
.speed-sel{{padding:3px 7px;border-radius:5px;border:1px solid #CBD5E1;font-family:Lexend,sans-serif;font-size:.8rem;}}
</style></head>
<body class="{tint_class} {font_class} {spacing_class}">
<div class="tts-bar">
  <button class="tbtn" onclick="startTTS()">🔊 Play</button>
  <button class="tbtn" onclick="pauseTTS()">⏸ Pause</button>
  <button class="tbtn stop" onclick="stopTTS()">⏹ Stop</button>
  <span style="font-size:.8rem;font-family:Lexend,sans-serif;font-weight:500;">Speed:</span>
  <select id="rate" class="speed-sel" onchange="updRate()">
    <option value="0.6">0.6× Slow</option>
    <option value="0.75" selected>0.75× Recommended</option>
    <option value="0.9">0.9×</option>
    <option value="1.0">1.0× Normal</option>
  </select>
</div>
<div id="rc" class="reading-box ruler-active">
  {ruler_html}
  <div id="tc">{spans}</div>
</div>
<script>
let synth=window.speechSynthesis,utt=null,paused=false;
const raw="{js_text}";
const rc=document.getElementById('rc');
const ruler=document.getElementById('reading-ruler');
if({str(ruler).lower()} && ruler){{
  rc.addEventListener('mousemove',e=>{{
    const r=rc.getBoundingClientRect();
    ruler.style.top=(e.clientY-r.top-17)+'px';
    ruler.style.display='block';
  }});
  rc.addEventListener('mouseleave',()=>ruler.style.display='none');
}}
function startTTS(){{
  if(paused){{synth.resume();paused=false;return;}}
  synth.cancel();
  utt=new SpeechSynthesisUtterance(raw);
  utt.rate=parseFloat(document.getElementById('rate').value);
  const sp=document.getElementsByClassName('word-span');
  utt.onboundary=ev=>{{
    if(ev.name==='word'){{
      clearH();
      for(let i=0;i<sp.length;i++){{
        const s=parseInt(sp[i].getAttribute('data-start'));
        const e=parseInt(sp[i].getAttribute('data-end'));
        if(ev.charIndex>=s&&ev.charIndex<e){{sp[i].classList.add('tts-word-highlight');break;}}
      }}
    }}
  }};
  utt.onend=()=>{{clearH();paused=false;}};
  synth.speak(utt);
}}
function pauseTTS(){{if(synth.speaking&&!synth.paused){{synth.pause();paused=true;}}}}
function stopTTS(){{synth.cancel();clearH();paused=false;}}
function updRate(){{if(synth.speaking){{const p=!synth.paused;stopTTS();if(p)startTTS();}}}}
function clearH(){{const sp=document.getElementsByClassName('word-span');for(let i=0;i<sp.length;i++)sp[i].classList.remove('tts-word-highlight');}}
</script></body></html>"""

# ─────────────────────────────────────────
# IMAGE QUIZ HELPERS
# ─────────────────────────────────────────
IMAGE_QUIZ_DATA = [
    {"word":"ROCKET",  "image_key":"rocket",   "sound":"rocket"},
    {"word":"DINOSAUR","image_key":"dinosaur",  "sound":"dinosaur"},
    {"word":"DOLPHIN", "image_key":"dolphin",   "sound":"dolphin"},
    {"word":"BOOK",    "image_key":"book",       "sound":"book"},
]

def new_image_round(round_idx):
    target = IMAGE_QUIZ_DATA[round_idx % len(IMAGE_QUIZ_DATA)]
    choices = list(QUIZ_IMAGES.keys())
    random.shuffle(choices)
    st.session_state.img_quiz_target    = target["image_key"]
    st.session_state.img_quiz_choices   = choices
    st.session_state.img_quiz_answered  = False
    st.session_state.img_quiz_correct   = False
    st.session_state.img_quiz_done      = False

def tts_button_html(word):
    return f"""<button onclick="(new SpeechSynthesisUtterance('{word}') && window.speechSynthesis.speak(new SpeechSynthesisUtterance('{word}')))"
style="background:#6366F1;color:white;border:none;padding:6px 14px;border-radius:8px;
font-size:.9rem;cursor:pointer;font-family:Lexend,sans-serif;font-weight:600;">🔊 Listen</button>"""

# ─────────────────────────────────────────────────────────
#  ███████╗ ██████╗ ██████╗ ███████╗███████╗███╗   ██╗
#  ██╔════╝██╔════╝██╔══██╗██╔════╝██╔════╝████╗  ██║
#  ███████╗██║     ██████╔╝█████╗  █████╗  ██╔██╗ ██║
#  ╚════██║██║     ██╔══██╗██╔══╝  ██╔══╝  ██║╚██╗██║
#  ███████║╚██████╗██║  ██║███████╗███████╗██║ ╚████║
#  ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝
#         ONBOARDING / FIRST LOGIN SCREEN
# ─────────────────────────────────────────────────────────
if not st.session_state.logged_in:
    st.markdown("""
    <div style="text-align:center;padding:40px 0 20px 0;">
      <div style="font-size:4rem;">🌈</div>
      <h1 style="font-family:Lexend,sans-serif;font-size:3rem;margin:0;
                 background:linear-gradient(135deg,#6366F1,#a855f7,#ec4899);
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
        JoyVerse AI
      </h1>
      <p style="font-size:1.2rem;color:#64748B;font-family:Lexend,sans-serif;margin-top:8px;">
        Your Personalized Dyslexia Learning Assistant 🎓
      </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # Name input
    col_l, col_c, col_r = st.columns([1,2,1])
    with col_c:
        st.markdown("<h3 style='font-family:Lexend,sans-serif;text-align:center;'>👋 Who are you?</h3>", unsafe_allow_html=True)

        existing = list(mem_tool.memory.keys())
        mode = st.radio("", ["🔑 Return Student (pick profile)", "🌟 New Student (create profile)"], horizontal=True, label_visibility="collapsed")

        if "Return Student" in mode:
            chosen = st.selectbox("Select your name:", existing)
            name_input = chosen
        else:
            name_input = st.text_input("Enter your name:", placeholder="e.g. Aryan")
            age_input  = st.number_input("Your age:", min_value=5, max_value=18, value=8)
            wpm_input  = st.number_input("Reading goal (WPM):", min_value=20, max_value=200, value=60)

        st.markdown("<h3 style='font-family:Lexend,sans-serif;text-align:center;margin-top:1.5rem;'>🎭 Pick your Hero!</h3>", unsafe_allow_html=True)

        av_cols = st.columns(3)
        avatars = [
            ("🧑‍🚀", "Astro Explorer", "Space & rockets"),
            ("🧑‍🔬", "Marine Biologist", "Dolphins & oceans"),
            ("🤠",   "Dino Ranger",     "Dinosaurs & fossils"),
        ]
        for idx, (icon, role, desc) in enumerate(avatars):
            with av_cols[idx]:
                is_sel = st.session_state.avatar == icon
                border = "3px solid #6366F1" if is_sel else "2px solid #E2E8F0"
                bg     = "#EEF2F6" if is_sel else "white"
                st.markdown(
                    f"<div style='background:{bg};border:{border};border-radius:16px;padding:1.2rem;"
                    f"text-align:center;transition:all .2s;'>"
                    f"<div style='font-size:2.8rem;'>{icon}</div>"
                    f"<div style='font-family:Lexend,sans-serif;font-weight:700;margin:6px 0 2px;'>{role}</div>"
                    f"<div style='font-size:.8rem;color:#64748B;'>{desc}</div>"
                    f"</div>", unsafe_allow_html=True
                )
                if st.button(f"Select {icon}", key=f"av_{idx}", use_container_width=True):
                    st.session_state.avatar = icon
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("🚀 Let's Start Learning!", use_container_width=True, type="primary"):
            name = name_input.strip() if name_input else ""
            if not name:
                st.error("Please enter your name first!")
            else:
                if "New Student" in mode and name not in mem_tool.memory:
                    prog_agent.create_profile(name, int(age_input), int(wpm_input))
                st.session_state.logged_in    = True
                st.session_state.student_name = name
                st.rerun()

    st.stop()

# ─────────────────────────────────────────────────────────
#  MAIN DASHBOARD (after login)
# ─────────────────────────────────────────────────────────
student_name = st.session_state.student_name
profile      = mem_tool.get_profile(student_name) or {}

# ─── SIDEBAR ───
st.sidebar.markdown(
    f"<div style='text-align:center;padding:12px 0;'>"
    f"<div style='font-size:3rem;'>{st.session_state.avatar}</div>"
    f"<h3 style='font-family:Lexend;margin:4px 0 2px;color:#4F46E5;'>Hi, {student_name}! 👋</h3>"
    f"<p style='font-size:.8rem;color:#64748B;margin:0;'>Age {profile.get('age','?')} · "
    f"{len(profile.get('history',[]))} sessions completed</p></div>",
    unsafe_allow_html=True
)

if st.sidebar.button("🚪 Log Out", use_container_width=True):
    for k, v in defaults.items():
        st.session_state[k] = v
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Reading Controls")
font_opts = ["Lexend","Comic Neue","Standard"]
def_font  = font_opts.index(profile.get("preferred_font","Lexend")) if profile.get("preferred_font") in font_opts else 0
font_sel  = st.sidebar.selectbox("Font:", font_opts, index=def_font)
size_sel  = st.sidebar.slider("Text Size:", 1.0, 2.2, float(profile.get("font_size_scale",1.2)), 0.1)
sp_opts   = ["Normal","Medium","Large"]
def_sp    = sp_opts.index(profile.get("spacing_preference","Medium")) if profile.get("spacing_preference") in sp_opts else 1
spacing_sel = st.sidebar.selectbox("Spacing:", sp_opts, index=def_sp)
ruler_sel   = st.sidebar.checkbox("🔦 Reading Ruler", value=True)
tint_opts   = ["Warm Cream","Soft Peach","Soft Mint","Sky Blue","White","Dark"]
def_tint    = tint_opts.index(profile.get("tint_preference","Warm Cream")) if profile.get("tint_preference") in tint_opts else 0
tint_sel    = st.sidebar.selectbox("Background Tint:", tint_opts, index=def_tint)

# Save prefs
if profile:
    profile.update({"preferred_font":font_sel,"font_size_scale":size_sel,
                     "spacing_preference":spacing_sel,"tint_preference":tint_sel})
    mem_tool.set_profile(student_name, profile)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🤖 Gemini API")
api_in = st.sidebar.text_input("API Key (optional):", type="password", value=st.session_state.gemini_key, placeholder="For live AI generation")
if api_in != st.session_state.gemini_key:
    st.session_state.gemini_key = api_in
    st.cache_resource.clear()
    st.rerun()
if st.session_state.gemini_key:
    st.sidebar.success("✅ Live Gemini AI active!")
else:
    st.sidebar.info("🔮 Running in Simulation Mode")

st.sidebar.markdown(
    "<hr><p style='text-align:center;font-size:.72rem;color:#94A3B8;'>"
    "JoyVerse AI · Multi-Agent Dyslexia Assistant<br>"
    "Kaggle AI Course Capstone Project</p>", unsafe_allow_html=True
)

# ─── HEADER BANNER ───
st.markdown(
    f"<div style='background:linear-gradient(135deg,#6366F1 0%,#a855f7 60%,#ec4899 100%);"
    f"padding:22px 28px;border-radius:18px;color:white;margin-bottom:22px;"
    f"box-shadow:0 4px 20px rgba(99,102,241,.25);display:flex;align-items:center;gap:18px;'>"
    f"<div style='font-size:3rem;'>{st.session_state.avatar}</div>"
    f"<div><h1 style='margin:0;font-family:Lexend;font-size:2rem;'>JoyVerse AI</h1>"
    f"<p style='margin:4px 0 0;opacity:.9;font-family:Lexend;'>Personalized Dyslexia Learning · 5-Agent System · Memory + Tools + Evaluation</p></div>"
    f"</div>", unsafe_allow_html=True
)

# ─── TABS ───
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📖 Reading Arena",
    "🎮 Games & Image Quiz",
    "🤖 Agent Control Room",
    "📊 Parent Portal",
    "ℹ️ About Agents",
])

# ══════════════════════════════════════════════════════════
#  TAB 1 · READING ARENA
# ══════════════════════════════════════════════════════════
with tab1:
    st.markdown("### 📚 Prepare a Learning Lesson")
    c1, c2 = st.columns([2,1])
    with c1:
        mode_r = st.radio("Mode:", ["Standard Topics", "Custom Topic"], horizontal=True)
        if mode_r == "Standard Topics":
            topic_sel = st.selectbox("Pick a topic:", ["Space","Dinosaurs","Dolphins"])
        else:
            topic_sel = st.text_input("Enter any topic:", "Rainforest Animals")
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Generate Lesson", use_container_width=True, type="primary"):
            with st.spinner("Multi-Agent workflow running..."):
                lesson = coord.execute_workflow(
                    student_name, topic_sel.lower(),
                    custom_api=bool(st.session_state.gemini_key)
                )
                st.session_state.current_lesson = lesson
                st.session_state.current_topic  = topic_sel.lower()
                # Reset game state
                for k in ["reading_wpm","mistakes_count","quiz_score","img_quiz_score",
                           "img_quiz_round","timer_running","timer_start","spelling_guess","bd_completed"]:
                    st.session_state[k] = defaults[k]
                word_pool = {"space":"ROCKET","dinosaurs":"DINOSAUR","dolphins":"DOLPHIN"}
                w = word_pool.get(topic_sel.lower(), "LEARNING")
                letters = list(w); random.shuffle(letters)
                st.session_state.spelling_word = w
                st.session_state.spelling_scrambled = letters
                new_image_round(0)
            st.success("✅ Lesson ready! Explore the tabs to play games.")

    st.markdown("---")

    if st.session_state.current_lesson:
        lesson = st.session_state.current_lesson
        st.markdown(f"## {lesson['title']}")
        c_t1, c_t2 = st.columns(2)
        with c_t1: simplify = st.toggle("📝 Simplify Text", False)
        with c_t2: syl_mode  = st.toggle("🎨 Highlight Syllables", False)

        active_text = lesson["simplified"] if simplify else lesson["story"]
        components.html(reader_html(active_text, font_sel, size_sel, spacing_sel, tint_sel, syl_mode, ruler_sel), height=340)

        st.markdown("### ⏱️ Fluency Timer")
        cb1, cb2, cstat = st.columns([1,1,2])
        with cb1:
            if st.button("▶️ Start Timer", use_container_width=True, disabled=st.session_state.timer_running):
                st.session_state.timer_start   = time.time()
                st.session_state.timer_running = True
                st.rerun()
        with cb2:
            if st.button("🏁 Done Reading", use_container_width=True, disabled=not st.session_state.timer_running):
                elapsed = time.time() - (st.session_state.timer_start or time.time())
                wpm = eval_tool.calculate_wpm(len(active_text.split()), elapsed)
                st.session_state.reading_wpm   = wpm
                st.session_state.timer_running = False
                st.rerun()
        with cstat:
            if st.session_state.timer_running:
                st.info("⏱️ Timer running — read the story then click Done!")
            elif st.session_state.reading_wpm:
                tgt = profile.get("target_wpm", 60)
                pct = min(100, int(st.session_state.reading_wpm / tgt * 100))
                st.success(f"🎉 **{st.session_state.reading_wpm} WPM** — {pct}% of your {tgt} WPM goal!")
            else:
                st.markdown("<p style='color:#94A3B8;padding-top:10px;'>Press Start, read the story, press Done.</p>", unsafe_allow_html=True)
    else:
        st.info("👆 Choose a topic above and click **Generate Lesson** to begin!")

# ══════════════════════════════════════════════════════════
#  TAB 2 · GAMES & IMAGE QUIZ
# ══════════════════════════════════════════════════════════
with tab2:
    if not st.session_state.current_lesson:
        st.info("📖 Load a lesson in the Reading Arena first!")
    else:
        lesson = st.session_state.current_lesson
        game_tab1, game_tab2, game_tab3, game_tab4 = st.tabs([
            "🖼️ Image Quiz", "📝 Comprehension Quiz", "🔠 Word Builder", "🔡 b vs d Game"
        ])

        # ── IMAGE QUIZ ──
        with game_tab1:
            st.markdown("### 🖼️ Picture Match Quiz")
            st.markdown("Listen to the word, then **click the matching picture!**")

            round_num = st.session_state.img_quiz_round
            total_rounds = len(IMAGE_QUIZ_DATA)

            if round_num < total_rounds and not st.session_state.img_quiz_done:
                target_key   = st.session_state.img_quiz_target
                target_word  = IMAGE_QUIZ_DATA[round_num % len(IMAGE_QUIZ_DATA)]["word"]
                choices      = st.session_state.img_quiz_choices

                # Word display + TTS
                st.markdown(
                    f"<div style='background:linear-gradient(135deg,#6366F1,#a855f7);color:white;"
                    f"padding:16px 28px;border-radius:14px;text-align:center;margin:10px 0;'>"
                    f"<div style='font-family:Lexend;font-size:2rem;font-weight:700;letter-spacing:.15em;'>{target_word}</div>"
                    f"<div style='font-size:.85rem;opacity:.85;margin-top:4px;'>Find the picture that matches this word!</div>"
                    f"</div>", unsafe_allow_html=True
                )
                components.html(f"""<div style="text-align:center;margin:8px 0;">
                <button onclick="window.speechSynthesis.speak(new SpeechSynthesisUtterance('{target_word.lower()}'))"
                style="background:#6366F1;color:white;border:none;padding:8px 22px;border-radius:10px;
                font-size:1rem;cursor:pointer;font-family:Lexend,sans-serif;font-weight:600;">
                🔊 Listen to the Word</button></div>""", height=60)

                # Progress bar
                st.progress(round_num / total_rounds, text=f"Round {round_num+1} of {total_rounds}")

                # Four image cards
                cols = st.columns(4)
                answered = st.session_state.img_quiz_answered

                for idx, key in enumerate(choices):
                    img_path = QUIZ_IMAGES.get(key, "")
                    b64 = img_to_base64(img_path)
                    with cols[idx]:
                        if b64:
                            st.markdown(
                                f"<div style='border:3px solid {'#10B981' if answered and key==target_key else '#E2E8F0'};"
                                f"border-radius:16px;padding:8px;background:{'#ECFDF5' if answered and key==target_key else 'white'};'>"
                                f"<img src='data:image/png;base64,{b64}' style='width:100%;border-radius:10px;'>"
                                f"<p style='text-align:center;font-family:Lexend,sans-serif;font-weight:600;margin:6px 0 0;font-size:.95rem;'>{key.capitalize()}</p>"
                                f"</div>", unsafe_allow_html=True
                            )
                        if not answered:
                            if st.button(f"✅ This is {key.capitalize()}!", key=f"iq_{idx}_{round_num}", use_container_width=True):
                                st.session_state.img_quiz_answered = True
                                if key == target_key:
                                    st.session_state.img_quiz_correct = True
                                    st.session_state.img_quiz_score  += 1
                                else:
                                    st.session_state.img_quiz_correct = False
                                st.rerun()

                if answered:
                    if st.session_state.img_quiz_correct:
                        st.success(f"🎉 Correct! **{target_word}** matches the **{target_key.capitalize()}** picture!")
                        st.balloons()
                    else:
                        st.error(f"❌ Not quite! The word **{target_word}** matches **{target_key.capitalize()}**. Keep going!")

                    nxt_col, skip_col = st.columns(2)
                    with nxt_col:
                        next_round = round_num + 1
                        if next_round >= total_rounds:
                            if st.button("🏆 See Final Score!", use_container_width=True, type="primary"):
                                st.session_state.img_quiz_done  = True
                                st.session_state.img_quiz_round = next_round
                                # Award badge
                                if st.session_state.img_quiz_score >= total_rounds:
                                    p = mem_tool.get_profile(student_name)
                                    if p and "Image Champion" not in p.get("unlocked_badges",[]):
                                        p["unlocked_badges"].append("Image Champion")
                                        mem_tool.set_profile(student_name, p)
                                st.rerun()
                        else:
                            if st.button("➡️ Next Round!", use_container_width=True, type="primary"):
                                st.session_state.img_quiz_round = next_round
                                new_image_round(next_round)
                                st.rerun()
                    with skip_col:
                        if st.button("🔄 Restart Image Quiz", use_container_width=True):
                            st.session_state.img_quiz_score  = 0
                            st.session_state.img_quiz_round  = 0
                            new_image_round(0)
                            st.rerun()
            else:
                # Final score screen
                score = st.session_state.img_quiz_score
                st.markdown(
                    f"<div style='text-align:center;padding:30px;background:linear-gradient(135deg,#6366F1,#a855f7);"
                    f"border-radius:20px;color:white;margin:20px 0;'>"
                    f"<div style='font-size:4rem;'>{'🏆' if score==total_rounds else '⭐'}</div>"
                    f"<h2 style='font-family:Lexend;margin:10px 0;'>Image Quiz Complete!</h2>"
                    f"<p style='font-size:1.5rem;font-family:Lexend;'>You scored <strong>{score} / {total_rounds}</strong></p>"
                    f"{'<p>Perfect Score! You are an Image Champion! 🥇</p>' if score==total_rounds else '<p>Great effort! Practice makes perfect!</p>'}"
                    f"</div>", unsafe_allow_html=True
                )
                if st.button("🔄 Play Again!", use_container_width=True, type="primary"):
                    st.session_state.img_quiz_score  = 0
                    st.session_state.img_quiz_round  = 0
                    st.session_state.img_quiz_done   = False
                    new_image_round(0)
                    st.rerun()

        # ── COMPREHENSION QUIZ ──
        with game_tab2:
            st.markdown("### 📝 Reading Comprehension Quiz")
            quiz = lesson["quiz"]
            user_answers = []
            for i, q in enumerate(quiz):
                st.markdown(f"**Q{i+1}: {q['question']}**")
                ans = st.radio("", q["options"], key=f"cq_{i}", label_visibility="collapsed")
                user_answers.append((q["answer"], ans))
                st.markdown("")

            if st.button("🌟 Submit Quiz!", use_container_width=True, type="primary"):
                correct = sum(1 for t, g in user_answers if t == g)
                score   = int(correct / len(quiz) * 100)
                st.session_state.quiz_score = score
                wpm_val = st.session_state.reading_wpm or 50
                acc_val = eval_tool.calculate_accuracy(len(lesson["story"].split()), st.session_state.mistakes_count)
                new_badges = prog_agent.log_session(student_name, st.session_state.current_topic, wpm_val, acc_val, score)
                errors = {
                    "reversal":     sum(1 for v in st.session_state.bd_completed.values() if v == "wrong"),
                    "substitution": st.session_state.mistakes_count,
                }
                prog_agent.record_errors(student_name, errors)
                if score == 100:
                    st.balloons()
                    st.success("🎉 Perfect 100%! You're a star! 🌟")
                else:
                    st.info(f"You scored **{score}%** — review the story and try again!")
                if new_badges:
                    st.markdown(f"🏆 **New Badges Unlocked:** {', '.join(new_badges)}")

            if st.session_state.quiz_score is not None:
                st.metric("Quiz Score", f"{st.session_state.quiz_score}%")

        # ── WORD BUILDER ──
        with game_tab3:
            st.markdown("### 🔠 Word Builder — Spelling Game")
            st.markdown("Click the scrambled letters **in the correct order** to rebuild the word!")
            word      = st.session_state.spelling_word
            scrambled = st.session_state.spelling_scrambled
            guess     = st.session_state.spelling_guess
            guess_str = "".join(guess)

            st.markdown(
                f"<div style='background:#F8FAFC;border:2px dashed #CBD5E1;border-radius:12px;padding:12px;text-align:center;margin:8px 0;'>"
                f"<span style='font-family:Lexend;font-size:.9rem;color:#64748B;'>Your Answer:</span><br>"
                f"<span style='font-family:Lexend;font-size:2.2rem;font-weight:700;color:#6366F1;letter-spacing:.2em;'>"
                f"{guess_str if guess_str else '_ _ _'}</span></div>",
                unsafe_allow_html=True
            )

            ltr_cols = st.columns(max(len(scrambled), 5))
            for idx, ch in enumerate(scrambled):
                with ltr_cols[idx % len(ltr_cols)]:
                    if st.button(ch, key=f"lb_{idx}_{ch}_{len(guess)}", use_container_width=True):
                        st.session_state.spelling_guess.append(ch)
                        st.rerun()

            cl_col, ch_col = st.columns(2)
            with cl_col:
                if st.button("🧹 Clear", use_container_width=True):
                    st.session_state.spelling_guess = []
                    st.rerun()
            with ch_col:
                if st.button("✅ Check Spelling", use_container_width=True, type="primary"):
                    if guess_str == word:
                        st.success(f"🎉 Correct! You spelled **{word}**!")
                        if "Word Wizard" not in (mem_tool.get_profile(student_name) or {}).get("unlocked_badges",[]):
                            p = mem_tool.get_profile(student_name)
                            if p:
                                p["unlocked_badges"].append("Word Wizard")
                                mem_tool.set_profile(student_name, p)
                    else:
                        st.error("❌ Not quite! Try again!")
                        st.session_state.mistakes_count += 1
                    st.rerun()

        # ── b vs d GAME ──
        with game_tab4:
            st.markdown("### 🔡 Letter Navigator: b vs d")
            st.markdown("Many readers with dyslexia mix up **b** and **d**. Fill in the missing letter!")
            bd_questions = [
                {"id":"q1","sentence":"The dog loves to chase the **_all**.", "correct":"b"},
                {"id":"q2","sentence":"The child was very **sa_** when it rained.", "correct":"d"},
                {"id":"q3","sentence":"Open the **_oor** to let the sun shine in.", "correct":"d"},
                {"id":"q4","sentence":"Look at the **_eautiful** colorful bird.", "correct":"b"},
            ]
            all_done = all(st.session_state.bd_completed.get(q["id"]) == "correct" for q in bd_questions)
            if all_done:
                st.success("🏆 Amazing! You completed all the b vs d challenges perfectly!")
            for q in bd_questions:
                qid    = q["id"]
                status = st.session_state.bd_completed.get(qid, "unanswered")
                st.markdown(q["sentence"])
                c_b, c_d, c_st = st.columns([1,1,2])
                with c_b:
                    if st.button("b", key=f"b_{qid}", disabled=status!="unanswered"):
                        st.session_state.bd_completed[qid] = "correct" if q["correct"]=="b" else "wrong"
                        st.rerun()
                with c_d:
                    if st.button("d", key=f"d_{qid}", disabled=status!="unanswered"):
                        st.session_state.bd_completed[qid] = "correct" if q["correct"]=="d" else "wrong"
                        st.rerun()
                with c_st:
                    if status == "correct":
                        st.markdown("<span style='color:#10B981;font-weight:700;'>✔️ Correct!</span>", unsafe_allow_html=True)
                    elif status == "wrong":
                        st.markdown("<span style='color:#EF4444;font-weight:700;'>❌ Try again!</span>", unsafe_allow_html=True)
                        if st.button("Retry", key=f"retry_{qid}"):
                            st.session_state.bd_completed[qid] = "unanswered"
                            st.rerun()
                    else:
                        st.markdown("<span style='color:#94A3B8;'>Choose b or d ↑</span>", unsafe_allow_html=True)
                st.markdown("")

# ══════════════════════════════════════════════════════════
#  TAB 3 · AGENT CONTROL ROOM
# ══════════════════════════════════════════════════════════
with tab3:
    st.markdown("### 🤖 Multi-Agent Control Room")
    st.markdown("Watch the **5 agents** think, route tasks, call tools, and collaborate in real-time.")

    logs = coord.get_all_logs()
    if not logs:
        st.info("No agent activity yet. Generate a lesson in the Reading Arena to activate the agents!")
    else:
        icon_map = {
            "thought":      ("🤔", "terminal-thought"),
            "tool_call":    ("🛠️", "terminal-tool"),
            "observation":  ("👁️", "terminal-success"),
            "memory_fetch": ("💾", "terminal-memory"),
            "memory_write": ("💾", "terminal-memory"),
            "system":       ("⚙️", "terminal-prompt"),
        }
        html = """<div class="agent-terminal">
        <div class="terminal-header">
          <div><span class="terminal-dot dot-red"></span><span class="terminal-dot dot-yellow"></span>
          <span class="terminal-dot dot-green"></span> joyverse-multi-agent-console</div>
          <div>LIVE LOG</div>
        </div>"""
        for entry in logs:
            ico, cls = icon_map.get(entry["type"], ("·", "terminal-prompt"))
            html += f'<div class="terminal-line"><span style="color:#64748B;">[{entry["timestamp"]}]</span> <span class="{cls}">{ico} {entry["message"]}</span></div>'
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

        if st.button("🧹 Clear Logs"):
            coord.clear_logs()
            st.rerun()

# ══════════════════════════════════════════════════════════
#  TAB 4 · PARENT PORTAL
# ══════════════════════════════════════════════════════════
with tab4:
    st.markdown("### 📊 Parent & Teacher Analytics Portal")
    profile_fresh = mem_tool.get_profile(student_name) or {}
    history       = profile_fresh.get("history", [])

    if not history:
        st.info("No sessions recorded yet. Complete quizzes to populate the analytics!")
    else:
        df = pd.DataFrame(history)
        df["date"] = pd.to_datetime(df["date"])

        m1, m2, m3, m4 = st.columns(4)
        latest = history[-1]
        tgt    = profile_fresh.get("target_wpm", 60)
        m1.metric("Current WPM",  f"{latest['reading_speed_wpm']}",
                  delta=f"{latest['reading_speed_wpm']-tgt} vs goal")
        m2.metric("Accuracy",     f"{latest['accuracy_rate']}%")
        m3.metric("Last Quiz",    f"{latest['quiz_score']}%")
        m4.metric("Sessions",     str(len(history)))

        # Badges
        st.markdown("#### 🏆 Achievement Badges")
        earned = profile_fresh.get("unlocked_badges", [])
        b_cols = st.columns(len(ALL_BADGES))
        for idx, (badge, desc) in enumerate(ALL_BADGES.items()):
            locked = badge not in earned
            with b_cols[idx]:
                icon  = desc.split()[0]
                label = badge
                st.markdown(
                    f"<div class='badge-card {'locked' if locked else ''}'>"
                    f"<div class='badge-icon'>{'🔒' if locked else icon}</div>"
                    f"<div style='font-size:.75rem;font-weight:700;'>{label}</div>"
                    f"</div>", unsafe_allow_html=True
                )

        st.markdown("<br>", unsafe_allow_html=True)
        ch1, ch2 = st.columns(2)
        with ch1:
            fig1 = eval_tool.generate_performance_chart(history)
            if fig1: st.plotly_chart(fig1, use_container_width=True)
        with ch2:
            fig2 = eval_tool.generate_error_category_chart(profile_fresh.get("error_categories", {}))
            if fig2: st.plotly_chart(fig2, use_container_width=True)

        # Recommendations
        st.markdown("### 🩺 Diagnostic Recommendations")
        recs = prog_agent.get_recommendations(student_name)
        if not recs:
            st.success("🟢 All error levels are within healthy thresholds. Keep up the great work!")
        else:
            for r in recs:
                st.markdown(r)

# ══════════════════════════════════════════════════════════
#  TAB 5 · ABOUT THE AGENTS
# ══════════════════════════════════════════════════════════
with tab5:
    st.markdown("### 🧠 How the 5-Agent System Works")
    agents_info = [
        ("🎯", "Coordinator Agent",  "coordinator.py",  "The orchestrator. Routes every user request to the right specialist agent and combines results."),
        ("📖", "Reading Agent",      "reading_agent.py","Generates customized, dyslexia-friendly reading passages using the Gemini API or offline library."),
        ("📝", "Quiz Agent",         "quiz_agent.py",   "Creates comprehension MCQs, image quizzes, and spelling scrambles tailored to the story."),
        ("✂️", "Simplifier Agent",   "simplify_agent.py","Rewrites complex text into shorter, simpler sentences suitable for young dyslexic readers."),
        ("📊", "Progress Agent",     "progress_agent.py","Tracks WPM speeds, quiz scores, error patterns, and manages memory + badge achievements."),
    ]
    for icon, name, fname, desc in agents_info:
        with st.expander(f"{icon} {name} — `agents/{fname}`"):
            st.markdown(f"**Role:** {desc}")

    st.markdown("---")
    st.markdown("### 🛠️ Tools Used")
    tools_info = [
        ("🤖", "GeminiTool",     "tools/gemini_tool.py",     "Connects to Google Gemini API for live story/quiz generation. Falls back to an offline library."),
        ("💾", "MemoryTool",     "tools/memory_tool.py",     "Loads and saves student profiles, history, and badges to `memory/student_memory.json`."),
        ("📈", "EvaluationTool", "tools/evaluation_tool.py", "Computes WPM, accuracy rates, and renders Plotly performance + error-category charts."),
    ]
    tc = st.columns(3)
    for idx, (icon, name, fname, desc) in enumerate(tools_info):
        with tc[idx]:
            st.markdown(
                f"<div style='background:#F8FAFC;border:1px solid #E2E8F0;border-radius:14px;padding:18px;height:100%;'>"
                f"<div style='font-size:2rem;'>{icon}</div>"
                f"<h4 style='font-family:Lexend;margin:8px 0 4px;'>{name}</h4>"
                f"<code style='font-size:.78rem;background:#EEF2F6;padding:2px 6px;border-radius:4px;'>{fname}</code>"
                f"<p style='font-size:.85rem;color:#64748B;margin-top:8px;'>{desc}</p>"
                f"</div>", unsafe_allow_html=True
            )

    st.markdown("---")
    st.markdown("""
    ### ✅ AI Concepts Demonstrated

    | Concept | Implementation |
    |---|---|
    | **Memory** | Student profiles persisted in `memory/student_memory.json` across sessions |
    | **Tool Calling** | Agents invoke `GeminiTool`, `MemoryTool`, `EvaluationTool` to complete tasks |
    | **Personalization** | Font, size, spacing, tint, topic all tuned per student profile |
    | **Evaluation** | WPM timer, quiz scoring, error categorisation, badge tracking |
    | **Multi-Agent** | 5 independent agents orchestrated by a Coordinator with log tracing |
    """)
