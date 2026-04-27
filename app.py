import streamlit as st
from moviepy import VideoFileClip, TextClip, ImageClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
import moviepy.video.fx as vfx
import moviepy.audio.fx as afx
import os, glob, uuid, json
import numpy as np
import yt_dlp
from faster_whisper import WhisperModel

os.environ["PATH"] += os.pathsep + os.getcwd()

# ── FIX: pakai /tmp biar bisa nulis di Streamlit Cloud ──────────
INPUT_DIR = "/tmp/input"
OUTPUT_DIR = "/tmp/output"
WM_DIR = "/tmp/watermark"
BGM_PATH  = "/tmp/horror_bgm.mp3"
BGM_URL   = "https://www.youtube.com/watch?v=J-u8tF4s02c"

for folder in [INPUT_DIR, OUTPUT_DIR, WM_DIR]:
    if not os.path.exists(folder): os.makedirs(folder)

# ── Font resolver ───────────────────────────────────────────────
FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    # Linux (Streamlit Cloud)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_PATH = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
if FONT_PATH is None:
    for search_dir in ["C:/Windows/Fonts", "/usr/share/fonts"]:
        ttf = glob.glob(f"{search_dir}/**/*.ttf", recursive=True)
        if ttf:
            FONT_PATH = ttf[0]
            break

HORROR_KEYWORDS = [
    "tiba-tiba","bayangan","hantu","setan","pocong","kuntilanak","suara",
    "malam","gelap","takut","lari","teriak","pintu","ketuk","langkah",
    "muncul","hilang","aneh","mistis","gaib","penampakan","meninggal",
    "mati","darah","jeritan","menangis","berbisik","panas","dingin",
    "ghost","shadow","suddenly","scream","blood","dark","fear","run",
    "spirit","apparition","haunted","strange","disappeared","appeared",
]

# ── yt-dlp options helper (biar gampang di-reuse) ───────────────
def get_ydl_opts(extra=None):
    """Base yt-dlp options yang aman buat Streamlit Cloud."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_retries": 3,
        "socket_timeout": 30,
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


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════
def generate_hashtags(segments, video_name, api_key=None):
    import re
    from collections import Counter

    STOPWORDS = {
        "yang","dan","di","ke","dari","ini","itu","dengan","untuk","ada","tidak","juga",
        "saya","aku","kamu","dia","kami","kita","mereka","nya","pun","lah","kah","ya",
        "tapi","atau","karena","kalau","jika","maka","saat","waktu","sudah","akan","bisa",
        "ada","adalah","pada","dalam","oleh","setelah","sebelum","ketika","seperti","buat",
        "lagi","masih","sudah","belum","baru","sangat","sekali","lebih","terus","punya",
        "the","a","an","is","are","was","were","be","been","have","has","had","do","does",
        "did","will","would","could","should","may","might","shall","can","need","dare",
        "i","you","he","she","we","they","it","me","him","her","us","them","my","your",
        "his","her","our","their","this","that","these","those","here","there","then",
        "when","where","who","what","how","why","which","and","but","or","so","if","as",
        "at","by","for","in","of","on","to","up","out","go","get","got","said","just",
        "gua","gue","lo","lu","ga","gak","nggak","udah","aja","sama","jadi","tuh","nih",
        "emang","kayak","bener","banget","dong","deh","sih","lho","wah","eh","oh","ah",
        "tau","mau","baik","pagi","sore","malam","hari","kali","orang","tempat","hal",
        "dua","tiga","satu","lima","banyak","semua","semuanya","namanya","namun","tetap",
    }

    if not segments:
        raw = os.path.splitext(video_name)[0]
        words = re.findall(r"[a-zA-Z]{4,}", raw.lower())
        base_tags = ["#" + w for w in words if w not in STOPWORDS]
    else:
        full_text = " ".join(s["text"] for s in segments)
        all_words = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", full_text)
        lower_words = [w.lower() for w in all_words]

        freq = Counter(w for w in lower_words if w not in STOPWORDS)

        specific = [w for w, c in freq.items() if 2 <= c <= 8 and len(w) >= 5]
        specific = sorted(specific, key=lambda w: freq[w], reverse=True)[:8]

        horror_found = [kw.replace("-","") for kw in HORROR_KEYWORDS
                        if kw.replace("-","") in freq or kw in full_text.lower()]
        horror_found = list(dict.fromkeys(horror_found))[:8]

        common = [w for w, c in freq.most_common(30)
                  if w not in STOPWORDS and len(w) >= 5
                  and w not in specific and w not in horror_found][:6]

        universal = [
            "horrortiktok","hororindonesia","ceritahoror","kisahnyata",
            "mistis","horor","horror","fyp","fypシ","viral",
            "penelusuran","pengalamanseram","ghoststory","paranormal",
        ]

        all_tags = []
        for w in specific:    all_tags.append("#" + w)
        for w in horror_found: all_tags.append("#" + w)
        for w in common:      all_tags.append("#" + w)
        for w in universal:   all_tags.append("#" + w)

        seen = set()
        base_tags = []
        for t in all_tags:
            if t not in seen:
                seen.add(t)
                base_tags.append(t)

    return " ".join(base_tags[:28])


def analyze_and_suggest_clips(video_path, n_clips, min_dur, max_dur, api_key):
    import librosa
    status = st.empty()

    status.info("🔍 Menganalisis audio...")
    clip = VideoFileClip(video_path)
    tmp  = f"/tmp/tmp_{uuid.uuid4().hex[:6]}.wav"
    clip.audio.write_audiofile(tmp, logger=None)
    clip.close()
    y, sr    = librosa.load(tmp, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    os.remove(tmp)

    hop      = sr * 2
    rms      = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_norm = (rms - rms.min()) / (rms.max() - rms.min() + 1e-9)
    times    = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    cache_key = f"transcript_{os.path.getsize(video_path)}_{os.path.basename(video_path)}"
    if cache_key in st.session_state:
        status.info("⚡ Transkrip dari cache, skip transkripsi...")
        segments = st.session_state[cache_key]
    else:
        status.info("🤖 Transkripsi AI berjalan...")
        model    = WhisperModel("tiny", device="cpu", compute_type="int8")
        raw, _   = model.transcribe(video_path, language="id", beam_size=1, vad_filter=True)
        segments = [{"start": s.start, "end": s.end, "text": s.text} for s in raw]
        st.session_state[cache_key] = segments

    candidates = []
    for start in np.arange(0, duration - min_dur, 15):
        end = min(start + np.random.randint(min_dur, max_dur + 1), duration)
        if end - start < min_dur: continue
        mask         = (times >= start) & (times <= end)
        energy_score = float(rms_norm[mask].mean()) if mask.any() else 0
        spike_score  = float(rms_norm[mask].std())  if mask.any() else 0
        kw_score, preview = 0, ""
        for seg in segments:
            if seg["end"] < start or seg["start"] > end: continue
            hits = sum(1 for kw in HORROR_KEYWORDS if kw in seg["text"].lower())
            kw_score += hits
            if not preview and hits > 0: preview = seg["text"].strip()
        total = (energy_score * 0.3) + (min(kw_score, 10) / 10 * 0.5) + (spike_score * 0.2)
        candidates.append({
            "start": float(start), "end": float(end), "score": total,
            "energy": energy_score, "keywords": kw_score,
            "preview": preview or "...",
            "label": f"{int(start//60):02d}:{int(start%60):02d} - {int(end//60):02d}:{int(end%60):02d}"
        })

    candidates.sort(key=lambda x: -x["score"])
    selected = []
    for c in candidates:
        if not any(min(c["end"],s["end"]) - max(c["start"],s["start"]) > (c["end"]-c["start"])*0.5 for s in selected):
            selected.append(c)
        if len(selected) >= n_clips: break

    status.info("✨ Generating hashtags dari transkrip...")
    try:
        hashtags = generate_hashtags(segments, os.path.basename(video_path))
    except Exception as e:
        hashtags = f"ERROR: {e}"

    status.empty()
    return selected, segments, hashtags


def render_clip(video_path, start, end, segments, use_subs, use_bgm, watermark_path=None, use_hook=True, use_grade=True, hook_text=''):
    clip  = VideoFileClip(video_path)
    final = clip.subclipped(start, end)

    w, h  = final.size
    final = final.with_effects([
        vfx.Crop(x_center=w/2, width=h*(9/16), height=h),
        vfx.Resize(height=1920)
    ])
    fw, fh = final.size

    if use_grade:
        def horror_grade(frame):
            f = frame.astype(np.float32)
            f = np.clip((f - 128) * 1.25 + 128, 0, 255)
            gray = f.mean(axis=2, keepdims=True)
            f = f * 0.80 + gray * 0.20
            f[:,:,0] = np.clip(f[:,:,0] * 0.92, 0, 255)
            f[:,:,2] = np.clip(f[:,:,2] * 1.05, 0, 255)
            return f.astype(np.uint8)
        final = final.image_transform(horror_grade)

    layers = [final]

    if use_subs and segments and FONT_PATH:
        for seg in segments:
            s0 = max(seg["start"] - start, 0)
            s1 = min(seg["end"]   - start, end - start)
            if s1 <= 0 or s0 >= (end - start) or (s1 - s0) <= 0: continue
            txt = (
                TextClip(
                    text=seg["text"], font_size=42, color="white",
                    font=FONT_PATH, stroke_color="black", stroke_width=2,
                    size=(980, None), method="caption", duration=s1 - s0
                )
                .with_start(s0)
                .with_position(("center", 1540))
            )
            layers.append(txt)

    if use_hook and FONT_PATH:
        import random
        HOOK_POOL = [
            "Tonton sampai habis, kalau berani...",
            "Pasang headset. Jangan tonton sendirian.",
            "Video ini bikin orang ga bisa tidur.",
            "Ini bukan fiksi. Ini pengalaman nyata.",
            "Satu orang udah kabur sebelum selesai nonton.",
            "Suara di menit terakhir bikin bulu kuduk berdiri.",
        ]
        h_text = hook_text.strip() if hook_text.strip() else random.choice(HOOK_POOL)
        hook = (
            TextClip(
                text=h_text, font_size=46, color="red",
                font=FONT_PATH, stroke_color="black", stroke_width=3,
                size=(960, None), method="caption", duration=3.0
            )
            .with_start(0)
            .with_position(("center", 280))
        )
        layers.append(hook)

    if watermark_path and os.path.exists(watermark_path):
        wm = (
            ImageClip(watermark_path)
            .with_effects([vfx.Resize(width=220)])
            .with_opacity(0.75)
            .with_duration(final.duration)
            .with_position((fw - 220 - 30, 60))
        )
        layers.append(wm)

    if len(layers) > 1:
        final = CompositeVideoClip(layers)

    if use_bgm and os.path.exists(BGM_PATH):
        bgm   = AudioFileClip(BGM_PATH).with_effects([afx.MultiplyVolume(0.15)]).with_duration(final.duration)
        final = final.with_audio(CompositeAudioClip([final.audio, bgm]))

    out = f"{OUTPUT_DIR}/klip_{uuid.uuid4().hex[:6]}.mp4"
    final.write_videofile(
        out,
        codec="libx264",
        bitrate="15000k",
        fps=30,
        ffmpeg_params=[
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-level", "4.1",
            "-movflags", "+faststart"
        ]
    )
    clip.close()
    return out


# ══════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════
st.set_page_config(page_title="Horror Clip Master", layout="wide")
st.title("✂️ Horror Clip Master")

# ── sources.json juga di /tmp ───────────────────────────────────
SOURCES_FILE = "/tmp/sources.json"

with st.sidebar:
    st.header("📥 Download Video")
    yt_url = st.text_input("Link YouTube / Podcast")
    if st.button("⬇️ Download"):
        if yt_url:
            dl_status = st.empty()

            # Step 1: Ambil info video dulu (tanpa download)
            dl_status.info("📡 Mengambil info video...")
            try:
                with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl_info:
                    info      = ydl_info.extract_info(yt_url, download=False)
                    vid_title = info.get("title", "Unknown")
                    vid_dur   = info.get("duration", 0)
                    dl_status.info(f"✅ Judul: **{vid_title}** | Durasi: {int(vid_dur//60)}m {int(vid_dur%60)}s")
            except Exception as e:
                dl_status.error(f"❌ Gagal ambil info video: {e}")
                st.stop()

            # Step 2: Download video
            dl_status.info("⬇️ Mendownload video...")
            try:
                with yt_dlp.YoutubeDL(get_ydl_opts({
                    "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
                    "outtmpl": f"{INPUT_DIR}/%(title)s.%(ext)s",
                    "merge_output_format": "mp4",
                })) as ydl:
                    ydl.download([yt_url])
            except Exception as e:
                dl_status.error(f"❌ Gagal download: {e}")
                st.stop()

            # Simpan mapping judul → URL ke /tmp/sources.json
            sources = {}
            if os.path.exists(SOURCES_FILE):
                with open(SOURCES_FILE) as sf:
                    try:
                        sources = json.load(sf)
                    except Exception:
                        sources = {}
            sources[vid_title] = yt_url
            with open(SOURCES_FILE, "w") as sf:
                json.dump(sources, sf, indent=2, ensure_ascii=False)

            # Step 3: Cari file yang baru didownload
            all_vids = sorted(
                [f for f in os.listdir(INPUT_DIR) if f.lower().endswith((".mp4",".mov",".mkv"))],
                key=lambda f: os.path.getmtime(os.path.join(INPUT_DIR, f)),
                reverse=True
            )
            new_vid_path = os.path.join(INPUT_DIR, all_vids[0]) if all_vids else None

            # Step 4: Auto transkripsi
            if new_vid_path:
                dl_status.info("🤖 Auto transkripsi berjalan (faster-whisper)...")
                try:
                    model    = WhisperModel("small", device="cpu", compute_type="int8")
                    raw, _   = model.transcribe(new_vid_path, language="id", beam_size=1, vad_filter=True)
                    segments = [{"start": s.start, "end": s.end, "text": s.text} for s in raw]
                    cache_key = f"transcript_{os.path.getsize(new_vid_path)}_{os.path.basename(new_vid_path)}"
                    st.session_state[cache_key] = segments
                    dl_status.success(f"✅ Download & transkripsi selesai! ({len(segments)} segmen)")
                except Exception as e:
                    dl_status.warning(f"Download OK, transkripsi gagal: {e}")
            else:
                dl_status.success("✅ Download selesai!")

            st.rerun()

    st.divider()
    if st.button("🎵 Download BGM Horror"):
        with st.spinner("Mengunduh BGM..."):
            try:
                with yt_dlp.YoutubeDL(get_ydl_opts({
                    "format": "bestaudio",
                    "outtmpl": BGM_PATH.replace(".mp3", ""),
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
                })) as ydl:
                    ydl.download([BGM_URL])
                st.success("BGM siap!")
            except Exception as e:
                st.error(f"Gagal download BGM: {e}")

    st.divider()

    st.subheader("🖼️ Watermark")
    wm_upload = st.file_uploader("Upload logo/watermark (PNG transparan disarankan)",
                                  type=["png","jpg","jpeg"])
    if wm_upload:
        wm_save_path = os.path.join(WM_DIR, wm_upload.name)
        with open(wm_save_path, "wb") as f:
            f.write(wm_upload.read())
        st.session_state["watermark"] = wm_save_path
        st.success(f"✅ {wm_upload.name} siap dipakai")
        st.rerun()

    wm_files = [f for f in os.listdir(WM_DIR) if f.lower().endswith((".png",".jpg",".jpeg"))]
    if wm_files:
        chosen_wm = st.selectbox("Pilih watermark aktif", ["(tidak pakai)"] + wm_files)
        if chosen_wm != "(tidak pakai)":
            st.session_state["watermark"] = os.path.join(WM_DIR, chosen_wm)
        else:
            st.session_state["watermark"] = None
    else:
        st.caption("Belum ada watermark diupload.")
        st.session_state.setdefault("watermark", None)

    st.divider()
    files         = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith((".mp4",".mov",".mkv"))]
    selected_file = st.selectbox("Pilih Video", files if files else ["(belum ada video)"])

    st.divider()
    st.subheader("⚙️ Pengaturan")
    n_clips  = st.slider("Jumlah saran klip", 3, 10, 5)
    min_dur  = st.slider("Durasi min (detik)", 20, 60, 30)
    max_dur  = st.slider("Durasi maks (detik)", 45, 180, 90)
    use_subs     = st.checkbox("Auto Subtitle", value=True)
    use_bgm      = st.checkbox("BGM Horror", value=True)
    use_hook     = st.checkbox("Hook Text (0-3 detik)", value=True)
    use_grade    = st.checkbox("Color Grading Horror", value=True)
    custom_hook  = st.text_input("Custom hook text (kosongkan = auto)", placeholder="Tulis hook sendiri...")


# ── Main ───────────────────────────────────────────────────────
if selected_file and selected_file != "(belum ada video)":
    video_path    = os.path.join(INPUT_DIR, selected_file)
    watermark_path = st.session_state.get("watermark")

    st.video(video_path)
    st.markdown("---")

    if st.button("🔍 Analisis & Sarankan Klip Terbaik", type="primary", use_container_width=True):
        with st.spinner("Menganalisis video..."):
            suggestions, whisper_segs, hashtags = analyze_and_suggest_clips(
                video_path, n_clips, min_dur, max_dur, None
            )
            st.session_state["suggestions"]  = suggestions
            st.session_state["whisper_segs"] = whisper_segs
            st.session_state["video_path"]   = video_path
            if hashtags:
                st.session_state["last_hashtags"] = hashtags

    if "suggestions" in st.session_state and st.session_state.get("video_path") == video_path:
        suggestions  = st.session_state["suggestions"]
        whisper_segs = st.session_state["whisper_segs"]

        if "last_hashtags" in st.session_state:
            ht = st.session_state["last_hashtags"]
            if ht.startswith("ERROR:"):
                st.warning(f"Hashtag gagal: {ht}")
            else:
                sources = {}
                if os.path.exists(SOURCES_FILE):
                    with open(SOURCES_FILE) as sf:
                        try:
                            sources = json.load(sf)
                        except Exception:
                            sources = {}

                src_url = ""
                for title, url in sources.items():
                    if title.lower() in selected_file.lower() or selected_file.lower().startswith(title[:20].lower()):
                        src_url = url
                        break

                segs_preview = whisper_segs[:5] if whisper_segs else []
                opening_line = segs_preview[0]["text"].strip() if segs_preview else ""
                caption_lines = []
                if opening_line:
                    caption_lines.append("🎙️ \"" + opening_line[:80] + "...\"")
                caption_lines.append("")
                caption_lines.append(ht)
                if src_url:
                    caption_lines.append("")
                    caption_lines.append(f"🎧 Sumber lengkap: {src_url}")
                full_caption = "\n".join(caption_lines)
                st.session_state["last_caption"] = full_caption

                with st.container(border=True):
                    tab1, tab2, tab3 = st.tabs(["📋 Caption TikTok", "# Hashtags", "🔗 Sumber Video"])

                    with tab1:
                        st.caption("Caption siap pakai — termasuk opening line, hashtag, dan link sumber.")
                        st.text_area("Caption", full_caption, height=200, label_visibility="collapsed")

                    with tab2:
                        st.caption("Hashtag aja kalau mau pisah.")
                        st.text_area("Hashtags", ht, height=110, label_visibility="collapsed")
                        tags    = [t for t in ht.split() if t.startswith("#")]
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total", len(tags))
                        id_tags = [t for t in tags if any(c in t.lower() for c in "aiueo")]
                        c2.metric("🇮🇩 Indonesia", len(id_tags))
                        c3.metric("🌐 Global", len(tags) - len(id_tags))
                        if st.button("🔄 Generate Ulang Hashtags"):
                            with st.spinner("Generating..."):
                                new_ht = generate_hashtags(whisper_segs, selected_file)
                                st.session_state["last_hashtags"] = new_ht
                                st.rerun()

                    with tab3:
                        st.caption("Link YouTube sumber video ini.")
                        if src_url:
                            st.text_input("🔗 Link Sumber", src_url, label_visibility="collapsed")
                            st.markdown(f"[▶ Buka di YouTube]({src_url})")
                        else:
                            st.info("Link sumber tidak ditemukan. Pastikan video didownload lewat tombol Download di sidebar.")

                        if sources:
                            st.markdown("**Semua sumber yang pernah didownload:**")
                            for title, url in sources.items():
                                st.markdown(f"- [{title[:50]}...]({url})")

        st.markdown("---")
        st.subheader(f"🎯 {len(suggestions)} Klip Terbaik")

        for i, sug in enumerate(suggestions):
            score_pct = int(sug["score"] * 100)
            stars     = "⭐" * min(5, max(1, int(score_pct / 20)))
            with st.expander(f"**Klip #{i+1}** — {sug['label']} | {stars} Skor: {score_pct}%", expanded=(i==0)):
                c1, c2, c3 = st.columns(3)
                c1.metric("⏱️ Durasi", f"{int(sug['end']-sug['start'])}s")
                c2.metric("🔑 Keywords", sug["keywords"])
                c3.metric("🔊 Energi", f"{int(sug['energy']*100)}%")
                st.info(f"💬 *\"{sug['preview']}\"*")

                wm_label = f"✅ Watermark: {os.path.basename(watermark_path)}" if watermark_path else "❌ Watermark belum diupload"
                st.caption(wm_label)

                if st.button(f"🚀 Render Klip #{i+1}", key=f"render_{i}", use_container_width=True):
                    with st.spinner(f"Rendering klip #{i+1}..."):
                        out = render_clip(video_path, sug["start"], sug["end"],
                                          whisper_segs, use_subs, use_bgm, watermark_path,
                                          use_hook=use_hook, use_grade=use_grade,
                                          hook_text=custom_hook)
                    st.success(f"✅ Selesai! `{out}`")
                    st.balloons()

        st.markdown("---")
        with st.expander("✏️ Manual Override"):
            ci  = VideoFileClip(video_path)
            m_s = st.number_input("Start (detik)", 0.0, ci.duration, 0.0, key="ms")
            m_e = st.number_input("End (detik)",   0.0, ci.duration, min(ci.duration, 60.0), key="me")
            ci.close()
            if st.button("🚀 Render Manual", use_container_width=True):
                with st.spinner("Rendering..."):
                    out = render_clip(video_path, m_s, m_e, whisper_segs, use_subs, use_bgm, watermark_path,
                                      use_hook=use_hook, use_grade=use_grade, hook_text=custom_hook)
                st.success(f"✅ `{out}`")


# ── Output gallery ──────────────────────────────────────────────
st.markdown("---")
st.subheader("📁 Hasil Klip")
output_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".mp4")]
if output_files:
    for f in output_files:
        fpath = os.path.join(OUTPUT_DIR, f)
        st.write(f"🎞️ {f}")
        c1, c2, c3 = st.columns([2, 1, 1])
        c1.video(fpath)
        with open(fpath, "rb") as fobj:
            c2.download_button(
                "⬇️ Download", fobj, file_name=f,
                mime="video/mp4", key=f"dl_{f}"
            )
        if c3.button("🗑️ Hapus", key=f"del_{f}"):
            os.remove(fpath)
            st.rerun()
else:
    st.caption("Belum ada klip yang dirender.")
