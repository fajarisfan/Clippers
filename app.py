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

_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibrib.ttf", "C:/Windows/Fonts/seguibl.ttf",
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

FYP_WINDOWS = [
    {"label": "Pagi Aktif",      "range": (6,  9),  "desc": "Orang buka HP setelah bangun tidur"},
    {"label": "Istirahat Siang", "range": (11, 13), "desc": "Jam makan siang, scrolling santai"},
    {"label": "Sore Nongkrong",  "range": (15, 17), "desc": "Pulang kerja/sekolah, engagement tinggi"},
    {"label": "Prime Time",      "range": (19, 22), "desc": "JAM EMAS — traffic tertinggi TikTok/Reels"},
    {"label": "Late Night",      "range": (22, 24), "desc": "Niche audience, engagement loyal"},
]

def get_fyp_status():
    wib    = pytz.timezone("Asia/Jakarta")
    now    = datetime.now(wib)
    hour   = now.hour
    minute = now.minute
    current_window  = None
    next_window     = None
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
    return {"now": now, "hour": hour, "current_window": current_window,
            "next_window": next_window, "minutes_to_next": minutes_to_next}

EMOTION_LEXICON = {
    "ngakak":("komedi",5),"wkwkwk":("komedi",5),"hahaha":("komedi",4),"ketawa":("komedi",4),
    "lucu":("komedi",4),"gokil":("komedi",4),"receh":("komedi",3),"kocak":("komedi",4),
    "bercanda":("komedi",3),"lelucon":("komedi",3),"humor":("komedi",3),"lawak":("komedi",3),
    "absurd":("komedi",3),"geli":("komedi",3),"ngikik":("komedi",4),"ngenes":("komedi",3),
    "lebay":("komedi",3),"alay":("komedi",2),"jayus":("komedi",3),"awkward":("komedi",3),
    "parah":("komedi",3),"gilaa":("komedi",4),"gila":("komedi",3),"anjir":("komedi",4),
    "anjay":("komedi",4),"astaga":("komedi",3),
    "hantu":("horror",5),"setan":("horror",5),"pocong":("horror",5),"kuntilanak":("horror",5),
    "gendruwo":("horror",5),"tuyul":("horror",4),"arwah":("horror",5),"roh":("horror",4),
    "mistis":("horror",4),"kesurupan":("horror",5),"santet":("horror",5),"teluh":("horror",5),
    "pelet":("horror",4),"dukun":("horror",4),"pesugihan":("horror",5),"serem":("horror",4),
    "ngeri":("horror",4),"merinding":("horror",5),"takut":("horror",3),"ketakutan":("horror",4),
    "horor":("horror",4),"gelap":("horror",2),"malam":("horror",2),"kuburan":("horror",4),
    "mayat":("horror",4),"mati":("horror",3),"kematian":("horror",4),"terkutuk":("horror",5),
    "ritual":("horror",4),"gaib":("horror",4),"supranatural":("horror",4),"paranormal":("horror",4),
    "makhluk":("horror",3),"penampakan":("horror",5),"gangguan":("horror",3),
    "kaget":("kaget",5),"syok":("kaget",5),"terkejut":("kaget",4),"shock":("kaget",5),
    "ternyata":("kaget",4),"tiba-tiba":("kaget",4),"mendadak":("kaget",4),
    "nggak nyangka":("kaget",5),"gak nyangka":("kaget",5),"lho":("kaget",3),"wah":("kaget",3),
    "eh":("kaget",2),"kok bisa":("kaget",4),"masa":("kaget",3),"beneran":("kaget",3),
    "serius":("kaget",3),"bukan main":("kaget",4),"gila banget":("kaget",5),
    "parah banget":("kaget",5),"nggak percaya":("kaget",5),"gak percaya":("kaget",5),
    "mustahil":("kaget",4),"wtf":("kaget",5),"plot twist":("kaget",5),"twist":("kaget",4),
    "nangis":("haru",5),"terharu":("haru",5),"haru":("haru",4),"menyentuh":("haru",4),
    "touching":("haru",4),"sedih":("haru",4),"baper":("haru",3),"mewek":("haru",4),
    "pilu":("haru",4),"nelangsa":("haru",4),"rindu":("haru",3),"kehilangan":("haru",4),
    "ditinggal":("haru",4),"meninggal":("haru",4),"duka":("haru",4),"bangga":("haru",3),
    "menangis":("haru",5),
    "berantem":("drama",5),"ribut":("drama",4),"konflik":("drama",4),"cekcok":("drama",4),
    "debat":("drama",3),"bertengkar":("drama",5),"putus":("drama",4),"cerai":("drama",5),
    "selingkuh":("drama",5),"khianat":("drama",5),"bohong":("drama",4),"tipu":("drama",4),
    "fitnah":("drama",4),"gosip":("drama",4),"skandal":("drama",5),"ketahuan":("drama",5),
    "nyesel":("drama",4),"toxic":("drama",4),"ghosting":("drama",4),"sakit hati":("drama",4),
    "dendam":("drama",4),"marah":("drama",3),"ngamuk":("drama",4),
    "bangkit":("motivasi",4),"berjuang":("motivasi",4),"sukses":("motivasi",3),
    "gagal":("motivasi",3),"mimpi":("motivasi",3),"impian":("motivasi",3),
    "buktikan":("motivasi",4),"pantang menyerah":("motivasi",5),"semangat":("motivasi",3),
    "kuat":("motivasi",3),"optimis":("motivasi",3),"menginspirasi":("motivasi",4),
    "inspirasi":("motivasi",3),"transformasi":("motivasi",4),"hebat":("motivasi",3),
    "faktanya":("fakta",4),"tau nggak":("fakta",4),"tau gak":("fakta",4),
    "gue kira":("fakta",3),"salah kaprah":("fakta",4),"penelitian":("fakta",3),
    "terbukti":("fakta",3),"fakta":("fakta",3),"mitos":("fakta",4),"rahasia":("fakta",4),
    "bocoran":("fakta",5),"bocor":("fakta",4),"tersembunyi":("fakta",4),
    "dirahasiakan":("fakta",5),"terungkap":("fakta",5),"konspirasi":("fakta",4),
    "relate":("reaksi",4),"gue banget":("reaksi",5),"gua banget":("reaksi",5),
    "bener banget":("reaksi",4),"viral":("reaksi",3),"trending":("reaksi",3),
}
VIRAL_KEYWORDS = list(EMOTION_LEXICON.keys())

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
    "terus","gitu","gini","tapi","abis","udah","lagi","aja","itu","ini",
}

HOOK_POOL = [
    "Bagian ini yang paling banyak di-replay...",
    "Tonton sampai habis, ada yang ngena banget.",
    "Ini yang bikin jutaan orang relate.",
    "Momen ini bikin semua orang diam.",
    "Kalimat ini viral di mana-mana.",
    "Jujur banget sampai bikin kaget.",
    "Nonton ini sambil siapin tisu.",
    "Ini alasan podcast ini meledak.",
    "Satu kalimat yang mengubah segalanya.",
    "Semua orang diam setelah dengar ini.",
]

_EJA = {
    "gue":"saya","gua":"saya","lo":"kamu","lu":"kamu","ga":"tidak","gak":"tidak",
    "nggak":"tidak","enggak":"tidak","udah":"sudah","aja":"saja","emang":"memang",
    "kayak":"seperti","banget":"sekali","bener":"benar","gimana":"bagaimana","kalo":"kalau",
    "sampe":"sampai","abis":"habis","tau":"tahu","trus":"terus","ntar":"nanti",
    "btw":"omong-omong","ok":"oke","yep":"ya","nope":"tidak","bikin":"membuat",
    "ngomong":"berbicara","bilang":"mengatakan","ngeliat":"melihat","liat":"melihat",
    "ngerasa":"merasa","nanya":"bertanya","makin":"semakin","cuma":"hanya",
    "wkwk":"(tertawa)","haha":"(tertawa)","lol":"(tertawa)","fyi":"untuk diketahui",
}

def koreksi_ejaan(teks):
    if not teks:
        return teks
    kata_list = teks.split()
    hasil = []
    for kata in kata_list:
        suffix, base = "", kata
        while base and base[-1] in ".,!?;:":
            suffix = base[-1] + suffix
            base   = base[:-1]
        lower = base.lower()
        if lower in _EJA:
            ganti = _EJA[lower]
            if base and base[0].isupper():
                ganti = ganti[0].upper() + ganti[1:]
            hasil.append(ganti + suffix)
        else:
            hasil.append(kata)
    teks_hasil = " ".join(hasil)
    teks_hasil = re.sub(r'([.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), teks_hasil)
    if teks_hasil:
        teks_hasil = teks_hasil[0].upper() + teks_hasil[1:]
    return teks_hasil

def segment_subtitle(teks, maks_char=42):
    kata_list = teks.split()
    baris, baris_saat_ini, panjang_saat_ini = [], [], 0
    for kata in kata_list:
        if panjang_saat_ini + len(kata) + (1 if baris_saat_ini else 0) <= maks_char:
            baris_saat_ini.append(kata)
            panjang_saat_ini += len(kata) + (1 if len(baris_saat_ini) > 1 else 0)
        else:
            if baris_saat_ini:
                baris.append(" ".join(baris_saat_ini))
            baris_saat_ini  = [kata]
            panjang_saat_ini = len(kata)
    if baris_saat_ini:
        baris.append(" ".join(baris_saat_ini))
    hasil = []
    for i in range(0, len(baris), 2):
        hasil.append("\n".join(baris[i:i+2]))
    return hasil

def is_cloud():
    return (os.path.exists("/mount/src") or
            os.environ.get("STREAMLIT_SHARING_MODE") is not None)

IS_CLOUD = is_cloud()

# ── YT-DLP ──────────────────────────────────────────────────────
def _ydl_opts(extra=None):
    opts = {
        "quiet": True, "no_warnings": True,
        "extractor_retries": 3, "socket_timeout": 30,
        "http_headers": {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36")
        },
    }
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    elif not IS_CLOUD:
        browser_dirs = {
            "chrome":  os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data"),
            "edge":    os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\User Data"),
            "brave":   os.path.expanduser(r"~\AppData\Local\BraveSoftware\Brave-Browser\User Data"),
            "firefox": os.path.expanduser(r"~\AppData\Roaming\Mozilla\Firefox"),
        }
        for browser, path in browser_dirs.items():
            if os.path.exists(path):
                opts["cookiesfrombrowser"] = (browser,)
                break
    if extra:
        opts.update(extra)
    return opts

def get_video_info(url):
    opts = _ydl_opts()
    opts.pop("format", None)
    opts.update({"skip_download": True,
                 "youtube_include_dash_manifest": False,
                 "youtube_include_hls_manifest": False})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return info
    except Exception as e:
        err = str(e)
        if "403" in err or "Forbidden" in err:
            raise RuntimeError("YouTube 403 - cookies.txt expired. Export ulang dari Chrome lalu upload di sidebar.")
        raise RuntimeError(err)
    raise RuntimeError("Tidak dapat mengambil info video.")

def get_stream_urls(url):
    format_attempts = [
        "bestvideo[height<=720]+bestaudio",
        "bestvideo[height<=480]+bestaudio",
        "bestvideo+bestaudio",
        "best[height<=720]", "best", None,
    ]
    info, last_err = None, None
    for fmt in format_attempts:
        try:
            extra = {"format": fmt} if fmt else {}
            with yt_dlp.YoutubeDL(_ydl_opts(extra)) as ydl:
                info = ydl.extract_info(url, download=False)
            break
        except Exception as e:
            last_err = e
            continue
    if info is None:
        raise RuntimeError(f"Semua format gagal: {last_err}")
    if "requested_formats" in info:
        v_url = next((f["url"] for f in info["requested_formats"] if f.get("vcodec") != "none"), None)
        a_url = next((f["url"] for f in info["requested_formats"] if f.get("acodec") != "none"), None)
        return v_url or info.get("url",""), a_url or v_url or info.get("url","")
    direct = info.get("url","")
    return direct, direct

def download_audio_only(source_url, duration, max_sec=600):
    out_base = os.path.join(TMP_DIR, f"audio_{uuid.uuid4().hex[:6]}")
    out_wav  = out_base + ".wav"
    limit    = min(duration, max_sec)
    ydl_audio_opts = _ydl_opts({
        "format": "bestaudio/best",
        "outtmpl": out_base + ".%(ext)s",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "0"}],
        "postprocessor_args": {"FFmpegExtractAudio": ["-ar","16000","-ac","1","-t",str(int(limit))]},
    })
    try:
        with yt_dlp.YoutubeDL(ydl_audio_opts) as ydl:
            ydl.download([source_url])
    except Exception as e:
        err = str(e)
        if "403" in err or "Forbidden" in err:
            raise RuntimeError("YouTube 403 — cookies.txt expired. Export ulang lalu upload di sidebar.")
        raise RuntimeError(f"yt-dlp audio download gagal: {e}")
    if not os.path.exists(out_wav):
        candidates = glob.glob(out_base + ".*")
        if not candidates:
            raise RuntimeError("File audio tidak ditemukan setelah download.")
        src = candidates[0]
        if src != out_wav:
            r = subprocess.run(["ffmpeg","-y","-i",src,"-ar","16000","-ac","1",out_wav],
                               capture_output=True, timeout=120)
            try: os.remove(src)
            except Exception: pass
            if r.returncode != 0:
                raise RuntimeError(f"Konversi WAV gagal: {r.stderr.decode()[:200]}")
    if not os.path.exists(out_wav) or os.path.getsize(out_wav) < 1000:
        raise RuntimeError("File audio kosong atau tidak valid.")
    return out_wav

@st.cache_resource
def load_whisper(model_size):
    return WhisperModel(model_size, device="cpu", compute_type="int8")

def transcribe_audio(audio_path, model_size="tiny", koreksi=True):
    model  = load_whisper(model_size)
    raw, _ = model.transcribe(audio_path, beam_size=1, vad_filter=True,
                               word_timestamps=True, language="id")
    segments, words = [], []
    for seg in raw:
        teks = seg.text.strip()
        if koreksi:
            teks = koreksi_ejaan(teks)
        segments.append({"start": seg.start, "end": seg.end, "text": teks})
        if seg.words:
            for w in seg.words:
                wc = w.word.strip()
                if wc:
                    words.append({"start": w.start, "end": w.end,
                                  "word": koreksi_ejaan(wc) if koreksi else wc})
    return segments, words

EMOTION_EMOJI = {
    "komedi":"😂","horror":"👻","kaget":"😱","haru":"😢",
    "drama":"🔥","motivasi":"💪","fakta":"🤯","reaksi":"💬","campuran":"⭐",
}
SCORE_WEIGHTS = {"emosi":0.40,"energi":0.20,"density":0.15,"spike":0.15,"struktur":0.10}

def _scan_emotions(text):
    lower, cat_sc, total_w = text.lower(), {}, 0
    for phrase in sorted(EMOTION_LEXICON, key=len, reverse=True):
        if phrase in lower:
            cat, w = EMOTION_LEXICON[phrase]
            cat_sc[cat] = cat_sc.get(cat, 0) + w
            total_w += w
    return cat_sc, total_w

def _tempo_score(y, sr, t_start, t_end):
    import librosa
    s, e = int(t_start*sr), int(t_end*sr)
    seg  = y[s:e]
    if len(seg) < sr * 0.5:
        return 0.0
    zcr  = float(np.mean(librosa.feature.zero_crossing_rate(seg)))
    rmsv = float(np.std(librosa.feature.rms(y=seg, hop_length=512)[0]))
    return min(1.0, zcr * 5 + rmsv * 20)

def _spike_score(rms_norm, times, t_start, t_end):
    mask  = (times >= t_start) & (times <= t_end)
    chunk = rms_norm[mask]
    if len(chunk) < 3:
        return 0.0
    diff = np.diff(chunk)
    return min(1.0, float(np.sum(diff > 0.25)) * 0.2 + (float(diff.max()) if len(diff) else 0.0))

def _struktur_score(segs_in_window):
    TRANSISI   = ["ternyata","padahal","tapi","karena","jadi","akhirnya","tiba-tiba"]
    PERTANYAAN = ["kenapa","bagaimana","gimana","apa","siapa","kapan","berapa"]
    PENEGASAN  = ["beneran","serius","jujur","percaya","yakin","pasti","memang"]
    PEMBUKA    = ["jadi ceritanya","suatu hari","gue pernah","waktu gue","lo tau gak"]
    skor, gabung = 0.0, " ".join(s["text"].lower() for s in segs_in_window)
    for w in TRANSISI:
        if w in gabung: skor += 0.08
    for w in PERTANYAAN:
        if w in gabung: skor += 0.05
    for w in PENEGASAN:
        if w in gabung: skor += 0.06
    for w in PEMBUKA:
        if w in gabung: skor += 0.12
    return min(1.0, skor)

def score_clips(audio_path, segments, duration, n_clips, min_dur, max_dur, filter_kategori="semua"):
    import librosa
    y, sr  = librosa.load(audio_path, mono=True, sr=None)
    hop    = 512
    rms    = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_n  = (rms - rms.min()) / (rms.max() - rms.min() + 1e-9)
    times  = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    max_t  = min(duration, float(times[-1]) if len(times) else duration)
    step   = max(3, min_dur // 4)
    candidates = []
    for sf in np.arange(0, max_t - min_dur, step):
        ef = min(float(sf) + random.randint(min_dur, max_dur), duration)
        if ef - sf < min_dur:
            continue
        segs_win = [s for s in segments if not (s["end"] < sf or s["start"] > ef)]
        gabung   = " ".join(s["text"] for s in segs_win)
        cat_sc, emosi_raw = _scan_emotions(gabung)
        emosi_norm = min(1.0, emosi_raw / 30.0)
        dom_cat    = max(cat_sc, key=cat_sc.get) if cat_sc else "campuran"
        if filter_kategori != "semua" and dom_cat != filter_kategori:
            continue
        best_preview, best_w = "—", 0
        for seg in segs_win:
            _, w = _scan_emotions(seg["text"])
            if w > best_w:
                best_w       = w
                best_preview = seg["text"]
        mask    = (times >= sf) & (times <= ef)
        e_mean  = float(rms_n[mask].mean()) if mask.any() else 0.0
        density = _tempo_score(y, sr, sf, ef)
        spike   = _spike_score(rms_n, times, sf, ef)
        struktur = _struktur_score(segs_win)
        total = (emosi_norm*SCORE_WEIGHTS["emosi"] + e_mean*SCORE_WEIGHTS["energi"]
                 + density*SCORE_WEIGHTS["density"] + spike*SCORE_WEIGHTS["spike"]
                 + struktur*SCORE_WEIGHTS["struktur"])
        if dom_cat in ("horror","kaget"):   total = min(1.0, total * 1.20)
        elif dom_cat in ("komedi","drama"): total = min(1.0, total * 1.10)
        candidates.append({
            "start":float(sf),"end":float(ef),"score":total,
            "energy":e_mean,"spike":spike,"density":density,"emosi":emosi_norm,
            "struktur":struktur,"kategori":dom_cat,"cat_detail":cat_sc,
            "keywords":emosi_raw,"preview":best_preview.strip(),
            "label":f"{int(sf//60):02d}:{int(sf%60):02d} – {int(ef//60):02d}:{int(ef%60):02d}",
        })
    candidates.sort(key=lambda x: -x["score"])
    selected = []
    for c in candidates:
        if not any(min(c["end"],s["end"])-max(c["start"],s["start"]) > (c["end"]-c["start"])*0.50
                   for s in selected):
            selected.append(c)
        if len(selected) >= n_clips:
            break
    return selected

FYP_CORE_TAGS = ["#fyp","#fypシ","#foryou","#foryoupage","#viral","#trending",
                 "#podcastindonesia","#podcast","#kontenkreatif","#shorts","#reels","#tiktok"]
NICHE_MAP = {
    "motivasi":["#motivasi","#motivasihari","#semangat","#inspirasi","#quotes","#quotesindo"],
    "drama":["#drama","#storytime","#curhat","#cerita","#kisahnyata","#pengalaman"],
    "edukasi":["#edukasi","#belajar","#fakta","#faktaunik","#ilmupengetahuan","#tips"],
    "komedi":["#lucu","#ngakak","#hiburan","#comedy","#receh","#meme"],
    "horror":["#horror","#serem","#mistis","#hantuin","#creepy","#lenteramalam"],
    "bisnis":["#bisnis","#entrepreneur","#usaha","#sukses","#finansial","#investasi"],
    "relationship":["#relationship","#cinta","#pasangan","#toxic","#bucin","#galau"],
}

def detect_niche(segments):
    if not segments: return "motivasi"
    full = " ".join(s["text"] for s in segments)
    cat_sc, _ = _scan_emotions(full)
    if not cat_sc: return "motivasi"
    dom = max(cat_sc, key=cat_sc.get)
    return {"komedi":"komedi","horror":"horror","kaget":"kaget","haru":"drama",
            "drama":"drama","motivasi":"motivasi","fakta":"edukasi","reaksi":"motivasi"}.get(dom,"motivasi")

def generate_hashtags(segments, title):
    title_words = re.findall(r"[a-zA-Z0-9]{3,}", title)
    title_tags  = ["#"+w.lower() for w in title_words if w.lower() not in STOPWORDS and len(w)>=3][:5]
    niche       = detect_niche(segments)
    niche_tags  = NICHE_MAP.get(niche, [])
    specific_tags = []
    if segments:
        full_text   = " ".join(s["text"] for s in segments)
        lower_words = [w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", full_text)]
        freq        = Counter(w for w in lower_words if w not in STOPWORDS)
        specific    = sorted([w for w,c in freq.items() if 2<=c<=8 and len(w)>=5],
                             key=lambda w: freq[w], reverse=True)[:4]
        specific_tags = ["#"+w for w in specific]
    all_tags = FYP_CORE_TAGS + niche_tags + title_tags + specific_tags
    seen, final = set(), []
    for t in all_tags:
        if t not in seen:
            seen.add(t)
            final.append(t)
    return " ".join(final[:30])

def generate_caption_fyp(segments, title, url, fyp_info):
    hashtags = generate_hashtags(segments, title)
    hook = f'🎙️ "{segments[0]["text"][:80]}..."' if segments else f'🎙️ {title}'
    cw   = fyp_info.get("current_window")
    if cw and "Prime Time" in cw["label"]:   cta = "⭐ Tonton sekarang — ini jam prime time! Drop komen kamu 👇"
    elif cw and "Pagi" in cw["label"]:       cta = "☕ Konten pagi yang bikin hari kamu lebih bermakna."
    elif cw and "Sore" in cw["label"]:       cta = "🌆 Sambil santai sore, tonton ini dulu. Komen kalau relate!"
    elif cw and "Late Night" in cw["label"]: cta = "🦉 Buat yang masih melek — save dulu, baru tidur!"
    else:                                     cta = "💬 Komen kalau relate. Save kalau bermanfaat!"
    return f"{hook}\n\n{cta}\n\n🎧 Full episode:\n{url}\n\n{hashtags}".strip()

def make_grade_fn(style):
    if style == "warm":
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f-128)*1.15+135,0,255)
            f[:,:,0] = np.clip(f[:,:,0]*1.10,0,255)
            f[:,:,2] = np.clip(f[:,:,2]*0.90,0,255)
            return f.astype(np.uint8)
    elif style == "noir":
        def fn(f):
            f = f.astype(np.float32)
            g = f.mean(axis=2,keepdims=True)
            return np.clip((g*np.ones_like(f)-128)*1.45+128,0,255).astype(np.uint8)
    elif style == "vibrant":
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f-128)*1.3+128,0,255)
            g = f.mean(axis=2,keepdims=True)
            return np.clip(f*1.15-g*0.15,0,255).astype(np.uint8)
    else:
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f-128)*1.2+128,0,255)
            g = f.mean(axis=2,keepdims=True)
            f = f*0.85+g*0.15
            f[:,:,0] = np.clip(f[:,:,0]*0.94,0,255)
            f[:,:,2] = np.clip(f[:,:,2]*1.04,0,255)
            return f.astype(np.uint8)
    return fn

def _tc(text, size, color, stroke_w, dur, width=960):
    if not FONT_PATH: return None
    try:
        return TextClip(text=text, font_size=size, color=color, font=FONT_PATH,
                        stroke_color="black", stroke_width=stroke_w,
                        size=(width,None), method="caption", duration=dur)
    except Exception:
        return None

def subs_tiktok_rapi(words, cs, ce, sub_y, color, video_w=1080):
    layers, dur, grup_kata, i = [], ce-cs, [], 0
    while i < len(words):
        w = words[i]
        if w["start"] < cs or w["end"] > ce:
            i += 1; continue
        if i+1 < len(words):
            w2 = words[i+1]
            if w2["start"]-w["end"] < 0.3 and w2["end"] <= ce:
                grup_kata.append((w["start"],w2["end"],w["word"].capitalize()+" "+w2["word"]))
                i += 2; continue
        grup_kata.append((w["start"],w["end"],w["word"].capitalize()))
        i += 1
    for (t0_abs,t1_abs,teks) in grup_kata:
        t0 = max(t0_abs-cs, 0)
        t1 = min(t1_abs-cs, dur)
        if t1-t0 < 0.05: continue
        tc = _tc(teks.upper(), 88, color, 5, t1-t0, video_w-60)
        if tc:
            layers.append(tc.with_start(t0).with_position(("center",sub_y)))
    return layers

def subs_kalimat_rapi(segments, cs, ce, sub_y, color, video_w=1080):
    layers, dur = [], ce-cs
    for seg in segments:
        if seg["end"] < cs or seg["start"] > ce: continue
        t0 = max(seg["start"]-cs, 0)
        t1 = min(seg["end"]-cs, dur)
        if t1-t0 < 0.05: continue
        for baris in segment_subtitle(seg["text"], maks_char=42):
            fraksi    = len(baris)/max(len(seg["text"]),1)
            dur_baris = max(0.5, (t1-t0)*fraksi)
            tc = _tc(baris, 52, color, 3, min(dur_baris,t1-t0), video_w-80)
            if tc:
                layers.append(tc.with_start(t0).with_position(("center",sub_y)))
    return layers

def render_clip(video_url, audio_url, start, end, segments, words, *,
                use_subs, sub_style, sub_position, sub_color,
                use_grade, grade_style, use_hook, hook_text,
                use_bgm, watermark_path, output_name=""):
    dur      = end - start
    tmp_clip = os.path.join(TMP_DIR, f"raw_{uuid.uuid4().hex[:6]}.mp4")
    st.caption("Mengambil segmen dari stream...")
    if video_url == audio_url:
        cmd = ["ffmpeg","-y","-user_agent","Mozilla/5.0","-ss",str(start),"-i",video_url,"-t",str(dur),"-c","copy",tmp_clip]
    else:
        cmd = ["ffmpeg","-y","-user_agent","Mozilla/5.0","-ss",str(start),"-i",video_url,
               "-ss",str(start),"-i",audio_url,"-t",str(dur),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac",tmp_clip]
    r = subprocess.run(cmd, capture_output=True, timeout=180)
    if r.returncode != 0 or not os.path.exists(tmp_clip):
        st.caption("Fallback re-encode...")
        cmd2 = ["ffmpeg","-y","-user_agent","Mozilla/5.0","-ss",str(start),"-i",video_url,"-t",str(dur),"-c:v","libx264","-c:a","aac",tmp_clip]
        subprocess.run(cmd2, capture_output=True, timeout=300)
    if not os.path.exists(tmp_clip) or os.path.getsize(tmp_clip) < 1000:
        raise RuntimeError("Segmen kosong — stream URL kadaluarsa. Muat ulang lalu render lagi.")
    st.caption("Menerapkan efek & subtitle...")
    clip  = VideoFileClip(tmp_clip)
    final = clip.copy()
    w, h  = final.size
    final = final.with_effects([vfx.Crop(x_center=w/2,width=int(h*9/16),height=h), vfx.Resize((1080,1920))])
    fw = final.size[0]
    if use_grade:
        final = final.image_transform(make_grade_fn(grade_style))
    layers = [final]
    if use_subs and FONT_PATH:
        sub_y = 1580 if sub_position == "Bawah" else 160
        if "TikTok" in sub_style and words:
            layers.extend(subs_tiktok_rapi(words, start, end, sub_y, sub_color, fw))
        else:
            layers.extend(subs_kalimat_rapi(segments, start, end, sub_y, sub_color, fw))
    if use_hook and FONT_PATH:
        h_text = hook_text.strip() or random.choice(HOOK_POOL)
        tc = _tc(h_text, 46, "#FFD700", 3, 3.5, fw-80)
        if tc:
            layers.append(tc.with_start(0).with_position(("center",140)))
    if watermark_path and os.path.exists(watermark_path):
        try:
            wm = (ImageClip(watermark_path).with_effects([vfx.Resize(width=180)])
                  .with_opacity(0.70).with_duration(final.duration).with_position((fw-200,40)))
            layers.append(wm)
        except Exception: pass
    if len(layers) > 1:
        final = CompositeVideoClip(layers)
    if use_bgm and os.path.exists(BGM_PATH):
        try:
            bgm  = AudioFileClip(BGM_PATH).with_effects([afx.MultiplyVolume(0.15)]).with_duration(final.duration)
            orig = final.audio
            final = final.with_audio(CompositeAudioClip([orig,bgm]) if orig else bgm)
        except Exception: pass
    safe = re.sub(r"[^\w]","_",output_name)[:40] if output_name else uuid.uuid4().hex[:8]
    out  = os.path.join(OUTPUT_DIR, f"{safe}.mp4")
    final.write_videofile(out, codec="libx264", bitrate="10000k", fps=30, logger=None,
        ffmpeg_params=["-pix_fmt","yuv420p","-profile:v","high","-level","4.1","-movflags","+faststart"])
    clip.close()
    try: os.remove(tmp_clip)
    except Exception: pass
    return out

# ════════════════════════════════════════════════════════════════
#  UI — Dark Dashboard
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="Clipper Pro", layout="wide", page_icon="🎙️")

# ── CSS Injection via st.html (compatible with Streamlit 1.32+) ──
_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>

/* Base */
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.stApp { background: #0c0c0f !important; }
section[data-testid="stSidebar"] { background: #111115 !important; border-right: 1px solid #1f1f28 !important; }
section[data-testid="stSidebar"] > div { background: #111115 !important; }

/* Top toolbar */
header[data-testid="stHeader"] { background: #111115 !important; border-bottom: 1px solid #1f1f28 !important; }

/* Main content area */
.block-container { background: #0c0c0f !important; padding-top: 1.5rem !important; }

/* All text */
body, p, span, label, div { color: #d4d4d8 !important; }
h1 { color: #f4f4f5 !important; font-size: 22px !important; font-weight: 700 !important; letter-spacing: -0.5px !important; }
h2 { color: #f4f4f5 !important; font-size: 18px !important; font-weight: 600 !important; }
h3 { color: #e4e4e7 !important; font-size: 15px !important; font-weight: 600 !important; }

/* Sidebar text */
section[data-testid="stSidebar"] label { color: #a1a1aa !important; font-size: 12px !important; font-weight: 500 !important; }
section[data-testid="stSidebar"] p { color: #71717a !important; font-size: 12px !important; }
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #e4e4e7 !important; }

/* Buttons */
.stButton > button {
    background: #18181b !important; border: 1px solid #27272a !important;
    color: #a1a1aa !important; border-radius: 8px !important;
    font-size: 13px !important; font-weight: 500 !important;
    transition: all 0.15s !important; font-family: 'Inter', sans-serif !important;
}
.stButton > button:hover {
    background: #27272a !important; border-color: #3f3f46 !important;
    color: #f4f4f5 !important;
}
.stButton > button[kind="primary"] {
    background: #6d28d9 !important; border-color: #6d28d9 !important;
    color: #fff !important;
}
.stButton > button[kind="primary"]:hover { background: #5b21b6 !important; border-color: #5b21b6 !important; }

/* Text inputs */
.stTextInput > div > div > input {
    background: #18181b !important; border: 1px solid #27272a !important;
    color: #f4f4f5 !important; border-radius: 8px !important;
    font-size: 13px !important; font-family: 'Inter', sans-serif !important;
}
.stTextInput > div > div > input:focus { border-color: #6d28d9 !important; box-shadow: 0 0 0 2px #6d28d920 !important; }
.stTextInput > div > div > input::placeholder { color: #52525b !important; }

/* Selectbox */
.stSelectbox > div > div {
    background: #18181b !important; border: 1px solid #27272a !important;
    border-radius: 8px !important; color: #d4d4d8 !important;
}
.stSelectbox > div > div:focus-within { border-color: #6d28d9 !important; }

/* Sliders */
.stSlider > div > div > div > div { background: #6d28d9 !important; }
.stSlider > div > div > div { background: #27272a !important; }

/* Checkboxes */
.stCheckbox > label > div { background: #18181b !important; border-color: #27272a !important; }
.stCheckbox > label > div[data-checked="true"] { background: #6d28d9 !important; border-color: #6d28d9 !important; }

/* File uploader */
.stFileUploader > div {
    background: #18181b !important; border: 1px dashed #27272a !important;
    border-radius: 8px !important;
}
.stFileUploader > div:hover { border-color: #6d28d9 !important; }

/* Expanders */
.streamlit-expanderHeader {
    background: #18181b !important; border: 1px solid #27272a !important;
    border-radius: 8px !important; color: #d4d4d8 !important;
    font-size: 13px !important; font-weight: 500 !important;
}
.streamlit-expanderHeader:hover { background: #27272a !important; }
.streamlit-expanderContent { background: #111115 !important; border: 1px solid #27272a !important; border-top: none !important; border-radius: 0 0 8px 8px !important; }

/* Metric cards */
[data-testid="metric-container"] {
    background: #18181b !important; border: 1px solid #27272a !important;
    border-radius: 10px !important; padding: 12px 16px !important;
}
[data-testid="metric-container"] label { color: #71717a !important; font-size: 11px !important; font-weight: 500 !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"] { color: #f4f4f5 !important; font-size: 22px !important; font-weight: 700 !important; }
[data-testid="metric-container"] [data-testid="stMetricDelta"] { color: #71717a !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background: #18181b !important; border-radius: 8px !important; padding: 4px !important; gap: 4px !important; }
.stTabs [data-baseweb="tab"] {
    background: transparent !important; color: #71717a !important;
    border-radius: 6px !important; font-size: 13px !important; font-weight: 500 !important;
    border: none !important; padding: 6px 14px !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #d4d4d8 !important; background: #27272a !important; }
.stTabs [aria-selected="true"] { background: #6d28d9 !important; color: #fff !important; }
.stTabs [data-baseweb="tab-panel"] { background: transparent !important; }

/* Text area */
.stTextArea > div > div > textarea {
    background: #18181b !important; border: 1px solid #27272a !important;
    color: #d4d4d8 !important; border-radius: 8px !important;
    font-size: 13px !important; font-family: 'Inter', sans-serif !important;
}

/* Progress bars */
.stProgress > div > div { background: #27272a !important; border-radius: 4px !important; }
.stProgress > div > div > div { background: #6d28d9 !important; border-radius: 4px !important; }

/* Alerts / info boxes */
.stAlert { border-radius: 8px !important; border: 1px solid !important; }
div[data-baseweb="notification"] { background: #18181b !important; }

/* Success */
.element-container .stAlert[data-basetype="success"] { background: #052e16 !important; border-color: #14532d !important; color: #86efac !important; }
/* Info */
.element-container .stAlert[data-basetype="info"] { background: #0c1a2e !important; border-color: #1e3a5f !important; color: #93c5fd !important; }
/* Warning */
.element-container .stAlert[data-basetype="warning"] { background: #1c1308 !important; border-color: #3d2b08 !important; color: #fcd34d !important; }
/* Error */
.element-container .stAlert[data-basetype="error"] { background: #1c0808 !important; border-color: #3d0808 !important; color: #fca5a5 !important; }

/* Spinner */
.stSpinner > div { border-top-color: #6d28d9 !important; }

/* Divider */
hr { border-color: #27272a !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #18181b; }
::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #52525b; }

/* Caption */
.stCaption { color: #52525b !important; font-size: 11px !important; }

/* Download button */
.stDownloadButton > button {
    background: #1e1030 !important; border: 1px solid #4c1d95 !important;
    color: #c4b5fd !important; border-radius: 8px !important;
    font-size: 12px !important; font-weight: 500 !important;
}
.stDownloadButton > button:hover { background: #2d1a4a !important; }

/* Video player */
.stVideo { border-radius: 10px !important; overflow: hidden !important; border: 1px solid #27272a !important; }

/* Container with border */
[data-testid="stVerticalBlock"] > [data-testid="element-container"] > div[style*="border"] {
    background: #18181b !important; border-color: #27272a !important; border-radius: 12px !important;
}
</style>
"""
try:
    # st.html() tersedia di Streamlit >= 1.32
    st.html(_CSS)
except AttributeError:
    # Fallback: markdown dengan unsafe_allow_html
    st.markdown(_CSS, unsafe_allow_html=True)

fyp_info = get_fyp_status()
now_wib  = fyp_info["now"]
cw       = fyp_info["current_window"]
nw       = fyp_info["next_window"]
mnt      = fyp_info["minutes_to_next"]

# ── Header bar custom ────────────────────────────────────────────
mode_badge = "☁️ Cloud" if IS_CLOUD else "💻 Lokal"
cookies_ok_header = os.path.exists(COOKIES_FILE)
status_color = "#22c55e" if cookies_ok_header else "#ef4444"
status_text  = "Cookies Aktif" if cookies_ok_header else "Cookies Belum Ada"

fyp_active = cw is not None
fyp_color  = "#22c55e" if fyp_active else "#f59e0b"
fyp_text   = f"JAM FYP: {cw['label'].upper()}" if fyp_active else (
    f"FYP pukul {nw['range'][0]:02d}:00" if nw else "—")

st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;
     background:#111115;border:1px solid #1f1f28;border-radius:12px;
     padding:14px 20px;margin-bottom:20px;">
  <div style="display:flex;align-items:center;gap:12px">
    <div style="width:36px;height:36px;background:#6d28d9;border-radius:10px;
         display:flex;align-items:center;justify-content:center;
         font-size:16px;font-weight:800;color:#fff;letter-spacing:-1px">CP</div>
    <div>
      <div style="font-size:16px;font-weight:700;color:#f4f4f5">Clipper Pro</div>
      <div style="font-size:11px;color:#52525b">Modern. Cepat. Fungsional.</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    <div style="background:#18181b;border:1px solid #27272a;border-radius:20px;
         padding:5px 12px;font-size:11px;color:#71717a">{mode_badge}</div>
    <div style="background:#18181b;border:1px solid #27272a;border-radius:20px;
         padding:5px 12px;font-size:11px;display:flex;align-items:center;gap:6px">
      <div style="width:7px;height:7px;border-radius:50%;background:{status_color}"></div>
      <span style="color:#a1a1aa">{status_text}</span>
    </div>
    <div style="background:#18181b;border:1px solid #27272a;border-radius:20px;
         padding:5px 12px;font-size:11px;display:flex;align-items:center;gap:6px">
      <div style="width:7px;height:7px;border-radius:50%;background:{fyp_color}"></div>
      <span style="color:#a1a1aa">{fyp_text}</span>
    </div>
    <div style="background:#18181b;border:1px solid #27272a;border-radius:20px;
         padding:5px 12px;font-size:13px;font-weight:600;color:#f4f4f5">
      {now_wib.strftime('%H:%M')} WIB
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Stats row ────────────────────────────────────────────────────
output_count = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".mp4")])
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Klip", output_count)
c2.metric("Mode", "Cloud" if IS_CLOUD else "Lokal")
c3.metric("Cookies", "Aktif" if cookies_ok_header else "Belum")
c4.metric("Font", "OK" if FONT_PATH else "N/A")
c5.metric("Jam FYP", cw["label"] if cw else "—")

# ── FYP Windows visual ───────────────────────────────────────────
fyp_cols = st.columns(len(FYP_WINDOWS))
for idx, win in enumerate(FYP_WINDOWS):
    s, e   = win["range"]
    aktif  = cw and cw["label"] == win["label"]
    lewat  = now_wib.hour >= e and not aktif
    bg     = "#1e1030" if aktif else ("#18181b" if not lewat else "#111115")
    border = "#6d28d9" if aktif else "#27272a"
    txt    = "#c4b5fd" if aktif else ("#52525b" if lewat else "#71717a")
    dot    = "#6d28d9" if aktif else ("#27272a" if lewat else "#3f3f46")
    jam_str = f"{s:02d}:00–{e:02d}:00"
    badge  = '<span style="font-size:9px;background:#6d28d9;color:#fff;padding:1px 5px;border-radius:3px;margin-left:4px">LIVE</span>' if aktif else ""
    with fyp_cols[idx]:
        st.markdown(f"""
<div style="background:{bg};border:1px solid {border};border-radius:9px;
     padding:10px;text-align:center">
  <div style="display:flex;align-items:center;justify-content:center;gap:6px;margin-bottom:4px">
    <div style="width:6px;height:6px;border-radius:50%;background:{dot}"></div>
    <span style="font-size:11px;font-weight:600;color:{txt}">{win['label']}{badge}</span>
  </div>
  <div style="font-size:10px;color:#3f3f46">{jam_str}</div>
</div>""", unsafe_allow_html=True)

st.markdown("<div style='margin:8px 0'></div>", unsafe_allow_html=True)

# ── SIDEBAR ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
<div style="padding:4px 0 16px">
  <div style="font-size:13px;font-weight:700;color:#f4f4f5">Clipper Pro</div>
  <div style="font-size:10px;color:#52525b">Podcast → Klip Viral</div>
</div>""", unsafe_allow_html=True)

    # Cookies
    st.markdown('<div style="font-size:11px;font-weight:600;color:#52525b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">YouTube Cookies</div>', unsafe_allow_html=True)
    _secrets_ok = False
    try:
        _sc = st.secrets["cookies"]["content"]
        _secrets_ok = bool(_sc and len(_sc) > 100)
    except Exception:
        pass
    if os.path.exists(COOKIES_FILE):
        label = "Permanen via Secrets" if _secrets_ok else "Aktif (sementara)"
        st.success(f"Cookies {label}")
        if not _secrets_ok and IS_CLOUD:
            st.warning("Simpan ke Secrets agar tidak hilang saat restart.")
        if st.button("Hapus Cookies", use_container_width=True):
            os.remove(COOKIES_FILE); st.rerun()
    else:
        if IS_CLOUD:
            st.error("Belum ada cookies — YouTube 403")
        else:
            st.info("Auto-detect browser. Upload manual jika gagal.")
        st.caption("Export dari Chrome: buka YouTube → login → ekstensi 'Get cookies.txt LOCALLY' → Export Netscape")
    cookies_up = st.file_uploader("Upload cookies.txt", type=["txt"])
    if cookies_up:
        raw_bytes = cookies_up.read()
        with open(COOKIES_FILE, "wb") as fh:
            fh.write(raw_bytes)
        # Simpan isi cookies ke session_state biar bisa ditampilkan
        st.session_state["cookies_raw"] = raw_bytes.decode("utf-8", errors="ignore")
        st.success("Cookies tersimpan!")
        st.rerun()

    # Tampilkan isi cookies + tombol salin ke Secrets jika sudah ada
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8", errors="ignore") as fh:
                _raw = fh.read().strip()
        except Exception:
            _raw = ""

        if _raw and IS_CLOUD:
            with st.expander("Salin isi cookies untuk Streamlit Secrets", expanded=False):
                # Format langsung siap paste ke Secrets
                _secrets_ready = f'''[cookies]
content = """
{_raw}
"""'''
                st.caption("Salin semua teks di bawah → paste ke Streamlit Cloud Settings → Secrets")
                st.text_area(
                    "secrets_content",
                    value=_secrets_ready,
                    height=180,
                    label_visibility="collapsed",
                    help="Select All (Ctrl+A) lalu Copy"
                )
                st.caption("Cara: Streamlit Cloud → App kamu → Settings → Secrets → paste → Save")

    st.divider()
    st.markdown('<div style="font-size:11px;font-weight:600;color:#52525b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Pengaturan Klip</div>', unsafe_allow_html=True)
    n_clips     = st.slider("Jumlah saran klip",       3, 12,  6)
    min_dur     = st.slider("Durasi minimum (detik)",  15, 60, 30)
    max_dur     = st.slider("Durasi maksimum (detik)", 30,180, 90)
    model_size  = st.selectbox("Model Whisper", ["tiny","base","small"], index=0,
                                help="tiny=cepat | base=seimbang | small=akurat")
    analyze_max = st.slider("Analisis maks (menit)", 10, 60, 20)
    koreksi_on  = st.checkbox("Koreksi Ejaan (EYD)", value=True)

    st.divider()
    st.markdown('<div style="font-size:11px;font-weight:600;color:#52525b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Filter Momen</div>', unsafe_allow_html=True)
    filter_kat = st.selectbox("Kategori",
        options=["semua","komedi","horror","kaget","haru","drama","motivasi","fakta"],
        format_func=lambda x: {"semua":"Semua (mix terbaik)","komedi":"😂 Komedi","horror":"👻 Horror",
            "kaget":"😱 Kaget / Twist","haru":"😢 Haru","drama":"🔥 Drama",
            "motivasi":"💪 Motivasi","fakta":"🤯 Fakta"}[x], index=0)
    st.session_state["filter_kat"] = filter_kat

    st.divider()
    st.markdown('<div style="font-size:11px;font-weight:600;color:#52525b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Efek Video</div>', unsafe_allow_html=True)
    use_grade   = st.checkbox("Color Grading", value=True)
    grade_style = st.selectbox("Gaya", ["sinematik","warm","vibrant","noir"], disabled=not use_grade)
    use_subs     = st.checkbox("Auto Subtitle", value=True)
    sub_style    = st.selectbox("Gaya Subtitle", ["🎬 TikTok — per kata, besar","📝 Kalimat — klasik"], disabled=not use_subs)
    sub_position = st.selectbox("Posisi", ["Bawah","Atas"], disabled=not use_subs)
    sub_color    = st.selectbox("Warna Teks", ["white","yellow","#FF3333","#00FFFF"], disabled=not use_subs)

    st.divider()
    st.markdown('<div style="font-size:11px;font-weight:600;color:#52525b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Hook & BGM</div>', unsafe_allow_html=True)
    use_hook    = st.checkbox("Hook Text (3 dtk pertama)", value=True)
    custom_hook = st.text_input("Custom hook (kosong = auto)")
    use_bgm     = st.checkbox("BGM Latar", value=False)
    bgm_upload  = st.file_uploader("Upload BGM (.mp3)", type=["mp3"])
    if bgm_upload:
        with open(BGM_PATH,"wb") as fh: fh.write(bgm_upload.read())
        st.success("BGM tersimpan!")
    st.caption("BGM aktif" if os.path.exists(BGM_PATH) else "Belum ada BGM")

    st.divider()
    st.markdown('<div style="font-size:11px;font-weight:600;color:#52525b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Watermark</div>', unsafe_allow_html=True)
    wm_upload = st.file_uploader("Upload logo (PNG transparan)", type=["png","jpg","jpeg"])
    if wm_upload:
        wm_save = os.path.join(WM_DIR, wm_upload.name)
        with open(wm_save,"wb") as fh: fh.write(wm_upload.read())
        st.session_state["watermark"] = wm_save
        st.success(f"{wm_upload.name}")
        st.rerun()
    wm_files = [f for f in os.listdir(WM_DIR) if f.lower().endswith((".png",".jpg",".jpeg"))]
    if wm_files:
        chosen_wm = st.selectbox("Pilih watermark", ["(tidak pakai)"]+wm_files)
        st.session_state["watermark"] = (os.path.join(WM_DIR,chosen_wm) if chosen_wm!="(tidak pakai)" else None)
    else:
        st.caption("Belum ada watermark.")
        st.session_state.setdefault("watermark", None)

# ── MAIN ─────────────────────────────────────────────────────────
watermark_path = st.session_state.get("watermark")

if IS_CLOUD and not os.path.exists(COOKIES_FILE):
    st.markdown("""
<div style="background:#1c0a0a;border:1px solid #7f1d1d;border-radius:10px;padding:16px 20px;margin:8px 0">
  <div style="font-size:14px;font-weight:600;color:#fca5a5;margin-bottom:4px">Cookies belum diupload</div>
  <div style="font-size:12px;color:#f87171">Upload cookies.txt di sidebar untuk mulai menggunakan app.</div>
</div>""", unsafe_allow_html=True)
    st.stop()

# ── URL Input ────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:13px;font-weight:600;color:#a1a1aa;margin-bottom:8px">
  Paste Link YouTube / Podcast
</div>""", unsafe_allow_html=True)
col_url, col_btn = st.columns([5, 1])
with col_url:
    input_url = st.text_input("url", label_visibility="collapsed",
                               placeholder="https://www.youtube.com/watch?v=...")
with col_btn:
    btn_load = st.button("Muat", use_container_width=True, type="primary")

if btn_load and input_url.strip():
    with st.spinner("Mengambil info..."):
        try:
            info = get_video_info(input_url.strip())
            st.session_state.update({
                "film_url":      input_url.strip(),
                "film_title":    info.get("title","Unknown"),
                "film_duration": float(info.get("duration") or 0),
                "film_thumb":    info.get("thumbnail"),
                "film_channel":  info.get("channel") or info.get("uploader",""),
            })
            for k in ["suggestions","segs","words","hashtags","video_url","audio_url"]:
                st.session_state.pop(k, None)
            st.rerun()
        except Exception as e:
            err = str(e)
            if "403" in err or "Forbidden" in err:
                st.error("YouTube 403 — cookies.txt belum diupload atau sudah expired.")
            elif "cookie" in err.lower():
                st.error("Gagal baca cookies. Upload cookies.txt manual di sidebar.")
            else:
                st.error(f"Gagal memuat: {err}")

if "film_title" in st.session_state:
    title    = st.session_state["film_title"]
    duration = st.session_state["film_duration"]
    thumb    = st.session_state.get("film_thumb")
    channel  = st.session_state.get("film_channel","")
    url      = st.session_state["film_url"]

    st.markdown("<div style='margin:16px 0 8px'></div>", unsafe_allow_html=True)

    col_t, col_m = st.columns([1, 4])
    with col_t:
        if thumb:
            st.image(thumb, use_container_width=True)
    with col_m:
        dur_str = (f"{int(duration//3600)}j {int((duration%3600)//60)}m"
                   if duration >= 3600 else f"{int(duration//60)}m {int(duration%60)}d")
        st.markdown(f"""
<div style="background:#18181b;border:1px solid #27272a;border-radius:12px;padding:16px 20px">
  <div style="font-size:16px;font-weight:700;color:#f4f4f5;margin-bottom:4px">{title}</div>
  {"<div style='font-size:12px;color:#71717a;margin-bottom:12px'>"+channel+"</div>" if channel else ""}
  <div style="display:flex;gap:10px;flex-wrap:wrap">
    <div style="background:#111115;border:1px solid #27272a;border-radius:7px;padding:6px 12px;font-size:11px;color:#a1a1aa">
      <span style="color:#52525b">Durasi</span> &nbsp; <strong style="color:#d4d4d8">{dur_str}</strong>
    </div>
    <div style="background:#111115;border:1px solid #27272a;border-radius:7px;padding:6px 12px;font-size:11px;color:#a1a1aa">
      <span style="color:#52525b">Analisis</span> &nbsp; <strong style="color:#d4d4d8">{analyze_max} menit pertama</strong>
    </div>
    <div style="background:#111115;border:1px solid #27272a;border-radius:7px;padding:6px 12px;font-size:11px;color:#a1a1aa">
      <span style="color:#52525b">Watermark</span> &nbsp; <strong style="color:{'#86efac' if watermark_path else '#f87171'}">{"Ada" if watermark_path else "Belum"}</strong>
    </div>
    <div style="background:#111115;border:1px solid #27272a;border-radius:7px;padding:6px 12px;font-size:11px;color:#a1a1aa">
      <span style="color:#52525b">Font</span> &nbsp; <strong style="color:{'#86efac' if FONT_PATH else '#f87171'}">{"OK" if FONT_PATH else "N/A"}</strong>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("<div style='margin:12px 0'></div>", unsafe_allow_html=True)

    if st.button("Analisis Momen Terbaik (AI)", type="primary", use_container_width=True):
        try:
            with st.spinner(f"Download audio {analyze_max} menit pertama..."):
                audio_path = download_audio_only(url, duration, max_sec=analyze_max*60)
                st.session_state["audio_path"] = audio_path
            with st.spinner("Ambil stream URL untuk render..."):
                v_url, a_url = get_stream_urls(url)
                st.session_state["video_url"] = v_url
                st.session_state["audio_url"] = a_url
            with st.spinner(f"Transkripsi AI ({model_size}) + koreksi ejaan..."):
                segs, words = transcribe_audio(audio_path, model_size, koreksi=koreksi_on)
                st.session_state["segs"]  = segs
                st.session_state["words"] = words
            with st.spinner("Scoring momen terbaik..."):
                filter_kat = st.session_state.get("filter_kat","semua")
                suggestions = score_clips(audio_path, segs, min(duration,analyze_max*60),
                                          n_clips, min_dur, max_dur, filter_kategori=filter_kat)
                st.session_state["suggestions"] = suggestions
                st.session_state["hashtags"]    = generate_hashtags(segs, title)
            st.rerun()
        except Exception as e:
            st.error(f"Analisis gagal: {e}")

if "suggestions" in st.session_state and "film_title" in st.session_state:
    suggestions = st.session_state["suggestions"]
    segs        = st.session_state.get("segs", [])
    words       = st.session_state.get("words", [])
    title       = st.session_state["film_title"]
    v_url       = st.session_state.get("video_url","")
    a_url       = st.session_state.get("audio_url","")
    duration    = st.session_state.get("film_duration", 0)
    url         = st.session_state["film_url"]
    hashtags    = generate_hashtags(segs, title)
    caption_fyp = generate_caption_fyp(segs, title, url, fyp_info)

    # ── HASHTAG & CAPTION — langsung keliatan, no tab needed ──────
    niche    = detect_niche(segs)
    emo_icon = {"komedi":"😂","horror":"👻","kaget":"😱","haru":"😢",
                "drama":"🔥","motivasi":"💪","edukasi":"🤯"}.get(niche,"⭐")
    total_kw = sum(sum(1 for k in VIRAL_KEYWORDS if k in s["text"].lower()) for s in segs)
    viral_lv = "🔥 Tinggi" if total_kw>=15 else ("✅ Sedang" if total_kw>=7 else "⚠️ Rendah")
    viral_cl = "#22c55e" if total_kw>=15 else ("#f59e0b" if total_kw>=7 else "#ef4444")

    st.markdown(f"""
<div style="background:#18181b;border:1px solid #27272a;border-radius:12px;padding:16px 20px;margin-bottom:12px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
    <div style="font-size:13px;font-weight:700;color:#f4f4f5">Auto Hashtag + Caption FYP</div>
    <div style="display:flex;gap:8px">
      <div style="background:#111115;border:1px solid #27272a;border-radius:6px;padding:3px 10px;font-size:11px;color:#a1a1aa">
        {emo_icon} Niche: <strong style="color:#c4b5fd">{niche.upper()}</strong>
      </div>
      <div style="background:#111115;border:1px solid {viral_cl}44;border-radius:6px;padding:3px 10px;font-size:11px;color:{viral_cl}">
        Viral: {viral_lv}
      </div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    col_ht, col_cap = st.columns([1, 1])
    with col_ht:
        st.markdown('<div style="font-size:11px;font-weight:600;color:#71717a;margin-bottom:6px">HASHTAG — salin ke caption</div>', unsafe_allow_html=True)
        st.text_area("ht", hashtags, height=160, label_visibility="collapsed",
                     help="Hashtag otomatis dari analisis konten + niche + kata viral transkripsi")
        tags = [t for t in hashtags.split() if t.startswith("#")]
        hc1, hc2, hc3 = st.columns(3)
        hc1.metric("Total tag", len(tags))
        hc2.metric("Kata viral", total_kw)
        if hc3.button("Ulang Hashtag"):
            st.session_state["hashtags"] = generate_hashtags(segs, title)
            st.rerun()
    with col_cap:
        st.markdown('<div style="font-size:11px;font-weight:600;color:#71717a;margin-bottom:6px">CAPTION FYP — langsung paste</div>', unsafe_allow_html=True)
        st.text_area("cap", caption_fyp, height=160, label_visibility="collapsed",
                     help="Caption dengan CTA otomatis sesuai jam FYP sekarang")
        if cw:
            st.success(f"Jam FYP aktif — upload sekarang! ({cw['label']})")
        else:
            jam_str = f"{nw['range'][0]:02d}:00" if nw else "—"
            st.info(f"Upload optimal pukul {jam_str} WIB")

    if words:
        with st.expander(f"Preview Transkripsi — {len(words)} kata | {len(segs)} segmen", expanded=False):
            ca, cb = st.columns(2)
            ca.caption("50 kata pertama + timing:")
            ca.markdown("  ".join(f"`{w['word']}` _{w['start']:.1f}s_" for w in words[:50])
                        + (" …" if len(words)>50 else ""))
            cb.caption("Teks lengkap:")
            cb.caption(" ".join(s["text"] for s in segs)[:600] + "…")

    st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin:20px 0 12px">
  <div style="font-size:15px;font-weight:700;color:#f4f4f5">{len(suggestions)} Momen Terbaik</div>
</div>""", unsafe_allow_html=True)

    if not suggestions:
        st.warning("Tidak ada momen ditemukan. Kurangi durasi minimum atau tambah menit analisis.")
    else:
        def do_render(start, end, out_name):
            try:
                out = render_clip(v_url, a_url, start, end, segs, words,
                    use_subs=use_subs, sub_style=sub_style, sub_position=sub_position,
                    sub_color=sub_color, use_grade=use_grade, grade_style=grade_style,
                    use_hook=use_hook, hook_text=custom_hook, use_bgm=use_bgm,
                    watermark_path=watermark_path, output_name=out_name)
                st.success("Selesai! Cek galeri di bawah.")
                st.balloons()
            except Exception as e:
                st.error(f"Render gagal: {e}")
                st.caption("Muat ulang link lalu render lagi jika stream expired.")

        if len(suggestions) > 1 and st.button("Render SEMUA Klip Sekaligus", use_container_width=True):
            prog = st.progress(0, "Memulai...")
            for idx, sug in enumerate(suggestions):
                prog.progress(idx/len(suggestions), f"Render klip #{idx+1}...")
                do_render(sug["start"], sug["end"],
                          f"{re.sub(r'[^\\w]','_',title)[:25]}_klip{idx+1}")
            prog.progress(1.0, "Semua selesai!")
            st.balloons(); st.rerun()

        for i, sug in enumerate(suggestions):
            score_pct = int(sug["score"] * 100)
            kat       = sug.get("kategori","campuran")
            emo_emoji = EMOTION_EMOJI.get(kat,"⭐")
            score_color = "#22c55e" if score_pct>=70 else ("#f59e0b" if score_pct>=45 else "#ef4444")

            with st.expander(
                f"Klip #{i+1} {emo_emoji} {kat.upper()} — {sug['label']} | {score_pct}%",
                expanded=(i==0)):

                # Score badge custom
                st.markdown(f"""
<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
  <div style="background:#18181b;border:1px solid {score_color}33;border-radius:7px;
       padding:4px 10px;font-size:11px;font-weight:700;color:{score_color}">
    Skor FYP: {score_pct}%
  </div>
  <div style="background:#18181b;border:1px solid #27272a;border-radius:7px;
       padding:4px 10px;font-size:11px;color:#71717a">
    {int(sug['end']-sug['start'])} detik
  </div>
  {"<div style='background:#18181b;border:1px solid #27272a;border-radius:7px;padding:4px 10px;font-size:11px;color:#71717a'>⚡ Spike "+str(int(sug.get('spike',0)*100))+"</div>" if sug.get('spike',0)>0.3 else ""}
</div>""", unsafe_allow_html=True)

                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Emosi",   f"{int(sug.get('emosi',0)*100)}%")
                c2.metric("Energi",  f"{int(sug.get('energy',0)*100)}%")
                c3.metric("Spike",   f"{int(sug.get('spike',0)*100)}%")
                c4.metric("Struktur",f"{int(sug.get('struktur',0)*100)}%")

                cat_detail = sug.get("cat_detail",{})
                if cat_detail:
                    badges = "  ".join(
                        f"{EMOTION_EMOJI.get(c,'⭐')} **{c}** ({w}pt)"
                        for c,w in sorted(cat_detail.items(),key=lambda x:-x[1])[:4])
                    st.markdown(f"**Emosi:** {badges}")

                if sug.get("preview") and sug["preview"] != "—":
                    st.info(f'{emo_emoji} *"{sug["preview"]}"*')

                if score_pct >= 70:   st.success("Potensi viral TINGGI — prioritas upload!")
                elif score_pct >= 45: st.info("Potensi sedang — layak diupload.")
                else:                 st.warning("Skor rendah — coba filter lain.")

                with st.expander("Detail skor komponen", expanded=False):
                    for lbl, val in {
                        "Emosi (40%)":        sug.get("emosi",0),
                        "Energi audio (20%)": sug.get("energy",0),
                        "Kepadatan (15%)":    sug.get("density",0),
                        "Lonjakan (15%)":     sug.get("spike",0),
                        "Struktur (10%)":     sug.get("struktur",0),
                    }.items():
                        st.progress(float(val), text=f"{lbl}: {int(val*100)}%")

                if st.button(f"Render Klip #{i+1}", key=f"r_{i}", use_container_width=True):
                    with st.spinner(f"Render klip #{i+1}..."):
                        do_render(sug["start"], sug["end"],
                                  f"{re.sub(r'[^\\w]','_',title)[:25]}_klip{i+1}_{kat}")

        st.markdown("---")
        with st.expander("Potong Manual — tentukan sendiri start & end"):
            cm1, cm2 = st.columns(2)
            m_s    = cm1.number_input("Start (detik)", 0.0, float(duration or 9999), 0.0, step=1.0, key="ms")
            m_e    = cm2.number_input("End (detik)",   0.0, float(duration or 9999), min(float(duration or 60),90.0), step=1.0, key="me")
            m_name = st.text_input("Nama output", placeholder="nama_klip_kamu")
            if st.button("Render Manual", use_container_width=True):
                if m_e <= m_s:
                    st.error("End harus lebih besar dari Start!")
                else:
                    with st.spinner("Render..."):
                        do_render(m_s, m_e, m_name.strip() or f"{re.sub(r'[^\\w]','_',title)[:25]}_manual")

# ── Gallery ───────────────────────────────────────────────────────
st.markdown("<div style='margin:24px 0 0'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
  <div style="font-size:15px;font-weight:700;color:#f4f4f5">Galeri Klip</div>
</div>""", unsafe_allow_html=True)

output_files = sorted(
    (f for f in os.listdir(OUTPUT_DIR) if f.endswith(".mp4")),
    key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR,f)), reverse=True)

if not output_files:
    st.markdown("""
<div style="background:#18181b;border:1px dashed #27272a;border-radius:10px;
     padding:32px;text-align:center;color:#52525b;font-size:13px">
  Belum ada klip yang dirender
</div>""", unsafe_allow_html=True)
else:
    st.caption(f"{len(output_files)} klip tersedia")
    if st.button("Hapus Semua Klip", use_container_width=False):
        for f in output_files:
            try: os.remove(os.path.join(OUTPUT_DIR,f))
            except Exception: pass
        st.rerun()
    for f in output_files:
        fpath   = os.path.join(OUTPUT_DIR,f)
        size_mb = os.path.getsize(fpath) / 1_048_576
        st.markdown(f'<div style="font-size:12px;color:#71717a;margin:8px 0 4px">{f} — {size_mb:.1f} MB</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([3,1,1])
        c1.video(fpath)
        with open(fpath,"rb") as fh:
            c2.download_button("Unduh", fh, file_name=f, mime="video/mp4",
                               key=f"dl_{f}", use_container_width=True)
        if c3.button("Hapus", key=f"del_{f}", use_container_width=True):
            os.remove(fpath); st.rerun()
