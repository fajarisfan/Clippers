import streamlit as st
import os, glob, uuid, re, random, subprocess, json
from collections import Counter

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

# ── Direktori kerja (/tmp writable di Streamlit Cloud) ───────────
TMP_DIR    = "/tmp/fc_tmp"
OUTPUT_DIR = "/tmp/fc_output"
WM_DIR     = "/tmp/fc_wm"
BGM_PATH   = "/tmp/fc_bgm.mp3"

for _d in [TMP_DIR, OUTPUT_DIR, WM_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── Font resolver ────────────────────────────────────────────────
_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
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

VIRAL_KEYWORDS = [
    "bunuh","mati","mampus","tembak","tusuk","lawan","hajar","serang","kejar","kabur",
    "ledak","hancur","jatuh","tabrak","bakar","api","darah","luka","jerit","tembakan",
    "cinta","sayang","rindu","selingkuh","khianat","cerai","nikah","hamil","tangis","nangis",
    "maaf","benci","dendam","bahagia","sedih","kecewa","patah","pergi","tinggal","peluk",
    "lucu","ngakak","gila","goblok","bego","norak","lebay","alay","malu","panik",
    "hantu","setan","pocong","kuntilanak","misteri","rahasia","sembunyi","bohong","tipu","kutuk",
    "tidak","jangan","tolong","bantu","harus","berani","takut","dengar","percaya","diam",
    "kill","die","love","hate","run","stop","help","never","always","truth",
    "lie","fight","dead","fire","secret","sorry","leave","stay","trust","alone",
]

STOPWORDS = {
    "yang","dan","di","ke","dari","ini","itu","dengan","untuk","ada","tidak","juga",
    "saya","aku","kamu","dia","kami","kita","mereka","nya","pun","lah","kah","ya",
    "tapi","atau","karena","kalau","jika","maka","saat","waktu","sudah","akan","bisa",
    "adalah","pada","dalam","oleh","setelah","sebelum","ketika","seperti","buat","lagi",
    "masih","belum","baru","sangat","sekali","lebih","terus","punya","the","a","an",
    "is","are","was","were","be","been","have","has","had","do","does","did","will",
    "would","could","should","may","might","shall","can","just","said","i","you","he",
    "she","we","they","it","me","him","her","us","them","my","your","his","our","their",
    "this","that","these","those","here","there","then","and","but","or","so","if","as",
    "at","by","for","in","of","on","to","up","out","go","gua","gue","lo","lu","ga","gak",
    "nggak","udah","aja","sama","jadi","tuh","nih","emang","kayak","bener","banget","dong",
    "deh","sih","lho","wah","eh","oh","ah","tau","mau","baik","pagi","sore","malam","hari",
    "kali","orang","tempat","hal","dua","tiga","satu","lima","banyak","semua","namun","tetap",
}

HOOK_POOL = [
    "Scene ini bikin jutaan orang nangis...",
    "Salah satu scene terbaik film Indonesia.",
    "Dialog ini viral di mana-mana.",
    "Tonton sampai habis, dijamin merinding.",
    "Akting terbaik yang pernah ada.",
    "Scene ini bikin bioskop hening total.",
    "Ini alasan film ini jadi legenda.",
    "Adegan ini bikin bulu kuduk berdiri.",
]


# ════════════════════════════════════════════════════════════════
#  YT-DLP — ambil info & URL stream (TANPA download full)
# ════════════════════════════════════════════════════════════════
def _ydl_opts(extra: dict = None) -> dict:
    opts = {
        "quiet":            True,
        "no_warnings":      True,
        "extractor_retries": 3,
        "socket_timeout":   30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    }
    if extra:
        opts.update(extra)
    return opts


def get_video_info(url: str) -> dict:
    """Ambil metadata film tanpa download."""
    with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
        return ydl.extract_info(url, download=False)


def get_stream_urls(url: str) -> tuple[str, str]:
    """
    Return (video_url, audio_url) — direct stream URL dari server hosting.
    Tidak ada file yang didownload ke disk.
    """
    opts = _ydl_opts({
        "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
    })
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Kalau ada requested_formats (video+audio terpisah)
    if "requested_formats" in info:
        video_url = next(
            (f["url"] for f in info["requested_formats"] if f.get("vcodec") != "none"), None
        )
        audio_url = next(
            (f["url"] for f in info["requested_formats"] if f.get("acodec") != "none"), None
        )
        return video_url or info.get("url", ""), audio_url or video_url or info.get("url", "")

    direct = info.get("url", "")
    return direct, direct


# ════════════════════════════════════════════════════════════════
#  AUDIO ANALYSIS — download HANYA audio stream (sementara)
# ════════════════════════════════════════════════════════════════
def download_audio_only(audio_url: str, duration: float, max_sec: int = 600) -> str:
    """
    Download audio stream saja (bukan video) ke /tmp untuk dianalisis Whisper.
    Maksimal max_sec detik pertama — hemat bandwidth & waktu.
    """
    out_path = os.path.join(TMP_DIR, f"audio_{uuid.uuid4().hex[:6]}.wav")
    limit    = min(duration, max_sec)

    cmd = [
        "ffmpeg", "-y",
        "-headers", "User-Agent: Mozilla/5.0",
        "-i", audio_url,
        "-t", str(limit),
        "-vn",                    # skip video
        "-ar", "16000",           # 16kHz cukup buat Whisper
        "-ac", "1",               # mono
        "-f", "wav",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"ffmpeg audio extract gagal: {result.stderr.decode()[:300]}")
    return out_path


# ════════════════════════════════════════════════════════════════
#  WHISPER — transkripsi word-level
# ════════════════════════════════════════════════════════════════
@st.cache_resource
def load_whisper(model_size: str):
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe_audio(audio_path: str, model_size: str = "tiny") -> tuple[list, list]:
    model  = load_whisper(model_size)
    raw, _ = model.transcribe(audio_path, beam_size=1, vad_filter=True, word_timestamps=True)
    segments, words = [], []
    for seg in raw:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        if seg.words:
            for w in seg.words:
                wc = w.word.strip()
                if wc:
                    words.append({"start": w.start, "end": w.end, "word": wc})
    return segments, words


# ════════════════════════════════════════════════════════════════
#  SCORING — deteksi scene terbaik dari energi audio + kata kunci
# ════════════════════════════════════════════════════════════════
def score_clips(audio_path: str, segments: list, duration: float, n_clips: int,
                min_dur: int, max_dur: int) -> list:
    import librosa

    y, sr    = librosa.load(audio_path, mono=True)
    hop      = sr * 2
    rms      = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_norm = (rms - rms.min()) / (rms.max() - rms.min() + 1e-9)
    times    = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    candidates = []
    step = max(5, min_dur // 3)
    for sf in np.arange(0, min(duration, times[-1] if len(times) else duration) - min_dur, step):
        ef = min(float(sf) + random.randint(min_dur, max_dur), duration)
        if ef - sf < min_dur:
            continue
        mask  = (times >= sf) & (times <= ef)
        e_sc  = float(rms_norm[mask].mean()) if mask.any() else 0.0
        sp_sc = float(rms_norm[mask].std())  if mask.any() else 0.0
        kw, preview = 0, ""
        for seg in segments:
            if seg["end"] < sf or seg["start"] > ef:
                continue
            hits = sum(1 for kw_ in VIRAL_KEYWORDS if kw_ in seg["text"].lower())
            kw += hits
            if not preview and hits:
                preview = seg["text"]
        total = (e_sc * 0.3) + (min(kw, 10) / 10 * 0.5) + (sp_sc * 0.2)
        candidates.append({
            "start":    float(sf), "end": float(ef), "score": total,
            "energy":   e_sc,      "keywords": kw,
            "preview":  preview.strip() or "—",
            "label":    f"{int(sf//60):02d}:{int(sf%60):02d} – {int(ef//60):02d}:{int(ef%60):02d}",
        })

    candidates.sort(key=lambda x: -x["score"])
    selected = []
    for c in candidates:
        if not any(
            min(c["end"], s["end"]) - max(c["start"], s["start"]) > (c["end"] - c["start"]) * 0.5
            for s in selected
        ):
            selected.append(c)
        if len(selected) >= n_clips:
            break
    return selected


# ════════════════════════════════════════════════════════════════
#  HASHTAG GENERATOR
# ════════════════════════════════════════════════════════════════
def generate_hashtags(segments: list, title: str) -> str:
    title_words = re.findall(r"[a-zA-Z]{3,}", title)
    film_tags   = ["#" + w.lower() for w in title_words if w.lower() not in STOPWORDS]

    if not segments:
        return " ".join(film_tags[:28])

    full_text   = " ".join(s["text"] for s in segments)
    lower_words = [w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", full_text)]
    freq        = Counter(w for w in lower_words if w not in STOPWORDS)

    specific    = sorted([w for w, c in freq.items() if 2 <= c <= 8 and len(w) >= 5],
                         key=lambda w: freq[w], reverse=True)[:5]
    viral_found = list(dict.fromkeys(
        kw.replace("-","") for kw in VIRAL_KEYWORDS
        if kw.replace("-","") in freq or kw in full_text.lower()
    ))[:5]
    common      = [w for w, c in freq.most_common(30)
                   if w not in STOPWORDS and len(w) >= 5
                   and w not in specific and w not in viral_found][:4]
    universal   = [
        "filmIndonesia","bioskopIndonesia","rekomendasifilm","cuplikanfilm",
        "fyp","fypシ","viral","tiktokfilm","filmhits","klipfilm",
        "sinemaIndonesia","filmbagus","scene","movieclip",
    ]

    all_tags = (film_tags + ["#"+w for w in specific] + ["#"+w for w in viral_found]
                + ["#"+w for w in common] + ["#"+w for w in universal])
    seen, out = set(), []
    for t in all_tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return " ".join(out[:28])


# ════════════════════════════════════════════════════════════════
#  COLOR GRADING
# ════════════════════════════════════════════════════════════════
def make_grade_fn(style: str):
    if style == "warm":
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f-128)*1.15+135, 0, 255)
            f[:,:,0] = np.clip(f[:,:,0]*1.10, 0, 255)
            f[:,:,2] = np.clip(f[:,:,2]*0.90, 0, 255)
            return f.astype(np.uint8)
    elif style == "noir":
        def fn(f):
            f = f.astype(np.float32)
            g = f.mean(axis=2, keepdims=True)
            return np.clip((g*np.ones_like(f)-128)*1.45+128, 0, 255).astype(np.uint8)
    elif style == "vibrant":
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f-128)*1.3+128, 0, 255)
            g = f.mean(axis=2, keepdims=True)
            return np.clip(f*1.15 - g*0.15, 0, 255).astype(np.uint8)
    else:  # sinematik
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f-128)*1.2+128, 0, 255)
            g = f.mean(axis=2, keepdims=True)
            f = f*0.85 + g*0.15
            f[:,:,0] = np.clip(f[:,:,0]*0.94, 0, 255)
            f[:,:,2] = np.clip(f[:,:,2]*1.04, 0, 255)
            return f.astype(np.uint8)
    return fn


# ════════════════════════════════════════════════════════════════
#  SUBTITLE BUILDERS
# ════════════════════════════════════════════════════════════════
def _tc(text, size, color, stroke_w, dur, width=960):
    if not FONT_PATH:
        return None
    try:
        return TextClip(text=text, font_size=size, color=color, font=FONT_PATH,
                        stroke_color="black", stroke_width=stroke_w,
                        size=(width, None), method="caption", duration=dur)
    except Exception:
        return None


def subs_tiktok(words, cs, ce, sub_y, color):
    layers, dur = [], ce - cs
    for w in words:
        t0 = max(w["start"]-cs, 0)
        t1 = min(w["end"]-cs, dur)
        if t1 - t0 < 0.01:
            continue
        tc = _tc(w["word"].upper(), 96, color, 5, t1-t0, 900)
        if tc:
            layers.append(tc.with_start(t0).with_position(("center", sub_y)))
    return layers


def subs_kalimat(segments, cs, ce, sub_y, color):
    layers, dur = [], ce - cs
    for seg in segments:
        t0 = max(seg["start"]-cs, 0)
        t1 = min(seg["end"]-cs, dur)
        if t1 - t0 < 0.01:
            continue
        tc = _tc(seg["text"], 50, color, 2, t1-t0, 960)
        if tc:
            layers.append(tc.with_start(t0).with_position(("center", sub_y)))
    return layers


# ════════════════════════════════════════════════════════════════
#  RENDER — potong langsung dari stream URL via ffmpeg+MoviePy
# ════════════════════════════════════════════════════════════════
def render_clip_from_stream(
    video_url: str, audio_url: str,
    start: float, end: float,
    segments: list, words: list, *,
    use_subs, sub_style, sub_position, sub_color,
    use_grade, grade_style,
    use_hook, hook_text,
    use_bgm, watermark_path,
    output_name: str = "",
) -> str:
    dur      = end - start
    tmp_clip = os.path.join(TMP_DIR, f"raw_{uuid.uuid4().hex[:6]}.mp4")

    # Step 1: Potong segment dari stream pakai ffmpeg (tidak download full)
    st.caption("⏬ Mengambil segment dari stream...")
    if video_url == audio_url:
        # Single stream (video+audio dalam 1 URL)
        cmd = [
            "ffmpeg", "-y",
            "-headers", "User-Agent: Mozilla/5.0",
            "-ss", str(start),
            "-i", video_url,
            "-t", str(dur),
            "-c", "copy",
            tmp_clip,
        ]
    else:
        # Video & audio terpisah — merge via ffmpeg
        cmd = [
            "ffmpeg", "-y",
            "-headers", "User-Agent: Mozilla/5.0",
            "-ss", str(start), "-i", video_url,
            "-ss", str(start), "-i", audio_url,
            "-t", str(dur),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac",
            tmp_clip,
        ]

    result = subprocess.run(cmd, capture_output=True, timeout=180)
    if result.returncode != 0 or not os.path.exists(tmp_clip):
        # Fallback: re-encode (lebih lambat tapi lebih kompatibel)
        st.caption("⚠️ Copy stream gagal, fallback re-encode...")
        cmd_fb = [
            "ffmpeg", "-y",
            "-headers", "User-Agent: Mozilla/5.0",
            "-ss", str(start),
            "-i", video_url,
            "-t", str(dur),
            "-c:v", "libx264", "-c:a", "aac",
            tmp_clip,
        ]
        subprocess.run(cmd_fb, capture_output=True, timeout=300)

    # Step 2: Buka klip dengan MoviePy dan terapkan efek
    st.caption("🎨 Menerapkan efek & subtitle...")
    clip  = VideoFileClip(tmp_clip)
    final = clip.copy()

    # Crop 9:16 → 1080×1920
    w, h  = final.size
    final = final.with_effects([
        vfx.Crop(x_center=w/2, width=int(h*9/16), height=h),
        vfx.Resize(height=1920),
    ])
    fw = final.size[0]

    if use_grade:
        final = final.image_transform(make_grade_fn(grade_style))

    layers = [final]

    if use_subs and FONT_PATH:
        sub_y = 1620 if sub_position == "Bawah" else 200
        if "TikTok" in sub_style and words:
            layers.extend(subs_tiktok(words, start, end, sub_y, sub_color))
        else:
            layers.extend(subs_kalimat(segments, start, end, sub_y, sub_color))

    if use_hook and FONT_PATH:
        h_text = hook_text.strip() or random.choice(HOOK_POOL)
        tc = _tc(h_text, 48, "#FFD700", 3, 3.5, 960)
        if tc:
            layers.append(tc.with_start(0).with_position(("center", 220)))

    if watermark_path and os.path.exists(watermark_path):
        try:
            wm = (ImageClip(watermark_path)
                  .with_effects([vfx.Resize(width=200)])
                  .with_opacity(0.75)
                  .with_duration(final.duration)
                  .with_position((fw-230, 50)))
            layers.append(wm)
        except Exception:
            pass

    if len(layers) > 1:
        final = CompositeVideoClip(layers)

    if use_bgm and os.path.exists(BGM_PATH):
        try:
            bgm  = (AudioFileClip(BGM_PATH)
                    .with_effects([afx.MultiplyVolume(0.12)])
                    .with_duration(final.duration))
            orig = final.audio
            final = final.with_audio(CompositeAudioClip([orig, bgm]) if orig else bgm)
        except Exception:
            pass

    safe     = re.sub(r"[^\w]", "_", output_name)[:40] if output_name else uuid.uuid4().hex[:8]
    out_path = os.path.join(OUTPUT_DIR, f"{safe}.mp4")

    final.write_videofile(
        out_path, codec="libx264", bitrate="10000k", fps=30, logger=None,
        ffmpeg_params=["-pix_fmt","yuv420p","-profile:v","high","-level","4.1","-movflags","+faststart"],
    )
    clip.close()

    # Bersihkan tmp
    try:
        os.remove(tmp_clip)
    except Exception:
        pass

    return out_path


# ════════════════════════════════════════════════════════════════
#  STREAMLIT UI
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="🎬 Film Clipper ID", layout="wide")
st.title("🎬 Film Clipper Indonesia")
st.caption("Paste link film → AI analisis scene terbaik → potong langsung dari stream → siap upload")

# ── SIDEBAR ──────────────────────────────────────────────────────
with st.sidebar:

    st.subheader("⚙️ Pengaturan Klip")
    n_clips    = st.slider("Jumlah saran scene", 3, 12, 6)
    min_dur    = st.slider("Durasi min (detik)", 10, 60, 25)
    max_dur    = st.slider("Durasi maks (detik)", 20, 120, 55)
    model_size = st.selectbox("Model Whisper", ["tiny","base","small"], index=0,
                               help="tiny=cepat | base=seimbang | small=paling akurat")

    st.divider()
    st.subheader("🎨 Color Grading")
    use_grade   = st.checkbox("Aktifkan", value=True)
    grade_style = st.selectbox("Gaya", ["sinematik","warm","vibrant","noir"], disabled=not use_grade)

    st.divider()
    st.subheader("💬 Auto Subtitle")
    use_subs     = st.checkbox("Auto Caption (Voice-to-Text)", value=True)
    sub_style    = st.selectbox("Gaya subtitle",
                                ["🎬 TikTok — per kata, gede","📝 Kalimat — klasik"],
                                disabled=not use_subs)
    sub_position = st.selectbox("Posisi", ["Bawah","Atas"], disabled=not use_subs)
    sub_color    = st.selectbox("Warna teks", ["white","yellow","#FFD700","#00FFFF"],
                                disabled=not use_subs)

    st.divider()
    st.subheader("🎣 Hook & BGM")
    use_hook    = st.checkbox("Hook Text (3 detik pertama)", value=True)
    custom_hook = st.text_input("Custom hook (kosong = auto)")
    use_bgm     = st.checkbox("Background Music", value=False)
    bgm_upload  = st.file_uploader("Upload BGM (.mp3)", type=["mp3"])
    if bgm_upload:
        with open(BGM_PATH, "wb") as fh:
            fh.write(bgm_upload.read())
        st.success("✅ BGM tersimpan!")
    st.caption("🎵 BGM aktif" if os.path.exists(BGM_PATH) else "Belum ada BGM")

    st.divider()
    st.subheader("🖼️ Watermark")
    wm_upload = st.file_uploader("Upload logo (PNG transparan)", type=["png","jpg","jpeg"])
    if wm_upload:
        wm_save = os.path.join(WM_DIR, wm_upload.name)
        with open(wm_save, "wb") as fh:
            fh.write(wm_upload.read())
        st.session_state["watermark"] = wm_save
        st.success(f"✅ {wm_upload.name}")
        st.rerun()

    wm_files = [f for f in os.listdir(WM_DIR) if f.lower().endswith((".png",".jpg",".jpeg"))]
    if wm_files:
        chosen_wm = st.selectbox("Pilih watermark", ["(tidak pakai)"]+wm_files)
        st.session_state["watermark"] = (
            os.path.join(WM_DIR, chosen_wm) if chosen_wm != "(tidak pakai)" else None
        )
    else:
        st.caption("Belum ada watermark.")
        st.session_state.setdefault("watermark", None)

    st.divider()
    st.caption("💡 **Supported sites:** ngefilm, filmapik, lk21, dan 1000+ situs lain via yt-dlp. YouTube bisa error 403 di cloud server.")


# ════════════════════════════════════════════════════════════════
#  MAIN — Input link
# ════════════════════════════════════════════════════════════════
watermark_path = st.session_state.get("watermark")

# Input URL
st.subheader("🔗 Paste Link Film")
col_url, col_btn = st.columns([4, 1])
with col_url:
    input_url = st.text_input(
        "Link film",
        placeholder="https://ngefilm.bio/... atau https://filmapik.cc/...",
        label_visibility="collapsed",
    )
with col_btn:
    btn_load = st.button("📡 Load", use_container_width=True, type="primary")

# ── Load info dari URL ───────────────────────────────────────────
if btn_load and input_url:
    with st.spinner("📡 Mengambil info film..."):
        try:
            info = get_video_info(input_url)
            st.session_state["film_info"]     = info
            st.session_state["film_url"]      = input_url
            st.session_state["film_title"]    = info.get("title", "Unknown")
            st.session_state["film_duration"] = info.get("duration", 0) or 0
            st.session_state["film_thumb"]    = info.get("thumbnail")
            # Reset analisis sebelumnya
            for k in ["suggestions","segs","words","hashtags","audio_path"]:
                st.session_state.pop(k, None)
            st.rerun()
        except Exception as e:
            st.error(f"❌ Gagal load link: {e}")
            st.caption("Pastikan link valid dan situs mendukung yt-dlp. YouTube bisa 403 di Streamlit Cloud.")

# ── Tampilkan info film ──────────────────────────────────────────
if "film_title" in st.session_state:
    title    = st.session_state["film_title"]
    duration = st.session_state["film_duration"]
    thumb    = st.session_state.get("film_thumb")
    url      = st.session_state["film_url"]

    st.markdown("---")
    col_thumb, col_meta = st.columns([1, 3])
    with col_thumb:
        if thumb:
            st.image(thumb, use_container_width=True)
    with col_meta:
        st.subheader(title)
        dur_str = f"{int(duration//3600)}j {int((duration%3600)//60)}m {int(duration%60)}s" if duration >= 3600 \
                  else f"{int(duration//60)}m {int(duration%60)}s"
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("⏱️ Durasi", dur_str if duration else "?")
        col_b.metric("🖼️ WM",    "✅ Ada" if watermark_path else "❌ Belum")
        col_c.metric("🔤 Font",  "✅ OK"  if FONT_PATH      else "⚠️ N/A")
        st.caption(f"🔗 `{url[:80]}{'...' if len(url)>80 else ''}`")

    st.markdown("---")

    # Tombol analisis
    if st.button("🔍 Analisis Scene Terbaik (AI)", type="primary", use_container_width=True):
        try:
            with st.spinner("📡 Mengambil stream URL..."):
                video_url, audio_url = get_stream_urls(url)
                st.session_state["video_url"] = video_url
                st.session_state["audio_url"] = audio_url

            with st.spinner("⏬ Download audio untuk analisis AI (sementara)..."):
                audio_path = download_audio_only(audio_url, duration, max_sec=600)
                st.session_state["audio_path"] = audio_path

            with st.spinner(f"🤖 Transkripsi AI ({model_size}) — word-by-word..."):
                segs, words = transcribe_audio(audio_path, model_size)
                st.session_state["segs"]  = segs
                st.session_state["words"] = words

            with st.spinner("📊 Scoring scene terbaik..."):
                suggestions = score_clips(audio_path, segs, duration, n_clips, min_dur, max_dur)
                hashtags    = generate_hashtags(segs, title)
                st.session_state["suggestions"] = suggestions
                st.session_state["hashtags"]    = hashtags

            st.rerun()
        except Exception as e:
            st.error(f"❌ Analisis gagal: {e}")


# ── Hasil Analisis ───────────────────────────────────────────────
if "suggestions" in st.session_state and "film_title" in st.session_state:
    suggestions = st.session_state["suggestions"]
    segs        = st.session_state.get("segs", [])
    words       = st.session_state.get("words", [])
    hashtags    = st.session_state.get("hashtags", "")
    title       = st.session_state["film_title"]
    video_url   = st.session_state.get("video_url", "")
    audio_url   = st.session_state.get("audio_url", "")
    duration    = st.session_state.get("film_duration", 0)

    # Caption & Hashtag
    if hashtags:
        opening = segs[0]["text"][:80] + "..." if segs else ""
        caption = (f'🎙️ "{opening}"\n\n' if opening else "") + hashtags

        with st.container(border=True):
            t1, t2 = st.tabs(["📋 Caption TikTok / Reels", "# Hashtags"])
            with t1:
                st.text_area("cap", caption, height=180, label_visibility="collapsed")
                st.caption("Copy-paste langsung ke TikTok / Reels / YouTube Shorts")
            with t2:
                st.text_area("ht", hashtags, height=100, label_visibility="collapsed")
                tags = [t for t in hashtags.split() if t.startswith("#")]
                c1, c2 = st.columns(2)
                c1.metric("Total hashtag", len(tags))
                if c2.button("🔄 Generate Ulang"):
                    st.session_state["hashtags"] = generate_hashtags(segs, title)
                    st.rerun()

    # Preview transkripsi
    if words:
        with st.expander(f"🔤 Preview Transkripsi — {len(words)} kata ({len(segs)} segmen)", expanded=False):
            ca, cb = st.columns(2)
            ca.caption("**50 kata pertama + timing:**")
            ca.markdown("  ".join(f"`{w['word']}` _{w['start']:.1f}s_" for w in words[:50])
                        + (" …" if len(words) > 50 else ""))
            cb.caption("**Full teks:**")
            full_txt = " ".join(s["text"] for s in segs)
            cb.caption(full_txt[:500] + ("…" if len(full_txt) > 500 else ""))

    st.markdown("---")
    st.subheader(f"🎯 {len(suggestions)} Scene Terbaik Ditemukan")

    if not suggestions:
        st.warning("Tidak ada scene ditemukan. Coba kurangi durasi minimum.")
    else:
        def do_render(start, end, out_name):
            try:
                out = render_clip_from_stream(
                    video_url, audio_url, start, end, segs, words,
                    use_subs=use_subs, sub_style=sub_style,
                    sub_position=sub_position, sub_color=sub_color,
                    use_grade=use_grade, grade_style=grade_style,
                    use_hook=use_hook, hook_text=custom_hook,
                    use_bgm=use_bgm, watermark_path=watermark_path,
                    output_name=out_name,
                )
                st.success("✅ Selesai! Cek gallery di bawah.")
                st.balloons()
            except Exception as e:
                st.error(f"Render gagal: {e}")

        # Render semua sekaligus
        if len(suggestions) > 1 and st.button("🚀 Render SEMUA Scene Sekaligus", use_container_width=True):
            prog = st.progress(0, text="Memulai...")
            for idx, sug in enumerate(suggestions):
                prog.progress(idx/len(suggestions), text=f"Rendering scene #{idx+1}...")
                do_render(
                    sug["start"], sug["end"],
                    f"{re.sub(r'[^\\w]','_',title)[:30]}_scene{idx+1}",
                )
            prog.progress(1.0, text="✅ Semua selesai!")
            st.balloons()
            st.rerun()

        # Tiap scene
        for i, sug in enumerate(suggestions):
            score_pct = int(sug["score"] * 100)
            stars     = "⭐" * min(5, max(1, int(score_pct/20)))
            with st.expander(
                f"**Scene #{i+1}** — {sug['label']} | {stars} Skor: {score_pct}%",
                expanded=(i == 0),
            ):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("⏱️ Durasi",   f"{int(sug['end']-sug['start'])}s")
                c2.metric("🔥 Keywords", sug["keywords"])
                c3.metric("🔊 Energi",   f"{int(sug['energy']*100)}%")
                c4.metric("📊 Skor",     f"{score_pct}%")
                if sug["preview"] != "—":
                    st.info(f'💬 *"{sug["preview"]}"*')
                if st.button(f"🚀 Render Scene #{i+1}", key=f"r_{i}", use_container_width=True):
                    with st.spinner(f"Rendering scene #{i+1}..."):
                        do_render(
                            sug["start"], sug["end"],
                            f"{re.sub(r'[^\\w]','_',title)[:30]}_scene{i+1}",
                        )

        # Manual override
        st.markdown("---")
        with st.expander("✏️ Potong Manual — tentukan sendiri start & end"):
            cm1, cm2 = st.columns(2)
            m_s = cm1.number_input("▶ Start (detik)", 0.0, float(duration or 9999), 0.0,   step=1.0, key="ms")
            m_e = cm2.number_input("⏹ End (detik)",   0.0, float(duration or 9999), min(float(duration or 60), 60.0), step=1.0, key="me")
            m_name = st.text_input("Nama output (opsional)", placeholder="scene_joget_lucu")
            if st.button("🚀 Render Manual", use_container_width=True):
                if m_e <= m_s:
                    st.error("End harus lebih besar dari Start!")
                else:
                    with st.spinner("Rendering..."):
                        do_render(m_s, m_e, m_name.strip() or f"{re.sub(r'[^\\w]','_',title)[:30]}_manual")


# ════════════════════════════════════════════════════════════════
#  OUTPUT GALLERY
# ════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📁 Hasil Klip")

output_files = sorted(
    (f for f in os.listdir(OUTPUT_DIR) if f.endswith(".mp4")),
    key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)),
    reverse=True,
)

if not output_files:
    st.caption("Belum ada klip yang dirender.")
else:
    st.caption(f"{len(output_files)} klip tersedia")
    if st.button("🗑️ Hapus Semua Klip"):
        for f in output_files:
            try: os.remove(os.path.join(OUTPUT_DIR, f))
            except Exception: pass
        st.rerun()

    for f in output_files:
        fpath   = os.path.join(OUTPUT_DIR, f)
        size_mb = os.path.getsize(fpath) / 1_048_576
        st.write(f"🎞️ **{f}** — {size_mb:.1f} MB")
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.video(fpath)
        with open(fpath, "rb") as fh:
            c2.download_button("⬇️ Download", fh, file_name=f,
                               mime="video/mp4", key=f"dl_{f}", use_container_width=True)
        if c3.button("🗑️ Hapus", key=f"del_{f}", use_container_width=True):
            os.remove(fpath)
            st.rerun()
