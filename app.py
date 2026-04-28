# ╔══════════════════════════════════════════════════════════════╗
# ║           FILM CLIPPER INDONESIA — Streamlit Cloud           ║
# ║  Upload film → AI detect scene → auto subtitle → siap upload ║
# ╚══════════════════════════════════════════════════════════════╝

import streamlit as st
import os, glob, uuid, re, random
from collections import Counter

import numpy as np
from faster_whisper import WhisperModel

from moviepy import (
    VideoFileClip, TextClip, ImageClip,
    CompositeVideoClip, AudioFileClip, CompositeAudioClip,
)
import moviepy.video.fx as vfx
import moviepy.audio.fx as afx

os.environ["PATH"] += os.pathsep + os.getcwd()

# Direktori /tmp (writable di Streamlit Cloud)
INPUT_DIR  = "/tmp/fc_input"
OUTPUT_DIR = "/tmp/fc_output"
WM_DIR     = "/tmp/fc_wm"
BGM_PATH   = "/tmp/fc_bgm.mp3"

for _d in [INPUT_DIR, OUTPUT_DIR, WM_DIR]:
    os.makedirs(_d, exist_ok=True)

# Font resolver
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]
FONT_PATH = next((f for f in _FONT_CANDIDATES if os.path.exists(f)), None)
if FONT_PATH is None:
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


# ── Whisper (cached agar tidak reload tiap klik) ─────────────────
@st.cache_resource
def load_whisper(model_size):
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe_video(video_path, model_size="tiny"):
    model  = load_whisper(model_size)
    raw, _ = model.transcribe(
        video_path, beam_size=1, vad_filter=True, word_timestamps=True,
    )
    segments, words = [], []
    for seg in raw:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        if seg.words:
            for w in seg.words:
                wc = w.word.strip()
                if wc:
                    words.append({"start": w.start, "end": w.end, "word": wc})
    return segments, words


# ── Hashtag generator ─────────────────────────────────────────────
def generate_hashtags(segments, video_name):
    film_name  = os.path.splitext(video_name)[0]
    film_words = re.findall(r"[a-zA-Z]{3,}", film_name)
    film_tags  = ["#" + w.lower() for w in film_words if w.lower() not in STOPWORDS]

    if not segments:
        return " ".join(film_tags[:28])

    full_text   = " ".join(s["text"] for s in segments)
    lower_words = [w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", full_text)]
    freq        = Counter(w for w in lower_words if w not in STOPWORDS)

    specific    = sorted([w for w, c in freq.items() if 2 <= c <= 8 and len(w) >= 5],
                         key=lambda w: freq[w], reverse=True)[:5]
    viral_found = list(dict.fromkeys(
        kw.replace("-", "") for kw in VIRAL_KEYWORDS
        if kw.replace("-", "") in freq or kw in full_text.lower()
    ))[:5]
    common      = [w for w, c in freq.most_common(30)
                   if w not in STOPWORDS and len(w) >= 5
                   and w not in specific and w not in viral_found][:4]
    universal   = [
        "filmIndonesia","bioskopIndonesia","rekomendasifilm","cuplikanfilm",
        "fyp","fypシ","viral","tiktokfilm","filmhits","klipfilm",
        "sinemaIndonesia","filmbagus","scene","movieclip",
    ]

    all_tags = (film_tags + ["#"+w for w in specific] +
                ["#"+w for w in viral_found] + ["#"+w for w in common] +
                ["#"+w for w in universal])
    seen, out = set(), []
    for t in all_tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return " ".join(out[:28])


# ── Analisis audio + suggest clips ───────────────────────────────
def analyze_and_suggest_clips(video_path, n_clips, min_dur, max_dur, model_size="tiny"):
    import librosa

    status    = st.empty()
    cache_key = f"analysis_{os.path.getsize(video_path)}_{os.path.basename(video_path)}_{model_size}"

    if cache_key in st.session_state:
        status.info("⚡ Data dari cache — instan!")
        cached = st.session_state[cache_key]
        status.empty()
        return cached["suggestions"], cached["segments"], cached["words"], cached["hashtags"]

    # Ekstrak audio
    status.info("🔍 Menganalisis energi audio...")
    try:
        clip    = VideoFileClip(video_path)
        tmp_wav = f"/tmp/fc_tmp_{uuid.uuid4().hex[:6]}.wav"
        clip.audio.write_audiofile(tmp_wav, logger=None)
        duration = clip.duration
        clip.close()
    except Exception as e:
        status.error(f"Gagal baca video: {e}")
        return [], [], [], ""

    y, sr    = librosa.load(tmp_wav, mono=True)
    os.remove(tmp_wav)
    hop      = sr * 2
    rms      = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_norm = (rms - rms.min()) / (rms.max() - rms.min() + 1e-9)
    times    = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    # Transkripsi
    status.info(f"🤖 Transkripsi AI ({model_size}) — word-by-word timing...")
    try:
        segments, words = transcribe_video(video_path, model_size)
    except Exception as e:
        st.warning(f"Transkripsi gagal ({e}) — lanjut tanpa subtitle.")
        segments, words = [], []

    # Scoring
    candidates = []
    step = max(5, min_dur // 3)
    for start_f in np.arange(0, duration - min_dur, step):
        end_f = min(float(start_f) + random.randint(min_dur, max_dur), duration)
        if end_f - start_f < min_dur:
            continue
        mask         = (times >= start_f) & (times <= end_f)
        energy_score = float(rms_norm[mask].mean()) if mask.any() else 0.0
        spike_score  = float(rms_norm[mask].std())  if mask.any() else 0.0
        kw_score, preview = 0, ""
        for seg in segments:
            if seg["end"] < start_f or seg["start"] > end_f:
                continue
            hits = sum(1 for kw in VIRAL_KEYWORDS if kw in seg["text"].lower())
            kw_score += hits
            if not preview and hits > 0:
                preview = seg["text"]
        total = (energy_score * 0.3) + (min(kw_score, 10) / 10 * 0.5) + (spike_score * 0.2)
        candidates.append({
            "start":    float(start_f), "end": float(end_f), "score": total,
            "energy":   energy_score,   "keywords": kw_score,
            "preview":  preview.strip() or "—",
            "label":    f"{int(start_f//60):02d}:{int(start_f%60):02d} – {int(end_f//60):02d}:{int(end_f%60):02d}",
        })

    candidates.sort(key=lambda x: -x["score"])
    selected = []
    for c in candidates:
        if not any(
            min(c["end"],s["end"]) - max(c["start"],s["start"]) > (c["end"]-c["start"]) * 0.5
            for s in selected
        ):
            selected.append(c)
        if len(selected) >= n_clips:
            break

    status.info("✨ Generating hashtags...")
    hashtags = generate_hashtags(segments, os.path.basename(video_path))

    st.session_state[cache_key] = {
        "suggestions": selected, "segments": segments,
        "words": words, "hashtags": hashtags,
    }
    status.empty()
    return selected, segments, words, hashtags


# ── Text clip helper ──────────────────────────────────────────────
def make_tc(text, font_size, color, stroke_w, duration, width=960):
    if not FONT_PATH:
        return None
    try:
        return TextClip(
            text=text, font_size=font_size, color=color,
            font=FONT_PATH, stroke_color="black", stroke_width=stroke_w,
            size=(width, None), method="caption", duration=duration,
        )
    except Exception:
        return None


# ── Subtitle builders ─────────────────────────────────────────────
def subs_tiktok(words, clip_start, clip_end, sub_y, color):
    layers, dur = [], clip_end - clip_start
    for w in words:
        t0 = max(w["start"] - clip_start, 0)
        t1 = min(w["end"]   - clip_start, dur)
        if t1 - t0 < 0.01:
            continue
        tc = make_tc(w["word"].upper(), 96, color, 5, t1 - t0, 900)
        if tc:
            layers.append(tc.with_start(t0).with_position(("center", sub_y)))
    return layers


def subs_kalimat(segments, clip_start, clip_end, sub_y, color):
    layers, dur = [], clip_end - clip_start
    for seg in segments:
        t0 = max(seg["start"] - clip_start, 0)
        t1 = min(seg["end"]   - clip_start, dur)
        if t1 - t0 < 0.01:
            continue
        tc = make_tc(seg["text"], 50, color, 2, t1 - t0, 960)
        if tc:
            layers.append(tc.with_start(t0).with_position(("center", sub_y)))
    return layers


# ── Color grading ─────────────────────────────────────────────────
def make_grade_fn(style):
    if style == "warm":
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f - 128) * 1.15 + 135, 0, 255)
            f[:,:,0] = np.clip(f[:,:,0] * 1.10, 0, 255)
            f[:,:,2] = np.clip(f[:,:,2] * 0.90, 0, 255)
            return f.astype(np.uint8)
    elif style == "noir":
        def fn(f):
            f = f.astype(np.float32)
            g = f.mean(axis=2, keepdims=True)
            f = np.clip((g * np.ones_like(f) - 128) * 1.45 + 128, 0, 255)
            return f.astype(np.uint8)
    elif style == "vibrant":
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f - 128) * 1.3 + 128, 0, 255)
            g = f.mean(axis=2, keepdims=True)
            f = np.clip(f * 1.15 - g * 0.15, 0, 255)
            return f.astype(np.uint8)
    else:  # sinematik
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f - 128) * 1.2 + 128, 0, 255)
            g = f.mean(axis=2, keepdims=True)
            f = f * 0.85 + g * 0.15
            f[:,:,0] = np.clip(f[:,:,0] * 0.94, 0, 255)
            f[:,:,2] = np.clip(f[:,:,2] * 1.04, 0, 255)
            return f.astype(np.uint8)
    return fn


# ── Render clip ───────────────────────────────────────────────────
def render_clip(
    video_path, start, end, segments, words, *,
    use_subs, sub_style, sub_position, sub_color,
    use_grade, grade_style,
    use_hook, hook_text,
    use_bgm, watermark_path,
    output_name="",
):
    clip  = VideoFileClip(video_path)
    final = clip.subclipped(start, end)

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
        tc = make_tc(h_text, 48, "#FFD700", 3, 3.5, 960)
        if tc:
            layers.append(tc.with_start(0).with_position(("center", 220)))

    if watermark_path and os.path.exists(watermark_path):
        try:
            wm = (ImageClip(watermark_path)
                  .with_effects([vfx.Resize(width=200)])
                  .with_opacity(0.75)
                  .with_duration(final.duration)
                  .with_position((fw - 230, 50)))
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

    safe = re.sub(r"[^\w]", "_", output_name)[:40] if output_name else uuid.uuid4().hex[:8]
    out  = os.path.join(OUTPUT_DIR, f"{safe}.mp4")

    final.write_videofile(
        out, codec="libx264", bitrate="10000k", fps=30, logger=None,
        ffmpeg_params=["-pix_fmt","yuv420p","-profile:v","high","-level","4.1","-movflags","+faststart"],
    )
    clip.close()
    return out


# ════════════════════════════════════════════════════════════════
#  STREAMLIT UI
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="🎬 Film Clipper ID", layout="wide")
st.title("🎬 Film Clipper Indonesia")
st.caption("Upload film → AI deteksi scene terbaik → auto subtitle per kata → crop 9:16 → siap upload TikTok / Reels / Shorts")

with st.sidebar:
    st.header("📂 Upload Film")
    uploaded_film = st.file_uploader("Pilih file film", type=["mp4","mkv","mov"],
                                     help="Film dari ngefilm, filmapik, dll.")
    if uploaded_film is not None:
        sp = os.path.join(INPUT_DIR, uploaded_film.name)
        if not os.path.exists(sp):
            with st.spinner("Menyimpan..."):
                with open(sp, "wb") as fh:
                    fh.write(uploaded_film.read())
            st.success("✅ Tersimpan!")
            st.rerun()
        else:
            st.info("File sudah ada di library.")

    film_files    = sorted(f for f in os.listdir(INPUT_DIR) if f.lower().endswith((".mp4",".mkv",".mov")))
    selected_file = st.selectbox("🎞️ Pilih film", film_files if film_files else ["(belum ada film)"])

    if film_files and st.button("🗑️ Hapus film ini"):
        try:
            os.remove(os.path.join(INPUT_DIR, selected_file))
            st.rerun()
        except Exception:
            pass

    st.divider()
    st.subheader("⚙️ Pengaturan Klip")
    n_clips    = st.slider("Jumlah saran scene", 3, 12, 6)
    min_dur    = st.slider("Durasi min (detik)", 10, 60, 25)
    max_dur    = st.slider("Durasi maks (detik)", 20, 120, 55)
    model_size = st.selectbox("Model Whisper", ["tiny","base","small"], index=0,
                               help="tiny=cepat | base=seimbang | small=akurat")

    st.divider()
    st.subheader("🎨 Color Grading")
    use_grade   = st.checkbox("Aktifkan Color Grading", value=True)
    grade_style = st.selectbox("Gaya", ["sinematik","warm","vibrant","noir"], disabled=not use_grade,
                                help="sinematik=biru dingin | warm=oranye | vibrant=saturasi tinggi | noir=hitam putih")

    st.divider()
    st.subheader("💬 Auto Subtitle")
    use_subs     = st.checkbox("Auto Caption (Voice-to-Text)", value=True)
    sub_style    = st.selectbox("Gaya subtitle",
                                ["🎬 TikTok — per kata, gede", "📝 Kalimat — klasik"],
                                disabled=not use_subs)
    sub_position = st.selectbox("Posisi", ["Bawah","Atas"], disabled=not use_subs)
    sub_color    = st.selectbox("Warna teks", ["white","yellow","#FFD700","#00FFFF"], disabled=not use_subs)

    st.divider()
    st.subheader("🎣 Hook & BGM")
    use_hook    = st.checkbox("Hook Text (3 detik pertama)", value=True)
    custom_hook = st.text_input("Custom hook (kosong = auto)")
    use_bgm     = st.checkbox("Background Music", value=False)
    bgm_upload  = st.file_uploader("Upload BGM (.mp3)", type=["mp3"])
    if bgm_upload is not None:
        with open(BGM_PATH, "wb") as fh:
            fh.write(bgm_upload.read())
        st.success("✅ BGM tersimpan!")
    st.caption("🎵 BGM aktif" if os.path.exists(BGM_PATH) else "Belum ada BGM")

    st.divider()
    st.subheader("🖼️ Watermark")
    wm_upload = st.file_uploader("Upload logo (PNG transparan)", type=["png","jpg","jpeg"])
    if wm_upload is not None:
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


# ── Main ──────────────────────────────────────────────────────────
watermark_path = st.session_state.get("watermark")

if not film_files or selected_file == "(belum ada film)":
    st.info("👈 Upload film dulu lewat sidebar untuk mulai.")
    st.stop()

video_path = os.path.join(INPUT_DIR, selected_file)

col_vid, col_info = st.columns([3, 1])
with col_vid:
    st.video(video_path)
with col_info:
    try:
        _ci  = VideoFileClip(video_path)
        _dur = int(_ci.duration)
        _ci.close()
        st.metric("⏱️ Durasi", f"{_dur//60}m {_dur%60}s")
        st.metric("💾 Ukuran", f"{os.path.getsize(video_path)/1_048_576:.0f} MB")
    except Exception:
        pass
    st.metric("🖼️ WM",   "✅ Ada" if watermark_path else "❌ Belum")
    st.metric("🔤 Font", "✅ OK"  if FONT_PATH      else "⚠️ Tidak ada")

st.markdown("---")

if st.button("🔍 Analisis & Sarankan Scene Terbaik", type="primary", use_container_width=True):
    with st.spinner("AI menganalisis audio + transkripsi word-by-word..."):
        suggestions, segs, words, hashtags = analyze_and_suggest_clips(
            video_path, n_clips, min_dur, max_dur, model_size
        )
    st.session_state.update({
        "suggestions": suggestions, "segs": segs,
        "words": words, "hashtags": hashtags,
        "active_video": video_path,
    })
    st.rerun()

# ── Hasil ─────────────────────────────────────────────────────────
if "suggestions" in st.session_state and st.session_state.get("active_video") == video_path:
    suggestions = st.session_state["suggestions"]
    segs        = st.session_state["segs"]
    words       = st.session_state["words"]
    hashtags    = st.session_state["hashtags"]

    # Caption & Hashtag
    if hashtags and not hashtags.startswith("ERROR"):
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
                    st.session_state["hashtags"] = generate_hashtags(segs, selected_file)
                    st.rerun()

    # Preview transkripsi
    if words:
        with st.expander(f"🔤 Preview Transkripsi — {len(words)} kata ({len(segs)} segmen)", expanded=False):
            col_a, col_b = st.columns(2)
            col_a.caption("**50 kata pertama + timing:**")
            col_a.markdown("  ".join(f"`{w['word']}` _{w['start']:.1f}s_" for w in words[:50])
                           + (" …" if len(words) > 50 else ""))
            col_b.caption("**Full teks:**")
            full_txt = " ".join(s["text"] for s in segs)
            col_b.caption(full_txt[:600] + ("…" if len(full_txt) > 600 else ""))

    st.markdown("---")
    st.subheader(f"🎯 {len(suggestions)} Scene Terbaik")

    if not suggestions:
        st.warning("Tidak ada scene ditemukan. Coba kurangi durasi minimum atau cek apakah video valid.")
    else:
        # Render ALL
        if len(suggestions) > 1 and st.button("🚀 Render SEMUA Scene Sekaligus", use_container_width=True):
            prog = st.progress(0, text="Memulai...")
            for idx, sug in enumerate(suggestions):
                prog.progress(idx / len(suggestions), text=f"Rendering scene #{idx+1}...")
                try:
                    render_clip(
                        video_path, sug["start"], sug["end"], segs, words,
                        use_subs=use_subs, sub_style=sub_style,
                        sub_position=sub_position, sub_color=sub_color,
                        use_grade=use_grade, grade_style=grade_style,
                        use_hook=use_hook, hook_text=custom_hook,
                        use_bgm=use_bgm, watermark_path=watermark_path,
                        output_name=f"{os.path.splitext(selected_file)[0]}_scene{idx+1}",
                    )
                except Exception as e:
                    st.warning(f"Scene #{idx+1} gagal: {e}")
            prog.progress(1.0, text="✅ Semua selesai!")
            st.balloons()
            st.rerun()

        # Tiap scene
        for i, sug in enumerate(suggestions):
            score_pct = int(sug["score"] * 100)
            stars     = "⭐" * min(5, max(1, int(score_pct / 20)))
            with st.expander(f"**Scene #{i+1}** — {sug['label']} | {stars} Skor: {score_pct}%", expanded=(i==0)):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("⏱️ Durasi",   f"{int(sug['end']-sug['start'])}s")
                c2.metric("🔥 Keywords", sug["keywords"])
                c3.metric("🔊 Energi",   f"{int(sug['energy']*100)}%")
                c4.metric("📊 Skor",     f"{score_pct}%")
                if sug["preview"] != "—":
                    st.info(f'💬 *"{sug["preview"]}"*')
                if st.button(f"🚀 Render Scene #{i+1}", key=f"render_{i}", use_container_width=True):
                    with st.spinner(f"Rendering scene #{i+1}..."):
                        try:
                            render_clip(
                                video_path, sug["start"], sug["end"], segs, words,
                                use_subs=use_subs, sub_style=sub_style,
                                sub_position=sub_position, sub_color=sub_color,
                                use_grade=use_grade, grade_style=grade_style,
                                use_hook=use_hook, hook_text=custom_hook,
                                use_bgm=use_bgm, watermark_path=watermark_path,
                                output_name=f"{os.path.splitext(selected_file)[0]}_scene{i+1}",
                            )
                            st.success("✅ Selesai! Cek gallery di bawah.")
                            st.balloons()
                        except Exception as e:
                            st.error(f"Render gagal: {e}")

        # Manual override
        st.markdown("---")
        with st.expander("✏️ Potong Manual"):
            try:
                _ci2  = VideoFileClip(video_path)
                _dur2 = _ci2.duration
                _ci2.close()
            except Exception:
                _dur2 = 3600.0
            col_ms, col_me = st.columns(2)
            m_s    = col_ms.number_input("▶ Start (detik)", 0.0, _dur2, 0.0, step=1.0, key="ms")
            m_e    = col_me.number_input("⏹ End (detik)",   0.0, _dur2, min(_dur2, 60.0), step=1.0, key="me")
            m_name = st.text_input("Nama output (opsional)", placeholder="misal: scene_joget_lucu")
            if st.button("🚀 Render Manual", use_container_width=True):
                if m_e <= m_s:
                    st.error("End harus lebih besar dari Start!")
                else:
                    with st.spinner("Rendering..."):
                        try:
                            render_clip(
                                video_path, m_s, m_e, segs, words,
                                use_subs=use_subs, sub_style=sub_style,
                                sub_position=sub_position, sub_color=sub_color,
                                use_grade=use_grade, grade_style=grade_style,
                                use_hook=use_hook, hook_text=custom_hook,
                                use_bgm=use_bgm, watermark_path=watermark_path,
                                output_name=m_name.strip() or f"{os.path.splitext(selected_file)[0]}_manual",
                            )
                            st.success("✅ Selesai!")
                        except Exception as e:
                            st.error(f"Render gagal: {e}")


# ── Output Gallery ────────────────────────────────────────────────
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
            try:
                os.remove(os.path.join(OUTPUT_DIR, f))
            except Exception:
                pass
        st.rerun()
    for f in output_files:
        fpath   = os.path.join(OUTPUT_DIR, f)
        size_mb = os.path.getsize(fpath) / 1_048_576
        st.write(f"🎞️ **{f}** — {size_mb:.1f} MB")
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.video(fpath)
        with open(fpath, "rb") as fh:
            c2.download_button("⬇️ Download", fh, file_name=f, mime="video/mp4",
                               key=f"dl_{f}", use_container_width=True)
        if c3.button("🗑️ Hapus", key=f"del_{f}", use_container_width=True):
            os.remove(fpath)
            st.rerun()
