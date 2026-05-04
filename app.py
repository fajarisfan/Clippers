import streamlit as st
import os, glob, uuid, re, random, subprocess
from collections import Counter
from datetime import datetime
import pytz

import numpy as np
import yt_dlp
from faster_whisper import WhisperModel
from moviepy import (
    VideoFileClip, TextClip, ImageClip,
    CompositeVideoClip, AudioFileClip, CompositeAudioClip,
)
import moviepy.video.fx as vfx
import moviepy.audio.fx as afx

os.environ["PATH"] += os.pathsep + os.getcwd()

TMP_DIR      = "/tmp/hpc_tmp"
OUTPUT_DIR   = "/tmp/hpc_output"
WM_DIR       = "/tmp/hpc_wm"
BGM_PATH     = "/tmp/hpc_bgm.mp3"
COOKIES_FILE = "/tmp/hpc_cookies.txt"

for _d in [TMP_DIR, OUTPUT_DIR, WM_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── Auto-restore cookies dari Streamlit Secrets ──────────────────
def _restore_cookies_from_secrets():
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        return
    try:
        raw = st.secrets["cookies"]["content"]
        if not raw:
            return
        cleaned = raw.strip()
        if len(cleaned) < 50 or "youtube.com" not in cleaned:
            return
        with open(COOKIES_FILE, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(cleaned)
    except Exception:
        pass

_restore_cookies_from_secrets()

# ── Font Detection ────────────────────────────────────────────────
_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "C:/Windows/Fonts/seguibl.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]
FONT_PATH = next((f for f in _FONTS if os.path.exists(f)), None)
if not FONT_PATH:
    for _sd in ["C:/Windows/Fonts", "/usr/share/fonts"]:
        _ttf = glob.glob(f"{_sd}/**/*.ttf", recursive=True)
        if _ttf:
            FONT_PATH = _ttf[0]
            break

# ── FYP Windows ──────────────────────────────────────────────────
FYP_WINDOWS = [
    {"label": "🌅 Pagi Aktif",     "range": (6,  9),  "desc": "Orang buka HP setelah bangun tidur"},
    {"label": "☕ Istirahat Siang", "range": (11, 13), "desc": "Jam makan siang, scrolling santai"},
    {"label": "🌆 Sore Nongkrong", "range": (15, 17), "desc": "Pulang kerja/sekolah, engagement tinggi"},
    {"label": "🌙 Prime Time",     "range": (19, 22), "desc": "⭐ JAM EMAS — traffic tertinggi TikTok/Reels"},
    {"label": "🦉 Late Night",     "range": (22, 24), "desc": "Niche audience, engagement loyal"},
]

def get_fyp_status() -> dict:
    wib    = pytz.timezone("Asia/Jakarta")
    now    = datetime.now(wib)
    hour   = now.hour
    minute = now.minute
    current_window = next_window = None
    minutes_to_next = None
    for w in FYP_WINDOWS:
        s, e = w["range"]
        if s <= hour < e:
            current_window = w
            break
    for w in FYP_WINDOWS:
        s, e = w["range"]
        start_min = s * 60
        now_min   = hour * 60 + minute
        if start_min > now_min:
            next_window     = w
            minutes_to_next = start_min - now_min
            break
    if next_window is None and FYP_WINDOWS:
        nw = FYP_WINDOWS[0]
        minutes_to_next = (24 * 60) - (hour * 60 + minute) + nw["range"][0] * 60
        next_window = nw
    return {
        "now": now, "hour": hour,
        "current_window": current_window,
        "next_window": next_window,
        "minutes_to_next": minutes_to_next,
    }

# ── Emotion Lexicon ───────────────────────────────────────────────
EMOTION_LEXICON: dict = {
    "ngakak": ("komedi", 5), "wkwkwk": ("komedi", 5), "hahaha": ("komedi", 4),
    "ketawa": ("komedi", 4), "lucu": ("komedi", 4), "gokil": ("komedi", 4),
    "receh": ("komedi", 3), "kocak": ("komedi", 4), "bercanda": ("komedi", 3),
    "lelucon": ("komedi", 3), "humor": ("komedi", 3), "lawak": ("komedi", 3),
    "absurd": ("komedi", 3), "geli": ("komedi", 3), "ngikik": ("komedi", 4),
    "ngenes": ("komedi", 3), "lebay": ("komedi", 3), "alay": ("komedi", 2),
    "jayus": ("komedi", 3), "awkward": ("komedi", 3), "parah": ("komedi", 3),
    "gilaa": ("komedi", 4), "gila": ("komedi", 3), "anjir": ("komedi", 4),
    "anjay": ("komedi", 4), "astaga": ("komedi", 3),
    "hantu": ("horror", 5), "setan": ("horror", 5), "pocong": ("horror", 5),
    "kuntilanak": ("horror", 5), "gendruwo": ("horror", 5), "tuyul": ("horror", 4),
    "arwah": ("horror", 5), "roh": ("horror", 4), "mistis": ("horror", 4),
    "kesurupan": ("horror", 5), "santet": ("horror", 5), "teluh": ("horror", 5),
    "pelet": ("horror", 4), "dukun": ("horror", 4), "pesugihan": ("horror", 5),
    "serem": ("horror", 4), "ngeri": ("horror", 4), "merinding": ("horror", 5),
    "takut": ("horror", 3), "ketakutan": ("horror", 4), "horor": ("horror", 4),
    "gelap": ("horror", 2), "malam": ("horror", 2), "kuburan": ("horror", 4),
    "mayat": ("horror", 4), "mati": ("horror", 3), "kematian": ("horror", 4),
    "terkutuk": ("horror", 5), "ritual": ("horror", 4), "gaib": ("horror", 4),
    "supranatural": ("horror", 4), "paranormal": ("horror", 4),
    "makhluk": ("horror", 3), "penampakan": ("horror", 5), "gangguan": ("horror", 3),
    "kaget": ("kaget", 5), "syok": ("kaget", 5), "terkejut": ("kaget", 4),
    "shock": ("kaget", 5), "ternyata": ("kaget", 4), "tiba-tiba": ("kaget", 4),
    "mendadak": ("kaget", 4), "nggak nyangka": ("kaget", 5), "gak nyangka": ("kaget", 5),
    "lho": ("kaget", 3), "wah": ("kaget", 3), "eh": ("kaget", 2),
    "kok bisa": ("kaget", 4), "masa": ("kaget", 3), "beneran": ("kaget", 3),
    "serius": ("kaget", 3), "bukan main": ("kaget", 4), "gila banget": ("kaget", 5),
    "parah banget": ("kaget", 5), "nggak percaya": ("kaget", 5), "gak percaya": ("kaget", 5),
    "mustahil": ("kaget", 4), "wtf": ("kaget", 5), "plot twist": ("kaget", 5),
    "twist": ("kaget", 4),
    "nangis": ("haru", 5), "terharu": ("haru", 5), "haru": ("haru", 4),
    "menyentuh": ("haru", 4), "touching": ("haru", 4), "sedih": ("haru", 4),
    "baper": ("haru", 3), "mewek": ("haru", 4), "pilu": ("haru", 4),
    "nelangsa": ("haru", 4), "rindu": ("haru", 3), "kehilangan": ("haru", 4),
    "air mata": ("haru", 4), "menangis": ("haru", 5), "tersentuh": ("haru", 4),
    "emosional": ("haru", 4), "perasaan": ("haru", 3), "hati": ("haru", 2),
    "semangat": ("motivasi", 4), "inspirasi": ("motivasi", 5), "motivasi": ("motivasi", 5),
    "bangkit": ("motivasi", 4), "juara": ("motivasi", 4), "sukses": ("motivasi", 4),
    "berhasil": ("motivasi", 4), "berjuang": ("motivasi", 4), "pantang menyerah": ("motivasi", 5),
    "tekad": ("motivasi", 4), "optimis": ("motivasi", 4), "percaya diri": ("motivasi", 4),
    "luar biasa": ("motivasi", 4), "keren": ("motivasi", 3), "hebat": ("motivasi", 3),
    "mantap": ("motivasi", 3), "gas": ("motivasi", 4), "gaskeun": ("motivasi", 4),
}

def analyze_emotion(text: str) -> tuple[str, int]:
    text_lower = text.lower()
    scores: Counter = Counter()
    for keyword, (emotion, weight) in EMOTION_LEXICON.items():
        if keyword in text_lower:
            scores[emotion] += weight
    if not scores:
        return "netral", 0
    dominant = scores.most_common(1)[0]
    return dominant[0], dominant[1]


# ════════════════════════════════════════════════════════════════
#  CUSTOM CSS — Dark industrial theme
# ════════════════════════════════════════════════════════════════

def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif !important;
    }
    .stApp {
        background: #0a0a0f !important;
        color: #e2e2e8 !important;
    }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container {
        padding: 2rem 2.5rem 4rem !important;
        max-width: 920px !important;
    }

    /* Header */
    .hpc-header {
        font-family: 'Space Mono', monospace;
        font-size: 1.65rem;
        font-weight: 700;
        color: #fff;
        letter-spacing: -0.5px;
        padding: 1.25rem 0 0.2rem;
        border-bottom: 1px solid #1a1a28;
        margin-bottom: 1.4rem;
    }
    .hpc-header span { color: #7c6af7; }

    /* FYP Banner */
    .fyp-banner {
        background: #0d0d1a;
        border: 1px solid #1e1e30;
        border-left: 3px solid #7c6af7;
        border-radius: 8px;
        padding: 0.7rem 1.1rem;
        margin-bottom: 1.5rem;
        font-size: 0.83rem;
        color: #9090b8;
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }
    .fyp-live {
        background: #7c6af7;
        color: #fff;
        font-family: 'Space Mono', monospace;
        font-size: 0.62rem;
        padding: 2px 8px;
        border-radius: 3px;
        font-weight: 700;
        letter-spacing: 1.5px;
    }
    .fyp-next { color: #50508a; font-size: 0.77rem; }

    /* Section labels */
    .sec-label {
        font-family: 'Space Mono', monospace;
        font-size: 0.65rem;
        letter-spacing: 2.5px;
        text-transform: uppercase;
        color: #40407a;
        margin: 1.6rem 0 0.5rem;
    }

    /* Cards */
    .hpc-card {
        background: #0e0e1c;
        border: 1px solid #1c1c2e;
        border-radius: 10px;
        padding: 1.1rem 1.4rem 1.3rem;
        margin-bottom: 0.75rem;
    }
    .hpc-card-title {
        font-family: 'Space Mono', monospace;
        font-size: 0.65rem;
        color: #40407a;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 0.85rem;
    }

    /* Cookies badge */
    .ck-badge {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 4px 13px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 500;
        margin-bottom: 0.85rem;
    }
    .ck-badge.ok  { background:#0b2318; border:1px solid #175c33; color:#3ddc84; }
    .ck-badge.no  { background:#251808; border:1px solid #5c3a10; color:#dc983d; }
    .ck-dot { width:6px; height:6px; border-radius:50%; }
    .ck-dot.ok { background:#3ddc84; }
    .ck-dot.no { background:#dc983d; }

    /* Metrics row */
    .mrow {
        display: grid;
        grid-template-columns: repeat(3,1fr);
        gap: 9px;
        margin: 0.85rem 0;
    }
    .mcrd {
        background: #09091a;
        border: 1px solid #1c1c2e;
        border-radius: 8px;
        padding: 0.75rem 0.9rem;
        text-align: center;
    }
    .mcrd .mv {
        font-family: 'Space Mono', monospace;
        font-size: 1.05rem;
        font-weight: 700;
        color: #d8d8f8;
    }
    .mcrd .ml {
        font-size: 0.68rem;
        color: #404070;
        margin-top: 3px;
        letter-spacing: 0.5px;
    }

    /* Secrets preview block */
    .sec-block {
        background: #060610;
        border: 1px solid #1a1a2c;
        border-radius: 8px;
        padding: 0.9rem 1.1rem;
        font-family: 'Space Mono', monospace;
        font-size: 0.7rem;
        color: #7070b0;
        white-space: pre-wrap;
        word-break: break-all;
        max-height: 200px;
        overflow-y: auto;
        line-height: 1.75;
        margin: 0.6rem 0 0.9rem;
    }
    .sec-block .k { color: #7c6af7; }
    .sec-block .v { color: #3ddc84; }
    .sec-block .c { color: #30305a; }

    /* Alert boxes */
    .box-info {
        background: #0b0b1e; border: 1px solid #20204060;
        border-left: 3px solid #7c6af7; border-radius: 6px;
        padding: 0.65rem 1rem; font-size: 0.8rem; color: #7878c0;
        margin: 0.6rem 0; line-height: 1.6;
    }
    .box-warn {
        background: #1a120a; border: 1px solid #40300a60;
        border-left: 3px solid #dc983d; border-radius: 6px;
        padding: 0.65rem 1rem; font-size: 0.8rem; color: #b08050;
        margin: 0.6rem 0;
    }
    .box-ok {
        background: #091810; border: 1px solid #0a3a1560;
        border-left: 3px solid #3ddc84; border-radius: 6px;
        padding: 0.65rem 1rem; font-size: 0.8rem; color: #50a870;
        margin: 0.6rem 0;
    }
    .box-err {
        background: #180909; border: 1px solid #3a0a0a60;
        border-left: 3px solid #dc3d3d; border-radius: 6px;
        padding: 0.65rem 1rem; font-size: 0.8rem; color: #a85050;
        margin: 0.6rem 0;
    }

    /* Widget overrides */
    .stTextInput > div > div > input {
        background: #0e0e1c !important;
        border: 1px solid #252538 !important;
        border-radius: 8px !important;
        color: #e2e2f8 !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 0.9rem !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #7c6af7 !important;
        box-shadow: 0 0 0 2px #7c6af718 !important;
    }
    .stButton > button {
        background: #7c6af7 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.875rem !important;
        padding: 0.55rem 1.5rem !important;
        transition: all 0.15s !important;
        letter-spacing: 0.2px !important;
    }
    .stButton > button:hover {
        background: #9580ff !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 24px #7c6af738 !important;
    }
    .stButton > button:active { transform: translateY(0) !important; }
    .stDownloadButton > button {
        background: #0b2318 !important;
        color: #3ddc84 !important;
        border: 1px solid #175c33 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stDownloadButton > button:hover {
        background: #102e1e !important;
        box-shadow: 0 4px 16px #3ddc8422 !important;
    }
    .stCheckbox > label span, .stRadio > label span {
        color: #9090b8 !important;
        font-size: 0.875rem !important;
    }
    div[data-baseweb="select"] > div {
        background: #0e0e1c !important;
        border: 1px solid #252538 !important;
        border-radius: 8px !important;
        color: #e2e2f8 !important;
    }
    .stSlider [data-baseweb="slider"] div[role="slider"] {
        background: #7c6af7 !important;
    }
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #7c6af7, #a590ff) !important;
    }
    [data-testid="stSidebar"] {
        background: #06060f !important;
        border-right: 1px solid #141424 !important;
    }
    [data-testid="stSidebar"] label span {
        color: #70709a !important;
        font-size: 0.85rem !important;
    }
    [data-testid="stFileUploadDropzone"] {
        background: #0b0b18 !important;
        border: 1.5px dashed #252540 !important;
        border-radius: 10px !important;
    }
    [data-testid="stFileUploadDropzone"]:hover {
        border-color: #7c6af7 !important;
        background: #0e0e20 !important;
    }
    .streamlit-expanderHeader {
        background: #0e0e1c !important;
        color: #70709a !important;
        border: 1px solid #1c1c2e !important;
        border-radius: 8px !important;
        font-size: 0.82rem !important;
    }
    /* Hide default alerts — using custom boxes */
    div[data-testid="stAlert"] { display: none !important; }

    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: #0a0a0f; }
    ::-webkit-scrollbar-thumb { background: #252540; border-radius: 2px; }
    ::-webkit-scrollbar-thumb:hover { background: #404080; }
    </style>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
#  COOKIES UPLOADER
# ════════════════════════════════════════════════════════════════

def render_cookies_uploader():
    cookies_ok = os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100

    # Status badge
    if cookies_ok:
        size_kb = os.path.getsize(COOKIES_FILE) // 1024
        st.markdown(
            f'<div class="ck-badge ok"><div class="ck-dot ok"></div>'
            f'Cookies aktif &mdash; {size_kb} KB</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="ck-badge no"><div class="ck-dot no"></div>'
            'Cookies belum ada</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="sec-label">Upload cookies.txt</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="box-info">Export dari browser pakai ekstensi '
        '<b>Get cookies.txt LOCALLY</b> → pilih youtube.com → save sebagai .txt</div>',
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        label="cookies",
        type=["txt"],
        key="cookies_uploader",
        label_visibility="collapsed",
    )

    if uploaded is not None:
        try:
            raw_content = uploaded.read().decode("utf-8", errors="ignore")
        except Exception as e:
            st.markdown(f'<div class="box-err">❌ Gagal baca file: {e}</div>', unsafe_allow_html=True)
            return

        lines       = [l for l in raw_content.splitlines() if l.strip()]
        total_lines = len(lines)
        is_netscape = any("# Netscape" in l or "# HTTP Cookie File" in l for l in lines[:5])
        has_youtube = "youtube.com" in raw_content or "google.com" in raw_content
        is_valid    = is_netscape or has_youtube

        # Metric row
        st.markdown(
            f'''<div class="mrow">
              <div class="mcrd"><div class="mv">{total_lines}</div><div class="ml">Total Baris</div></div>
              <div class="mcrd"><div class="mv">{"✓" if is_netscape else "?"}</div><div class="ml">Netscape fmt</div></div>
              <div class="mcrd"><div class="mv">{"✓" if has_youtube else "✗"}</div><div class="ml">Domain YT</div></div>
            </div>''',
            unsafe_allow_html=True,
        )

        if not is_valid:
            st.markdown(
                '<div class="box-err">❌ File bukan cookies valid. '
                'Pastikan export dari youtube.com format Netscape HTTP Cookie.</div>',
                unsafe_allow_html=True,
            )
            return

        st.markdown(
            f'<div class="box-ok">✓ File valid &mdash; {total_lines} baris ditemukan</div>',
            unsafe_allow_html=True,
        )

        # ── Format Streamlit Secrets ──────────────────────────
        st.markdown('<div class="sec-label">Format Streamlit Secrets</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="box-info">'
            'Copy teks di bawah (tombol kanan atas blok kode) → '
            'Streamlit Cloud → App Settings → Secrets → Paste → Save → Reboot app.'
            '</div>',
            unsafe_allow_html=True,
        )

        secrets_text = f'[cookies]\ncontent = """\n{raw_content.strip()}\n"""'

        # st.code: tombol copy built-in di pojok kanan atas
        st.code(secrets_text, language="toml")

        # Syntax-highlighted preview (dekoratif)
        preview_lines = raw_content.strip().splitlines()
        shown         = preview_lines[:8]
        remaining     = max(0, len(preview_lines) - 8)
        rows_html = ""
        for l in shown:
            if l.startswith("#"):
                rows_html += f'<span class="c">{l}</span>\n'
            else:
                parts = l.split("\t")
                if len(parts) >= 2:
                    rows_html += (
                        f'<span class="k">{parts[0]}</span>\t'
                        + "\t".join(f'<span class="v">{p}</span>' for p in parts[1:])
                        + "\n"
                    )
                else:
                    rows_html += f'<span class="v">{l[:90]}{"…" if len(l)>90 else ""}</span>\n'
        if remaining:
            rows_html += f'<span class="c">… +{remaining} baris lainnya</span>'

        st.markdown(
            f'<div class="sec-block">'
            f'<span class="k">[cookies]</span>\n'
            f'<span class="k">content</span> = <span class="v">"""</span>\n'
            f'{rows_html}'
            f'<span class="v">"""</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Aktifkan sesi ini ─────────────────────────────────
        st.markdown('<div class="sec-label">Aktifkan Sekarang</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="box-warn">⚠ Tidak permanen &mdash; hilang saat app restart. '
            'Tetap paste ke Secrets untuk permanen.</div>',
            unsafe_allow_html=True,
        )

        if st.button("💾  Simpan & Aktifkan Sekarang", key="btn_activate_cookies"):
            try:
                with open(COOKIES_FILE, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(raw_content.strip())
                st.markdown(
                    f'<div class="box-ok">✓ Tersimpan di <code>{COOKIES_FILE}</code> '
                    f'({os.path.getsize(COOKIES_FILE)//1024} KB). Siap dipakai!</div>',
                    unsafe_allow_html=True,
                )
                st.rerun()
            except Exception as e:
                st.markdown(f'<div class="box-err">❌ Gagal simpan: {e}</div>', unsafe_allow_html=True)

    # ── Hapus cookies ─────────────────────────────────────────
    if cookies_ok:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑  Hapus Cookies Aktif", key="btn_delete_cookies"):
            try:
                os.remove(COOKIES_FILE)
                st.markdown('<div class="box-ok">✓ Cookies dihapus.</div>', unsafe_allow_html=True)
                st.rerun()
            except Exception as e:
                st.markdown(f'<div class="box-err">❌ Gagal hapus: {e}</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
#  DOWNLOAD HELPER
# ════════════════════════════════════════════════════════════════

def _ydl_opts(output_path: str, format_str: str = "bestvideo+bestaudio/best") -> dict:
    opts = {
        "format": format_str,
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        opts["cookiefile"] = COOKIES_FILE
    return opts

def download_video(url: str, out_dir: str = TMP_DIR) -> str | None:
    uid  = uuid.uuid4().hex[:8]
    path = os.path.join(out_dir, f"{uid}.%(ext)s")
    try:
        with yt_dlp.YoutubeDL(_ydl_opts(path)) as ydl:
            info = ydl.extract_info(url, download=True)
            ext  = info.get("ext", "mp4")
            return os.path.join(out_dir, f"{uid}.{ext}")
    except Exception as e:
        st.markdown(f'<div class="box-err">❌ Download gagal: {e}</div>', unsafe_allow_html=True)
        return None


# ════════════════════════════════════════════════════════════════
#  WHISPER
# ════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="Memuat model Whisper…")
def load_whisper(model_size: str = "base") -> WhisperModel:
    return WhisperModel(model_size, device="cpu", compute_type="int8")

def transcribe_video(video_path: str, model_size: str = "base") -> list[dict]:
    model = load_whisper(model_size)
    segments, _ = model.transcribe(video_path, beam_size=5, language="id")
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]


# ════════════════════════════════════════════════════════════════
#  VIDEO EDITING HELPERS
# ════════════════════════════════════════════════════════════════

def add_subtitles(clip, segments, font_path=FONT_PATH, fontsize=40,
                  color="white", stroke_color="black", stroke_width=2):
    txt_clips = []
    for seg in segments:
        if not seg["text"]:
            continue
        txt = (
            TextClip(
                text=seg["text"], font=font_path, font_size=fontsize,
                color=color, stroke_color=stroke_color, stroke_width=stroke_width,
                method="caption", size=(int(clip.w * 0.9), None),
            )
            .with_start(seg["start"]).with_end(seg["end"])
            .with_position(("center", 0.85), relative=True)
        )
        txt_clips.append(txt)
    return CompositeVideoClip([clip, *txt_clips])

def add_watermark(clip, wm_path, position=("right", "top"), opacity=0.7, scale=0.15):
    wm = (
        ImageClip(wm_path).with_opacity(opacity)
        .resized(width=int(clip.w * scale))
        .with_position(position).with_duration(clip.duration)
    )
    return CompositeVideoClip([clip, wm])

def add_bgm(clip, bgm_path, bgm_volume=0.15, fade_duration=2.0):
    bgm = AudioFileClip(bgm_path).with_effects([
        afx.AudioLoop(duration=clip.duration),
        afx.MultiplyVolume(bgm_volume),
        afx.AudioFadeOut(fade_duration),
    ])
    final_audio = CompositeAudioClip([clip.audio, bgm]) if clip.audio else bgm
    return clip.with_audio(final_audio)

def export_clip(clip, output_path, fps=30, preset="fast", threads=4):
    clip.write_videofile(
        output_path, fps=fps, codec="libx264", audio_codec="aac",
        preset=preset, threads=threads, logger=None,
    )
    return output_path


# ════════════════════════════════════════════════════════════════
#  MAIN UI
# ════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="HPC Video Tools",
        page_icon="🎬",
        layout="wide",
    )
    inject_css()

    # ── Header ───────────────────────────────────────────────────
    st.markdown(
        '<div class="hpc-header">HPC <span>Video</span> Tools</div>',
        unsafe_allow_html=True,
    )

    # ── FYP Banner ───────────────────────────────────────────────
    fyp = get_fyp_status()
    if fyp["current_window"]:
        cw = fyp["current_window"]
        nw = fyp["next_window"]
        st.markdown(
            f'<div class="fyp-banner">'
            f'<span class="fyp-live">LIVE</span>'
            f'<span>{cw["label"]} &mdash; {cw["desc"]}</span>'
            f'<span class="fyp-next">| Next: {nw["label"]} dalam {fyp["minutes_to_next"]} mnt</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        nw = fyp["next_window"]
        st.markdown(
            f'<div class="fyp-banner">'
            f'<span>⏳ Di luar jam FYP</span>'
            f'<span class="fyp-next">| Window berikutnya: {nw["label"]} '
            f'dalam {fyp["minutes_to_next"]} mnt</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Sidebar ───────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<div style="font-family:\'Space Mono\',monospace;font-size:0.62rem;'
            'letter-spacing:2.5px;color:#30306a;text-transform:uppercase;'
            'padding:1rem 0 0.6rem;">Navigation</div>',
            unsafe_allow_html=True,
        )
        page = st.radio(
            "nav",
            ["🎬  Download & Edit", "🍪  Kelola Cookies", "ℹ️  Info"],
            label_visibility="collapsed",
        )
        st.markdown(
            "<hr style='border:none;border-top:1px solid #141424;margin:0.8rem 0'>",
            unsafe_allow_html=True,
        )
        cookies_ok = os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100
        dot_c  = "#3ddc84" if cookies_ok else "#dc983d"
        dot_lb = "Cookies aktif" if cookies_ok else "Cookies kosong"
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:7px;'
            f'font-size:0.73rem;color:#50507a;">'
            f'<div style="width:6px;height:6px;border-radius:50%;background:{dot_c}"></div>'
            f'{dot_lb}</div>',
            unsafe_allow_html=True,
        )

    # ── Pages ─────────────────────────────────────────────────────
    if "Kelola Cookies" in page:
        render_cookies_uploader()
        return

    if "Info" in page:
        st.markdown('<div class="sec-label">Tentang</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="hpc-card">'
            '<div class="hpc-card-title">Stack</div>'
            '<div style="font-size:0.85rem;color:#7070a0;line-height:2;">'
            'yt-dlp &nbsp;&middot;&nbsp; faster-whisper &nbsp;&middot;&nbsp; '
            'moviepy &nbsp;&middot;&nbsp; streamlit'
            '</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="sec-label">Path Aktif</div>', unsafe_allow_html=True)
        st.json({
            "TMP_DIR": TMP_DIR,
            "OUTPUT_DIR": OUTPUT_DIR,
            "COOKIES_FILE": COOKIES_FILE,
            "FONT_PATH": FONT_PATH or "tidak ditemukan",
        })
        return

    # ── Download & Edit ───────────────────────────────────────────
    st.markdown('<div class="sec-label">Input URL</div>', unsafe_allow_html=True)
    url = st.text_input(
        "url",
        placeholder="https://youtu.be/...  atau  https://tiktok.com/...",
        label_visibility="collapsed",
    )

    st.markdown('<div class="sec-label">Opsi</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="hpc-card"><div class="hpc-card-title">Audio & Subtitle</div>', unsafe_allow_html=True)
        whisper_model = st.selectbox("Model Whisper", ["tiny", "base", "small", "medium"], index=1)
        add_sub       = st.checkbox("Tambah Subtitle Otomatis", value=True)
        sub_fontsize  = st.slider("Ukuran Font", 20, 80, 40) if add_sub else 40
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="hpc-card"><div class="hpc-card-title">Visual & BGM</div>', unsafe_allow_html=True)
        add_wm  = st.checkbox("Tambah Watermark")
        wm_file = None
        if add_wm:
            wm_file = st.file_uploader("Watermark (PNG/JPG)", type=["png", "jpg", "jpeg"])

        use_bgm  = st.checkbox("Tambah Background Music")
        bgm_file = None
        bgm_vol  = 0.15
        if use_bgm:
            bgm_file = st.file_uploader("BGM (MP3/WAV)", type=["mp3", "wav"])
            bgm_vol  = st.slider("Volume BGM", 0.05, 0.5, 0.15, step=0.05)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("🚀  Proses Video", disabled=not bool(url and url.strip())):
        progress = st.progress(0, text="Memulai…")
        status   = st.empty()

        # 1. Download
        status.markdown('<div class="box-info">⬇ Mendownload video…</div>', unsafe_allow_html=True)
        progress.progress(10, text="Download…")
        video_path = download_video(url.strip())
        if not video_path or not os.path.exists(video_path):
            st.markdown(
                '<div class="box-err">❌ Download gagal. Cek URL atau upload cookies '
                'di halaman 🍪 Kelola Cookies.</div>',
                unsafe_allow_html=True,
            )
            return
        progress.progress(30, text="Download selesai")

        # 2. Transkripsi
        segments = []
        if add_sub:
            status.markdown('<div class="box-info">🎙 Transkripsi audio…</div>', unsafe_allow_html=True)
            progress.progress(40, text="Transkripsi…")
            segments = transcribe_video(video_path, model_size=whisper_model)
            progress.progress(60, text="Transkripsi selesai")

            if segments:
                full_text      = " ".join(s["text"] for s in segments)
                emotion, score = analyze_emotion(full_text)
                st.markdown(
                    f'<div class="box-info">Emosi dominan: '
                    f'<b style="color:#9580ff">{emotion}</b> &nbsp; skor: {score}</div>',
                    unsafe_allow_html=True,
                )
                with st.expander("📝 Lihat Transkrip"):
                    for seg in segments:
                        t = f"{int(seg['start']//60):02d}:{seg['start']%60:05.2f}"
                        st.text(f"[{t}] {seg['text']}")

        # 3. Edit
        status.markdown('<div class="box-info">✂ Memproses video…</div>', unsafe_allow_html=True)
        progress.progress(70, text="Editing…")

        try:
            clip = VideoFileClip(video_path)

            if add_sub and segments:
                clip = add_subtitles(clip, segments, fontsize=sub_fontsize)

            if add_wm and wm_file is not None:
                wm_path = os.path.join(WM_DIR, f"wm_{uuid.uuid4().hex[:6]}.png")
                with open(wm_path, "wb") as f:
                    f.write(wm_file.read())
                clip = add_watermark(clip, wm_path)

            if use_bgm and bgm_file is not None:
                with open(BGM_PATH, "wb") as f:
                    f.write(bgm_file.read())
                clip = add_bgm(clip, BGM_PATH, bgm_volume=bgm_vol)

            progress.progress(80, text="Rendering…")
            uid_out  = uuid.uuid4().hex[:8]
            out_path = os.path.join(OUTPUT_DIR, f"output_{uid_out}.mp4")
            export_clip(clip, out_path)
            clip.close()

        except Exception as e:
            st.markdown(f'<div class="box-err">❌ Gagal memproses video: {e}</div>', unsafe_allow_html=True)
            return

        progress.progress(100, text="Selesai!")
        status.markdown('<div class="box-ok">✓ Video berhasil diproses!</div>', unsafe_allow_html=True)

        with open(out_path, "rb") as f:
            st.download_button(
                label="⬇  Download Video Hasil",
                data=f,
                file_name=f"hpc_output_{uid_out}.mp4",
                mime="video/mp4",
            )

        try:
            os.remove(video_path)
        except Exception:
            pass


if __name__ == "__main__":
    main()
