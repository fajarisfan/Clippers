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

# ── Direktori ────────────────────────────────────────────────────
TMP_DIR      = "/tmp/hpc_tmp"
OUTPUT_DIR   = "/tmp/hpc_output"
WM_DIR       = "/tmp/hpc_wm"
BGM_PATH     = "/tmp/hpc_bgm.mp3"
COOKIES_FILE = "/tmp/hpc_cookies.txt"

for _d in [TMP_DIR, OUTPUT_DIR, WM_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── Font resolver ────────────────────────────────────────────────
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

# ════════════════════════════════════════════════════════════════
#  JAM FYP — Zona waktu Indonesia (WIB)
# ════════════════════════════════════════════════════════════════
FYP_WINDOWS = [
    {"label": "🌅 Pagi Aktif",     "range": (6,  9),  "desc": "Orang buka HP setelah bangun tidur"},
    {"label": "☕ Istirahat Siang", "range": (11, 13), "desc": "Jam makan siang, scrolling santai"},
    {"label": "🌆 Sore Nongkrong", "range": (15, 17), "desc": "Pulang kerja/sekolah, engagement tinggi"},
    {"label": "🌙 Prime Time",     "range": (19, 22), "desc": "⭐ JAM EMAS — traffic tertinggi TikTok/Reels"},
    {"label": "🦉 Late Night",     "range": (22, 24), "desc": "Niche audience, engagement loyal"},
]

def get_fyp_status() -> dict:
    """Cek jam sekarang vs jam FYP optimal (WIB)."""
    wib = pytz.timezone("Asia/Jakarta")
    now = datetime.now(wib)
    hour = now.hour
    minute = now.minute

    current_window = None
    next_window    = None
    minutes_to_next = None

    for w in FYP_WINDOWS:
        s, e = w["range"]
        if s <= hour < e:
            current_window = w
            break

    # Cari window berikutnya
    for w in FYP_WINDOWS:
        s, e = w["range"]
        start_min = s * 60
        now_min   = hour * 60 + minute
        if start_min > now_min:
            next_window     = w
            minutes_to_next = start_min - now_min
            break

    if next_window is None and FYP_WINDOWS:
        # Wrap ke hari berikutnya — window pertama besok
        nw = FYP_WINDOWS[0]
        s  = nw["range"][0]
        minutes_to_next = (24 * 60) - (hour * 60 + minute) + s * 60
        next_window = nw

    return {
        "now":            now,
        "hour":           hour,
        "current_window": current_window,
        "next_window":    next_window,
        "minutes_to_next": minutes_to_next,
    }


# ════════════════════════════════════════════════════════════════
#  EMOTION LEXICON — per kategori dengan bobot berbeda
# ════════════════════════════════════════════════════════════════

# Format: kata → (kategori, bobot 1–5)
# Bobot 5 = sinyal paling kuat untuk FYP / emosi tinggi
EMOTION_LEXICON: dict[str, tuple[str, int]] = {
    # ── KOMEDI / TAWA ──────────────────────────────────────────
    "ngakak": ("komedi", 5), "wkwkwk": ("komedi", 5), "hahaha": ("komedi", 4),
    "ketawa": ("komedi", 4), "lucu": ("komedi", 4), "gokil": ("komedi", 4),
    "receh": ("komedi", 3), "kocak": ("komedi", 4), "bercanda": ("komedi", 3),
    "lelucon": ("komedi", 3), "humor": ("komedi", 3), "lawak": ("komedi", 3),
    "absurd": ("komedi", 3), "geli": ("komedi", 3), "ngikik": ("komedi", 4),
    "ngenes": ("komedi", 3), "random": ("komedi", 2), "lebay": ("komedi", 3),
    "alay": ("komedi", 2), "jayus": ("komedi", 3), "awkward": ("komedi", 3),
    "parah": ("komedi", 3), "gilaa": ("komedi", 4), "gila": ("komedi", 3),
    "anjir": ("komedi", 4), "anjay": ("komedi", 4), "astaga": ("komedi", 3),

    # ── SERAM / HORROR ─────────────────────────────────────────
    "hantu": ("horror", 5), "setan": ("horror", 5), "pocong": ("horror", 5),
    "kuntilanak": ("horror", 5), "gendruwo": ("horror", 5), "tuyul": ("horror", 4),
    "arwah": ("horror", 5), "roh": ("horror", 4), "mistis": ("horror", 4),
    "kesurupan": ("horror", 5), "santet": ("horror", 5), "teluh": ("horror", 5),
    "pelet": ("horror", 4), "dukun": ("horror", 4), "pesugihan": ("horror", 5),
    "serem": ("horror", 4), "ngeri": ("horror", 4), "merinding": ("horror", 5),
    "takut": ("horror", 3), "ketakutan": ("horror", 4), "horor": ("horror", 4),
    "gelap": ("horror", 2), "malam": ("horror", 2), "kuburan": ("horror", 4),
    "mayat": ("horror", 4), "mati": ("horror", 3), "kematian": ("horror", 4),
    "sumpah": ("horror", 3), "terkutuk": ("horror", 5), "ritual": ("horror", 4),
    "gaib": ("horror", 4), "supranatural": ("horror", 4), "paranormal": ("horror", 4),
    "makhluk": ("horror", 3), "penampakan": ("horror", 5), "gangguan": ("horror", 3),

    # ── KAGET / TWIST / REAKSI ─────────────────────────────────
    "kaget": ("kaget", 5), "syok": ("kaget", 5), "terkejut": ("kaget", 4),
    "shock": ("kaget", 5), "ternyata": ("kaget", 4), "tiba-tiba": ("kaget", 4),
    "mendadak": ("kaget", 4), "nggak nyangka": ("kaget", 5), "gak nyangka": ("kaget", 5),
    "lho": ("kaget", 3), "wah": ("kaget", 3), "eh": ("kaget", 2),
    "kok bisa": ("kaget", 4), "masa": ("kaget", 3), "beneran": ("kaget", 3),
    "serius": ("kaget", 3), "sungguh": ("kaget", 2), "bukan main": ("kaget", 4),
    "gila banget": ("kaget", 5), "parah banget": ("kaget", 5),
    "nggak percaya": ("kaget", 5), "gak percaya": ("kaget", 5),
    "mustahil": ("kaget", 4), "impossible": ("kaget", 4), "wtf": ("kaget", 5),
    "plot twist": ("kaget", 5), "twist": ("kaget", 4), "balik badan": ("kaget", 3),

    # ── HARU / EMOSI DALAM ─────────────────────────────────────
    "nangis": ("haru", 5), "nangis-nangis": ("haru", 5), "ngebantu": ("haru", 3),
    "terharu": ("haru", 5), "haru": ("haru", 4), "menyentuh": ("haru", 4),
    "touching": ("haru", 4), "sedih": ("haru", 4), "kesedihan": ("haru", 4),
    "mengharu": ("haru", 4), "baper": ("haru", 3), "mewek": ("haru", 4),
    "pilu": ("haru", 4), "nelangsa": ("haru", 4), "rindu": ("haru", 3),
    "kehilangan": ("haru", 4), "ditinggal": ("haru", 4), "meninggal": ("haru", 4),
    "almarhum": ("haru", 4), "almarhumah": ("haru", 4), "duka": ("haru", 4),
    "bangga": ("haru", 3), "terharu bangga": ("haru", 5), "menangis": ("haru", 5),

    # ── KONFLIK / DRAMA ────────────────────────────────────────
    "berantem": ("drama", 5), "ribut": ("drama", 4), "konflik": ("drama", 4),
    "cekcok": ("drama", 4), "debat": ("drama", 3), "bertengkar": ("drama", 5),
    "putus": ("drama", 4), "cerai": ("drama", 5), "selingkuh": ("drama", 5),
    "khianat": ("drama", 5), "bohong": ("drama", 4), "tipu": ("drama", 4),
    "fitnah": ("drama", 4), "gosip": ("drama", 4), "skandal": ("drama", 5),
    "ketahuan": ("drama", 5), "ketangkap": ("drama", 4), "nyesel": ("drama", 4),
    "toxic": ("drama", 4), "ghosting": ("drama", 4), "friendzone": ("drama", 3),
    "sakit hati": ("drama", 4), "dendam": ("drama", 4), "marah": ("drama", 3),
    "kesel": ("drama", 3), "ngamuk": ("drama", 4), "emosi": ("drama", 3),

    # ── MOTIVASI / INSPIRASI ───────────────────────────────────
    "bangkit": ("motivasi", 4), "berjuang": ("motivasi", 4), "sukses": ("motivasi", 3),
    "gagal": ("motivasi", 3), "jatuh bangun": ("motivasi", 4), "mimpi": ("motivasi", 3),
    "impian": ("motivasi", 3), "buktikan": ("motivasi", 4), "nyerah": ("motivasi", 3),
    "pantang menyerah": ("motivasi", 5), "semangat": ("motivasi", 3), "kuat": ("motivasi", 3),
    "optimis": ("motivasi", 3), "percaya diri": ("motivasi", 4), "luar biasa": ("motivasi", 3),
    "menginspirasi": ("motivasi", 4), "inspirasi": ("motivasi", 3), "motivasi": ("motivasi", 3),
    "perubahan": ("motivasi", 3), "transformasi": ("motivasi", 4), "hebat": ("motivasi", 3),

    # ── FAKTA MENGEJUTKAN / EDUKASI ────────────────────────────
    "faktanya": ("fakta", 4), "ternyata": ("fakta", 3), "tau nggak": ("fakta", 4),
    "tau gak": ("fakta", 4), "gue kira": ("fakta", 3), "salah kaprah": ("fakta", 4),
    "penelitian": ("fakta", 3), "studi": ("fakta", 3), "ilmiah": ("fakta", 3),
    "terbukti": ("fakta", 3), "fakta": ("fakta", 3), "mitos": ("fakta", 4),
    "rahasia": ("fakta", 4), "bocoran": ("fakta", 5), "bocor": ("fakta", 4),
    "tersembunyi": ("fakta", 4), "dirahasiakan": ("fakta", 5), "dilarang": ("fakta", 4),
    "konspirasi": ("fakta", 4), "terungkap": ("fakta", 5), "terkuak": ("fakta", 5),

    # ── SINYAL REAKSI TINGGI (reaksi penonton) ─────────────────
    "aamiin": ("reaksi", 2), "setuju": ("reaksi", 2), "relate": ("reaksi", 4),
    "banget sih": ("reaksi", 4), "gue banget": ("reaksi", 5), "gua banget": ("reaksi", 5),
    "bener banget": ("reaksi", 4), "tepat banget": ("reaksi", 4),
    "ngehits": ("reaksi", 3), "viral": ("reaksi", 3), "trending": ("reaksi", 3),
    "share": ("reaksi", 2), "save": ("reaksi", 2), "bookmark": ("reaksi", 2),
    "komentar": ("reaksi", 2), "duet": ("reaksi", 3),
}

# Semua kata dalam lexicon (untuk backward compat)
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

# ════════════════════════════════════════════════════════════════
#  KOREKSI EJAAN BAHASA INDONESIA
# ════════════════════════════════════════════════════════════════
# Peta koreksi: kata informal/typo → kata baku EYD
_EJA = {
    # Vokal & huruf
    "gue":"saya", "gua":"saya", "lo":"kamu", "lu":"kamu",
    "ga":"tidak", "gak":"tidak", "nggak":"tidak", "enggak":"tidak",
    "udah":"sudah", "udeh":"sudah", "dah":"sudah",
    "aja":"saja", "aj":"saja",
    "emang":"memang", "emg":"memang",
    "kayak":"seperti", "kek":"seperti",
    "banget":"sekali", "bgt":"sekali",
    "bener":"benar", "bner":"benar",
    "mana":"mana", "gimana":"bagaimana", "gmn":"bagaimana",
    "kalo":"kalau", "klo":"kalau",
    "sampe":"sampai", "ampe":"sampai",
    "abis":"habis", "abish":"habis",
    "tau":"tahu", "tw":"tahu",
    "ngga":"tidak", "nga":"tidak",
    "trus":"terus", "trs":"terus",
    "buat":"untuk", "bt":"untuk",
    "ntar":"nanti", "tar":"nanti",
    "ntaps":"mantap", "mantep":"mantap",
    "keren":"keren", "krn":"karena", "krena":"karena",
    "dgn":"dengan", "dg":"dengan",
    "yg":"yang", "yng":"yang",
    "jd":"jadi", "jdnya":"jadinya",
    "tp":"tapi", "tapi":"tetapi",
    "hrs":"harus", "hrs":"harus",
    "skrg":"sekarang", "skrang":"sekarang",
    "blm":"belum", "blum":"belum",
    "sdh":"sudah", "sdah":"sudah",
    "org":"orang", "org2":"orang-orang",
    "byk":"banyak", "bnyk":"banyak",
    "spt":"seperti",
    "dll":"dan lain-lain", "dsb":"dan sebagainya",
    "utk":"untuk", "untk":"untuk",
    "ttg":"tentang", "tntg":"tentang",
    "pd":"pada",
    "dr":"dari",
    "dlm":"dalam",
    "scr":"secara",
    "jg":"juga", "jga":"juga",
    "ny":"nya",
    "bs":"bisa", "bsa":"bisa",
    "msh":"masih", "msih":"masih",
    "bikin":"membuat",
    "ngomong":"berbicara", "ngmg":"berbicara",
    "bilang":"mengatakan",
    "ngeliat":"melihat", "liat":"melihat",
    "ngerasa":"merasa",
    "ngaku":"mengaku",
    "nanya":"bertanya",
    "jawab":"menjawab",
    "balik":"kembali",
    "dateng":"datang",
    "pergi":"pergi",
    "ketemu":"bertemu",
    "nyebut":"menyebut",
    "nyoba":"mencoba",
    "mikir":"berpikir",
    "nemu":"menemukan",
    "bawa":"membawa",
    "kasih":"memberikan",
    "ambil":"mengambil",
    "makin":"semakin",
    "hampir":"hampir",
    "cuma":"hanya",
    "kok":"mengapa",
    "sih":"sebenarnya",
    "dong":"ya",
    "deh":"lah",
    "nih":"ini",
    "tuh":"itu",
    "wkwk":"(tertawa)",
    "haha":"(tertawa)",
    "hehe":"(tersenyum)",
    "lol":"(tertawa)",
    "btw":"omong-omong",
    "fyi":"untuk diketahui",
    "ok":"oke",
    "oke":"oke",
    "yep":"ya",
    "yups":"ya",
    "nope":"tidak",
}

def koreksi_ejaan(teks: str) -> str:
    """Koreksi kata informal → bahasa Indonesia baku, pertahankan kapitalisasi awal kalimat."""
    if not teks:
        return teks
    kata_list = teks.split()
    hasil = []
    for i, kata in enumerate(kata_list):
        # Pisahkan tanda baca di akhir
        suffix = ""
        base   = kata
        while base and base[-1] in ".,!?;:":
            suffix = base[-1] + suffix
            base   = base[:-1]

        lower = base.lower()
        if lower in _EJA:
            ganti = _EJA[lower]
            # Pertahankan huruf kapital jika kata asli kapital atau awal kalimat
            if base and base[0].isupper():
                ganti = ganti[0].upper() + ganti[1:]
            hasil.append(ganti + suffix)
        else:
            hasil.append(kata)

    teks_hasil = " ".join(hasil)
    # Kapitalisasi awal kalimat setelah . ! ?
    teks_hasil = re.sub(r'([.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), teks_hasil)
    # Kapital huruf pertama
    if teks_hasil:
        teks_hasil = teks_hasil[0].upper() + teks_hasil[1:]
    return teks_hasil


def segment_subtitle(teks: str, maks_char: int = 42) -> list[str]:
    """
    Pecah teks menjadi baris subtitle yang rapi:
    - Maks karakter per baris
    - Potong di kata, bukan di tengah kata
    - Maksimal 2 baris per subtitle
    """
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

    # Gabung maks 2 baris per subtitle
    hasil = []
    for i in range(0, len(baris), 2):
        chunk = baris[i:i+2]
        hasil.append("\n".join(chunk))
    return hasil


# ════════════════════════════════════════════════════════════════
#  ENV DETECTION
# ════════════════════════════════════════════════════════════════
def is_cloud() -> bool:
    return (
        os.path.exists("/mount/src") or
        os.environ.get("STREAMLIT_SHARING_MODE") is not None
    )

IS_CLOUD = is_cloud()

# ════════════════════════════════════════════════════════════════
#  YT-DLP — tanpa test cookies (PC lokal)
# ════════════════════════════════════════════════════════════════
def _ydl_opts(extra: dict = None) -> dict:
    opts = {
        "quiet":             True,
        "no_warnings":       True,
        "extractor_retries": 3,
        "socket_timeout":    30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    }

    if IS_CLOUD:
        if os.path.exists(COOKIES_FILE):
            opts["cookiefile"] = COOKIES_FILE
    else:
        # PC Lokal: cek folder browser ada atau tidak — TANPA inisialisasi YoutubeDL
        browser_dirs = {
            "chrome":  os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data"),
            "edge":    os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\User Data"),
            "brave":   os.path.expanduser(r"~\AppData\Local\BraveSoftware\Brave-Browser\User Data"),
            "firefox": os.path.expanduser(r"~\AppData\Roaming\Mozilla\Firefox"),
        }
        # Prioritaskan cookies.txt manual jika ada
        if os.path.exists(COOKIES_FILE):
            opts["cookiefile"] = COOKIES_FILE
        else:
            for browser, path in browser_dirs.items():
                if os.path.exists(path):
                    opts["cookiesfrombrowser"] = (browser,)
                    break

    if extra:
        opts.update(extra)
    return opts


def get_video_info(url: str) -> dict:
    with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
        return ydl.extract_info(url, download=False)


def get_stream_urls(url: str) -> tuple:
    format_attempts = [
        "bestvideo[height<=720]+bestaudio/bestvideo+bestaudio",
        "bestvideo[height<=480]+bestaudio/bestvideo+bestaudio",
        "best[height<=720]/best",
        "best",
    ]
    info, last_err = None, None
    for fmt in format_attempts:
        try:
            with yt_dlp.YoutubeDL(_ydl_opts({"format": fmt})) as ydl:
                info = ydl.extract_info(url, download=False)
            break
        except Exception as e:
            last_err = e
    if info is None:
        raise RuntimeError(f"Semua format gagal: {last_err}")
    if "requested_formats" in info:
        v_url = next((f["url"] for f in info["requested_formats"] if f.get("vcodec") != "none"), None)
        a_url = next((f["url"] for f in info["requested_formats"] if f.get("acodec") != "none"), None)
        return v_url or info.get("url",""), a_url or v_url or info.get("url","")
    direct = info.get("url","")
    return direct, direct


# ════════════════════════════════════════════════════════════════
#  AUDIO DOWNLOAD
# ════════════════════════════════════════════════════════════════
def download_audio_only(source_url: str, duration: float, max_sec: int = 600) -> str:
    out_base = os.path.join(TMP_DIR, f"audio_{uuid.uuid4().hex[:6]}")
    out_wav  = out_base + ".wav"
    limit    = min(duration, max_sec)

    ydl_audio_opts = _ydl_opts({
        "format":      "bestaudio/best",
        "outtmpl":     out_base + ".%(ext)s",
        "quiet":       True,
        "no_warnings": True,
        "postprocessors": [{
            "key":              "FFmpegExtractAudio",
            "preferredcodec":   "wav",
            "preferredquality": "0",
        }],
        "postprocessor_args": {
            "FFmpegExtractAudio": ["-ar", "16000", "-ac", "1", "-t", str(int(limit))],
        },
    })

    try:
        with yt_dlp.YoutubeDL(ydl_audio_opts) as ydl:
            ydl.download([source_url])
    except Exception as e:
        err = str(e)
        if "403" in err or "Forbidden" in err:
            raise RuntimeError(
                "❌ YouTube 403 Forbidden.\n"
                "Upload cookies.txt di sidebar (export dari Chrome/Edge yang sudah login YouTube)."
            )
        raise RuntimeError(f"yt-dlp audio download gagal: {e}")

    if not os.path.exists(out_wav):
        candidates = glob.glob(out_base + ".*")
        if not candidates:
            raise RuntimeError("File audio tidak ditemukan setelah download.")
        src = candidates[0]
        if src != out_wav:
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", out_wav],
                capture_output=True, timeout=120
            )
            try:
                os.remove(src)
            except Exception:
                pass
            if r.returncode != 0:
                raise RuntimeError(f"Konversi WAV gagal: {r.stderr.decode()[:200]}")

    if not os.path.exists(out_wav) or os.path.getsize(out_wav) < 1000:
        raise RuntimeError("File audio kosong atau tidak valid.")
    return out_wav


# ════════════════════════════════════════════════════════════════
#  WHISPER
# ════════════════════════════════════════════════════════════════
@st.cache_resource
def load_whisper(model_size: str):
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe_audio(audio_path: str, model_size: str = "tiny", koreksi: bool = True) -> tuple:
    model  = load_whisper(model_size)
    raw, _ = model.transcribe(
        audio_path, beam_size=1, vad_filter=True,
        word_timestamps=True, language="id",
    )
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
                    wc_fix = koreksi_ejaan(wc) if koreksi else wc
                    words.append({"start": w.start, "end": w.end, "word": wc_fix})
    return segments, words


# ════════════════════════════════════════════════════════════════
#  SCORING ENGINE — Multi-sinyal, deteksi emosi per kategori
# ════════════════════════════════════════════════════════════════

# Emoji label per kategori untuk UI
EMOTION_EMOJI = {
    "komedi":   "😂", "horror":  "👻", "kaget":   "😱",
    "haru":     "😢", "drama":   "🔥", "motivasi": "💪",
    "fakta":    "🤯", "reaksi":  "💬", "campuran": "⭐",
}

# Bobot komponen scoring final (harus jumlah 1.0)
SCORE_WEIGHTS = {
    "emosi":      0.40,   # skor kata emosional dari lexicon (utama)
    "energi":     0.20,   # RMS audio — keras / ramai
    "density":    0.15,   # kepadatan kata per detik (bicara padat = momen isi)
    "spike":      0.15,   # ada lonjakan energi mendadak (tawa/kaget/reaksi)
    "struktur":   0.10,   # bonus: kalimat lengkap, ada "karena/tapi/ternyata"
}

def _scan_emotions(text: str) -> dict:
    """
    Scan teks, kembalikan skor per kategori emosi dan total bobot.
    Mendukung frasa multi-kata (misal: 'nggak nyangka').
    """
    lower   = text.lower()
    cat_sc  : dict[str, int] = {}
    total_w = 0

    # Urutkan kunci dari terpanjang ke terpendek agar frasa diprioritaskan
    for phrase in sorted(EMOTION_LEXICON, key=len, reverse=True):
        if phrase in lower:
            cat, w    = EMOTION_LEXICON[phrase]
            cat_sc[cat] = cat_sc.get(cat, 0) + w
            total_w  += w

    return cat_sc, total_w


def _tempo_score(y: np.ndarray, sr: int, t_start: float, t_end: float) -> float:
    """
    Hitung 'kepadatan berbicara' dalam segmen:
    RMS variance tinggi + banyak zero-crossing = banyak konsonan = bicara cepat/ramai.
    """
    s = int(t_start * sr)
    e = int(t_end   * sr)
    seg = y[s:e]
    if len(seg) < sr * 0.5:
        return 0.0
    zcr  = float(np.mean(librosa.feature.zero_crossing_rate(seg)))
    rmsv = float(np.std(librosa.feature.rms(y=seg, hop_length=512)[0]))
    return min(1.0, zcr * 5 + rmsv * 20)


def _spike_score(rms_norm: np.ndarray, times: np.ndarray,
                 t_start: float, t_end: float) -> float:
    """
    Deteksi lonjakan energi mendadak dalam window.
    Ini sinyal kuat untuk: tawa meledak, kaget, teriak, momen inti.
    """
    mask  = (times >= t_start) & (times <= t_end)
    chunk = rms_norm[mask]
    if len(chunk) < 3:
        return 0.0
    diff  = np.diff(chunk)
    # Lonjakan = kenaikan drastis dalam 1–2 frame
    big_jumps = float(np.sum(diff > 0.25))
    max_jump  = float(diff.max()) if len(diff) else 0.0
    return min(1.0, big_jumps * 0.2 + max_jump)


def _struktur_score(segs_in_window: list) -> float:
    """
    Bonus struktur narasi: ada kata transisi, pertanyaan, penegasan,
    atau pembuka storytelling = penonton lebih mungkin nonton sampai habis.
    """
    TRANSISI  = ["ternyata","padahal","tapi","karena","jadi","akhirnya",
                  "tiba-tiba","setelah itu","waktu itu","pas itu"]
    PERTANYAAN = ["kenapa","bagaimana","gimana","apa","siapa","kapan","berapa"]
    PENEGASAN  = ["beneran","serius","jujur","percaya","yakin","pasti","memang"]
    PEMBUKA    = ["jadi ceritanya","suatu hari","gue pernah","waktu gue",
                  "gue mau cerita","ini kisah","lo tau gak","kalian tau"]

    skor   = 0.0
    gabung = " ".join(s["text"].lower() for s in segs_in_window)

    for w in TRANSISI:
        if w in gabung: skor += 0.08
    for w in PERTANYAAN:
        if w in gabung: skor += 0.05
    for w in PENEGASAN:
        if w in gabung: skor += 0.06
    for w in PEMBUKA:
        if w in gabung: skor += 0.12

    return min(1.0, skor)


def score_clips(audio_path: str, segments: list, duration: float,
                n_clips: int, min_dur: int, max_dur: int,
                filter_kategori: str = "semua") -> list:
    """
    Scoring multi-sinyal dengan deteksi emosi per kategori.

    filter_kategori: 'semua' | 'komedi' | 'horror' | 'kaget' |
                     'haru'  | 'drama'  | 'motivasi' | 'fakta'
    """
    import librosa

    y, sr  = librosa.load(audio_path, mono=True, sr=None)
    hop    = 512
    rms    = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_n  = (rms - rms.min()) / (rms.max() - rms.min() + 1e-9)
    times  = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    # Bangun index segmen per detik untuk lookup cepat
    max_t  = min(duration, float(times[-1]) if len(times) else duration)
    step   = max(3, min_dur // 4)   # step lebih halus = kandidat lebih banyak

    candidates = []

    for sf in np.arange(0, max_t - min_dur, step):
        # Durasi klip: random dalam [min_dur, max_dur], tapi juga coba titik pas setelah
        # lonjakan energi — sehingga klip mulai agak sebelum momen puncak
        ef = min(float(sf) + random.randint(min_dur, max_dur), duration)
        if ef - sf < min_dur:
            continue

        # ── 1. Skor emosi dari transkripsi ──────────────────────
        segs_win = [s for s in segments if not (s["end"] < sf or s["start"] > ef)]
        gabung   = " ".join(s["text"] for s in segs_win)
        cat_sc, emosi_raw = _scan_emotions(gabung)

        # Normalisasi emosi ke 0–1 (cap di 30 poin bobot)
        emosi_norm = min(1.0, emosi_raw / 30.0)

        # Dominan kategori
        dom_cat = max(cat_sc, key=cat_sc.get) if cat_sc else "campuran"

        # Filter kategori jika dipilih user
        if filter_kategori != "semua" and dom_cat != filter_kategori:
            continue

        # Preview: pilih kalimat dengan bobot emosi tertinggi di window
        best_preview, best_w = "—", 0
        for seg in segs_win:
            _, w = _scan_emotions(seg["text"])
            if w > best_w:
                best_w       = w
                best_preview = seg["text"]

        # ── 2. Energi audio (RMS mean) ──────────────────────────
        mask   = (times >= sf) & (times <= ef)
        e_mean = float(rms_n[mask].mean()) if mask.any() else 0.0

        # ── 3. Kepadatan bicara ─────────────────────────────────
        density = _tempo_score(y, sr, sf, ef)

        # ── 4. Lonjakan mendadak (spike) ────────────────────────
        spike = _spike_score(rms_n, times, sf, ef)

        # ── 5. Struktur narasi ──────────────────────────────────
        struktur = _struktur_score(segs_win)

        # ── Skor gabungan ───────────────────────────────────────
        total = (
            emosi_norm * SCORE_WEIGHTS["emosi"]
            + e_mean   * SCORE_WEIGHTS["energi"]
            + density  * SCORE_WEIGHTS["density"]
            + spike    * SCORE_WEIGHTS["spike"]
            + struktur * SCORE_WEIGHTS["struktur"]
        )

        # Bonus kategori premium (horror & kaget → sangat viral)
        if dom_cat in ("horror", "kaget"):
            total = min(1.0, total * 1.20)
        elif dom_cat in ("komedi", "drama"):
            total = min(1.0, total * 1.10)

        candidates.append({
            "start":    float(sf),
            "end":      float(ef),
            "score":    total,
            "energy":   e_mean,
            "spike":    spike,
            "density":  density,
            "emosi":    emosi_norm,
            "struktur": struktur,
            "kategori": dom_cat,
            "cat_detail": cat_sc,   # skor per kategori untuk debug/UI
            "keywords": emosi_raw,
            "preview":  best_preview.strip(),
            "label":    f"{int(sf//60):02d}:{int(sf%60):02d} – {int(ef//60):02d}:{int(ef%60):02d}",
        })

    # Sort by score desc
    candidates.sort(key=lambda x: -x["score"])

    # Deduplikasi: tolak klip yang tumpang tindih > 50% dengan yang sudah dipilih
    selected = []
    for c in candidates:
        overlap = any(
            min(c["end"], s["end"]) - max(c["start"], s["start"])
            > (c["end"] - c["start"]) * 0.50
            for s in selected
        )
        if not overlap:
            selected.append(c)
        if len(selected) >= n_clips:
            break

    return selected


# ════════════════════════════════════════════════════════════════
#  HASHTAG GENERATOR — FYP Optimized
# ════════════════════════════════════════════════════════════════
# Hashtag FYP inti — selalu disertakan
FYP_CORE_TAGS = [
    "#fyp","#fypシ","#foryou","#foryoupage","#viral","#trending",
    "#podcastindonesia","#podcast","#kontenkreatif","#shorts","#reels","#tiktok",
]

# Hashtag niche berdasarkan isi konten
NICHE_MAP = {
    "motivasi":   ["#motivasi","#motivasihari","#semangat","#inspirasi","#quotes","#quotesindo"],
    "drama":      ["#drama","#storytime","#curhat","#cerita","#kisahnyata","#pengalaman"],
    "edukasi":    ["#edukasi","#belajar","#fakta","#faktaunik","#ilmupengetahuan","#tips"],
    "komedi":     ["#lucu","#ngakak","#hiburan","#comedy","#receh","#meme"],
    "horror":     ["#horror","#serem","#mistis","#hantuin","#creepy","#lenteramalam"],
    "bisnis":     ["#bisnis","#entrepreneur","#usaha","#sukses","#finansial","#investasi"],
    "relationship":["#relationship","#cinta","#pasangan","#toxic","#bucin","#galau"],
}

def detect_niche(segments: list) -> str:
    """Deteksi niche dominan menggunakan emotion lexicon."""
    if not segments:
        return "motivasi"
    full = " ".join(s["text"] for s in segments)
    cat_sc, _ = _scan_emotions(full)
    if not cat_sc:
        return "motivasi"
    # Map kategori emosi → niche
    emo_to_niche = {
        "komedi": "komedi", "horror": "horror", "kaget": "kaget",
        "haru": "drama", "drama": "drama", "motivasi": "motivasi",
        "fakta": "edukasi", "reaksi": "motivasi",
    }
    dom = max(cat_sc, key=cat_sc.get)
    return emo_to_niche.get(dom, "motivasi")


def generate_hashtags(segments: list, title: str) -> str:
    title_words = re.findall(r"[a-zA-Z0-9]{3,}", title)
    title_tags  = ["#" + w.lower() for w in title_words
                   if w.lower() not in STOPWORDS and len(w) >= 3][:5]

    niche        = detect_niche(segments)
    niche_tags   = NICHE_MAP.get(niche, [])

    specific_tags = []
    if segments:
        full_text  = " ".join(s["text"] for s in segments)
        lower_words = [w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", full_text)]
        freq        = Counter(w for w in lower_words if w not in STOPWORDS)
        specific    = sorted(
            [w for w, c in freq.items() if 2 <= c <= 8 and len(w) >= 5],
            key=lambda w: freq[w], reverse=True
        )[:4]
        specific_tags = ["#" + w for w in specific]

    all_tags = FYP_CORE_TAGS + niche_tags + title_tags + specific_tags
    seen, final = set(), []
    for t in all_tags:
        if t not in seen:
            seen.add(t)
            final.append(t)

    return " ".join(final[:30])


def generate_caption_fyp(segments: list, title: str, url: str, fyp_info: dict) -> str:
    """Buat caption yang FYP-friendly: hook + isi + CTA + hashtag."""
    hashtags = generate_hashtags(segments, title)

    # Hook opening
    if segments:
        opening = segments[0]["text"][:80]
        hook    = f'🎙️ "{opening}..."'
    else:
        hook = f'🎙️ {title}'

    # CTA berdasarkan jam
    cw = fyp_info.get("current_window")
    if cw and "Prime Time" in cw["label"]:
        cta = "⭐ Tonton sekarang — ini jam prime time! Drop komen kamu 👇"
    elif cw and "Pagi" in cw["label"]:
        cta = "☕ Konten pagi yang bikin hari kamu lebih bermakna. Share ke teman!"
    elif cw and "Sore" in cw["label"]:
        cta = "🌆 Sambil santai sore, tonton ini dulu. Komen kalau relate!"
    elif cw and "Late Night" in cw["label"]:
        cta = "🦉 Buat yang masih melek — ini buat kamu. Save dulu, baru tidur!"
    else:
        cta = "💬 Komen kalau relate. Save kalau bermanfaat!"

    caption = f"""{hook}

{cta}

🎧 Dengarkan full episode:
{url}

{hashtags}"""
    return caption.strip()


# ════════════════════════════════════════════════════════════════
#  COLOR GRADING
# ════════════════════════════════════════════════════════════════
def make_grade_fn(style: str):
    if style == "warm":
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f - 128) * 1.15 + 135, 0, 255)
            f[:, :, 0] = np.clip(f[:, :, 0] * 1.10, 0, 255)
            f[:, :, 2] = np.clip(f[:, :, 2] * 0.90, 0, 255)
            return f.astype(np.uint8)
    elif style == "noir":
        def fn(f):
            f = f.astype(np.float32)
            g = f.mean(axis=2, keepdims=True)
            return np.clip((g * np.ones_like(f) - 128) * 1.45 + 128, 0, 255).astype(np.uint8)
    elif style == "vibrant":
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f - 128) * 1.3 + 128, 0, 255)
            g = f.mean(axis=2, keepdims=True)
            return np.clip(f * 1.15 - g * 0.15, 0, 255).astype(np.uint8)
    else:  # sinematik
        def fn(f):
            f = f.astype(np.float32)
            f = np.clip((f - 128) * 1.2 + 128, 0, 255)
            g = f.mean(axis=2, keepdims=True)
            f = f * 0.85 + g * 0.15
            f[:, :, 0] = np.clip(f[:, :, 0] * 0.94, 0, 255)
            f[:, :, 2] = np.clip(f[:, :, 2] * 1.04, 0, 255)
            return f.astype(np.uint8)
    return fn


# ════════════════════════════════════════════════════════════════
#  SUBTITLE — rapi, EYD, penempatan presisi
# ════════════════════════════════════════════════════════════════
def _tc(text: str, size: int, color: str, stroke_w: int, dur: float,
        width: int = 960, bg_opacity: float = 0.0) -> TextClip | None:
    if not FONT_PATH:
        return None
    try:
        clip = TextClip(
            text=text, font_size=size, color=color, font=FONT_PATH,
            stroke_color="black", stroke_width=stroke_w,
            size=(width, None), method="caption", duration=dur,
        )
        return clip
    except Exception:
        return None


def subs_tiktok_rapi(words: list, cs: float, ce: float,
                     sub_y: int, color: str, video_w: int = 1080) -> list:
    """
    Subtitle TikTok per kata — rapi, kapital huruf pertama, tidak overflow.
    Kata dikelompokkan 2–3 kata per frame agar lebih nyaman dibaca.
    """
    layers = []
    dur    = ce - cs

    # Kelompokkan kata 2–3 per tampilan
    grup_kata, i = [], 0
    while i < len(words):
        w = words[i]
        if w["start"] < cs or w["end"] > ce:
            i += 1
            continue
        # Ambil 2 kata sekaligus jika jeda pendek
        if i + 1 < len(words):
            w2 = words[i + 1]
            if w2["start"] - w["end"] < 0.3 and w2["end"] <= ce:
                grup_kata.append((w["start"], w2["end"],
                                  w["word"].capitalize() + " " + w2["word"]))
                i += 2
                continue
        grup_kata.append((w["start"], w["end"], w["word"].capitalize()))
        i += 1

    for (t0_abs, t1_abs, teks) in grup_kata:
        t0 = max(t0_abs - cs, 0)
        t1 = min(t1_abs - cs, dur)
        if t1 - t0 < 0.05:
            continue
        tc = _tc(teks.upper(), 88, color, 5, t1 - t0, video_w - 60)
        if tc:
            layers.append(tc.with_start(t0).with_position(("center", sub_y)))
    return layers


def subs_kalimat_rapi(segments: list, cs: float, ce: float,
                      sub_y: int, color: str, video_w: int = 1080) -> list:
    """
    Subtitle per kalimat — potong rapi maks 42 karakter/baris, maks 2 baris.
    Ejaan sudah dikoreksi dari transcribe.
    """
    layers = []
    dur    = ce - cs

    for seg in segments:
        if seg["end"] < cs or seg["start"] > ce:
            continue
        t0 = max(seg["start"] - cs, 0)
        t1 = min(seg["end"]   - cs, dur)
        if t1 - t0 < 0.05:
            continue

        baris_list = segment_subtitle(seg["text"], maks_char=42)
        for baris in baris_list:
            # Hitung durasi proporsional per baris
            fraksi   = len(baris) / max(len(seg["text"]), 1)
            dur_baris = max(0.5, (t1 - t0) * fraksi)
            tc = _tc(baris, 52, color, 3, min(dur_baris, t1 - t0), video_w - 80)
            if tc:
                layers.append(tc.with_start(t0).with_position(("center", sub_y)))
    return layers


# ════════════════════════════════════════════════════════════════
#  RENDER
# ════════════════════════════════════════════════════════════════
def render_clip(
    video_url, audio_url, start, end, segments, words, *,
    use_subs, sub_style, sub_position, sub_color,
    use_grade, grade_style,
    use_hook, hook_text,
    use_bgm, watermark_path,
    output_name="",
) -> str:
    dur      = end - start
    tmp_clip = os.path.join(TMP_DIR, f"raw_{uuid.uuid4().hex[:6]}.mp4")

    st.caption("⏬ Mengambil segmen dari stream...")
    if video_url == audio_url:
        cmd = [
            "ffmpeg", "-y",
            "-user_agent", "Mozilla/5.0",
            "-ss", str(start), "-i", video_url,
            "-t", str(dur), "-c", "copy", tmp_clip,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-user_agent", "Mozilla/5.0",
            "-ss", str(start), "-i", video_url,
            "-ss", str(start), "-i", audio_url,
            "-t", str(dur),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", tmp_clip,
        ]

    r = subprocess.run(cmd, capture_output=True, timeout=180)
    if r.returncode != 0 or not os.path.exists(tmp_clip):
        st.caption("⚠️ Fallback re-encode...")
        cmd2 = [
            "ffmpeg", "-y",
            "-user_agent", "Mozilla/5.0",
            "-ss", str(start), "-i", video_url,
            "-t", str(dur),
            "-c:v", "libx264", "-c:a", "aac", tmp_clip,
        ]
        subprocess.run(cmd2, capture_output=True, timeout=300)

    if not os.path.exists(tmp_clip) or os.path.getsize(tmp_clip) < 1000:
        raise RuntimeError("Segmen kosong — stream URL mungkin sudah kadaluarsa, coba muat ulang.")

    st.caption("🎨 Menerapkan efek & subtitle...")
    clip  = VideoFileClip(tmp_clip)
    final = clip.copy()

    w, h  = final.size
    # Crop ke 9:16 lalu resize ke 1080x1920
    crop_w = int(h * 9 / 16)
    final  = final.with_effects([
        vfx.Crop(x_center=w / 2, width=crop_w, height=h),
        vfx.Resize((1080, 1920)),
    ])
    fw, fh = final.size  # 1080 x 1920

    if use_grade:
        final = final.image_transform(make_grade_fn(grade_style))

    layers = [final]

    if use_subs and FONT_PATH:
        # Zona aman subtitle: bawah = y 1580, atas = y 160
        safe_bottom = 1580
        safe_top    = 160
        sub_y       = safe_bottom if sub_position == "Bawah" else safe_top

        if "TikTok" in sub_style and words:
            layers.extend(subs_tiktok_rapi(words, start, end, sub_y, sub_color, fw))
        else:
            layers.extend(subs_kalimat_rapi(segments, start, end, sub_y, sub_color, fw))

    if use_hook and FONT_PATH:
        h_text = hook_text.strip() or random.choice(HOOK_POOL)
        tc = _tc(h_text, 46, "#FFD700", 3, 3.5, fw - 80)
        if tc:
            # Hook di atas, zona aman y=140
            layers.append(tc.with_start(0).with_position(("center", 140)))

    if watermark_path and os.path.exists(watermark_path):
        try:
            wm = (
                ImageClip(watermark_path)
                .with_effects([vfx.Resize(width=180)])
                .with_opacity(0.70)
                .with_duration(final.duration)
                .with_position((fw - 200, 40))
            )
            layers.append(wm)
        except Exception:
            pass

    if len(layers) > 1:
        final = CompositeVideoClip(layers)

    if use_bgm and os.path.exists(BGM_PATH):
        try:
            bgm  = (AudioFileClip(BGM_PATH)
                    .with_effects([afx.MultiplyVolume(0.15)])
                    .with_duration(final.duration))
            orig = final.audio
            final = final.with_audio(CompositeAudioClip([orig, bgm]) if orig else bgm)
        except Exception:
            pass

    safe = re.sub(r"[^\w]", "_", output_name)[:40] if output_name else uuid.uuid4().hex[:8]
    out  = os.path.join(OUTPUT_DIR, f"{safe}.mp4")

    final.write_videofile(
        out, codec="libx264", bitrate="10000k", fps=30, logger=None,
        ffmpeg_params=[
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-level", "4.1",
            "-movflags", "+faststart",
        ],
    )
    clip.close()
    try:
        os.remove(tmp_clip)
    except Exception:
        pass
    return out


# ════════════════════════════════════════════════════════════════
#  UI
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="🎙️ Podcast Clipper Pro", layout="wide", page_icon="🎙️")

st.title("🎙️ Podcast Clipper Pro")
st.caption("Tempel link YouTube → AI deteksi momen terbaik → potong otomatis → langsung siap upload TikTok / Reels / Shorts")

# ── Mode badge ───────────────────────────────────────────────────
if IS_CLOUD:
    st.info("☁️ **Mode: Streamlit Cloud** — Upload cookies.txt YouTube di sidebar untuk mulai.", icon="☁️")
else:
    st.success("💻 **Mode: PC Lokal** — Cookies browser auto-detect. Langsung tempel link!", icon="✅")

# ════════════════════════════════════════════════════════════════
#  PANEL JAM FYP — ditampilkan di atas halaman
# ════════════════════════════════════════════════════════════════
fyp_info = get_fyp_status()
now_wib  = fyp_info["now"]
cw       = fyp_info["current_window"]
nw       = fyp_info["next_window"]
mnt      = fyp_info["minutes_to_next"]

with st.container(border=True):
    st.markdown(f"### 🕐 Jam Sekarang (WIB): **{now_wib.strftime('%H:%M')}**")

    if cw:
        st.success(
            f"✅ **{cw['label']}** — Kamu sedang di jam FYP!\n\n"
            f"_{cw['desc']}_\n\n"
            f"**🚀 Upload sekarang untuk maksimalkan jangkauan!**",
            icon="🔥",
        )
    else:
        jam_berikutnya = f"{nw['range'][0]:02d}:00" if nw else "—"
        sisa_jam  = mnt // 60
        sisa_mnt  = mnt % 60
        sisa_str  = (f"{sisa_jam}j {sisa_mnt}m" if sisa_jam else f"{sisa_mnt} menit") if mnt else "—"
        st.warning(
            f"⏳ **Belum masuk jam FYP.**\n\n"
            f"Window berikutnya: **{nw['label'] if nw else '—'}** pukul **{jam_berikutnya}** "
            f"_(sekitar {sisa_str} lagi)_\n\n"
            f"_{nw['desc'] if nw else ''}_",
            icon="⏳",
        )

    # Timeline semua window
    st.markdown("**Jadwal Jam FYP Hari Ini:**")
    cols = st.columns(len(FYP_WINDOWS))
    for idx, win in enumerate(FYP_WINDOWS):
        s, e   = win["range"]
        aktif  = cw and cw["label"] == win["label"]
        jam_str = f"{s:02d}:00–{e:02d}:00"
        with cols[idx]:
            if aktif:
                st.markdown(
                    f"<div style='background:#1a6b1a;padding:8px;border-radius:8px;"
                    f"text-align:center;font-size:12px'>"
                    f"<b>{win['label']}</b><br>{jam_str}<br>🔴 LIVE</div>",
                    unsafe_allow_html=True,
                )
            else:
                sudah_lewat = now_wib.hour >= e
                warna = "#333" if sudah_lewat else "#1a3a5c"
                st.markdown(
                    f"<div style='background:{warna};padding:8px;border-radius:8px;"
                    f"text-align:center;font-size:12px'>"
                    f"<b>{win['label']}</b><br>{jam_str}</div>",
                    unsafe_allow_html=True,
                )

st.markdown("")

# ════════════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════════════
with st.sidebar:

    # ── Cookies ──────────────────────────────────────────────────
    st.header("🍪 YouTube Cookies")
    if os.path.exists(COOKIES_FILE):
        st.success("✅ cookies.txt aktif")
        if st.button("🗑️ Hapus cookies"):
            os.remove(COOKIES_FILE)
            st.rerun()
    else:
        if IS_CLOUD:
            st.error("❌ Belum ada cookies — YouTube akan 403")
        else:
            st.info("ℹ️ Auto-detect browser. Upload cookies.txt manual jika gagal.")

        st.markdown("""
**Cara export cookies.txt:**
1. Install ekstensi **Get cookies.txt LOCALLY** di Chrome/Edge
2. Buka [youtube.com](https://youtube.com) — pastikan **sudah login**
3. Klik ekstensi → **Export** → simpan `cookies.txt`
4. Upload di bawah ↓
        """)

    cookies_up = st.file_uploader("Upload cookies.txt", type=["txt"])
    if cookies_up:
        with open(COOKIES_FILE, "wb") as fh:
            fh.write(cookies_up.read())
        st.success("✅ Cookies tersimpan!")
        st.rerun()

    st.divider()

    # ── Pengaturan klip ──────────────────────────────────────────
    st.subheader("⚙️ Pengaturan Klip")
    n_clips     = st.slider("Jumlah saran klip",        3, 12,  6)
    min_dur     = st.slider("Durasi minimum (detik)",  15, 60, 30)
    max_dur     = st.slider("Durasi maksimum (detik)", 30,180, 90)
    model_size  = st.selectbox("Model Whisper", ["tiny","base","small"], index=0,
                                help="tiny=cepat | base=seimbang | small=akurat (lambat)")
    analyze_max = st.slider("Analisis maks (menit)", 10, 60, 20,
                             help="Berapa menit pertama podcast yang dianalisis AI")
    koreksi_on  = st.checkbox("Koreksi Ejaan Otomatis (EYD)", value=True,
                               help="Ubah kata informal → bahasa Indonesia baku")

    st.divider()
    st.subheader("🎭 Filter Momen")
    st.caption("Pilih jenis momen yang ingin dicari AI:")
    filter_kat = st.selectbox(
        "Kategori emosi",
        options=["semua","komedi","horror","kaget","haru","drama","motivasi","fakta"],
        format_func=lambda x: {
            "semua":    "🎯 Semua (terbaik mix)",
            "komedi":   "😂 Komedi / Tawa",
            "horror":   "👻 Seram / Horror",
            "kaget":    "😱 Kaget / Plot Twist",
            "haru":     "😢 Haru / Menyentuh",
            "drama":    "🔥 Drama / Konflik",
            "motivasi": "💪 Motivasi / Inspirasi",
            "fakta":    "🤯 Fakta Mengejutkan",
        }[x],
        index=0,
    )
    st.session_state["filter_kat"] = filter_kat

    st.divider()
    st.subheader("🎨 Efek Video")
    use_grade   = st.checkbox("Color Grading", value=True)
    grade_style = st.selectbox(
        "Gaya Grading",
        ["sinematik", "warm", "vibrant", "noir"],
        disabled=not use_grade,
        help="sinematik=biru sejuk | warm=oranye hangat | vibrant=cerah | noir=hitam putih",
    )

    st.divider()
    st.subheader("💬 Subtitle Otomatis")
    use_subs     = st.checkbox("Auto Caption (Voice-to-Text)", value=True)
    sub_style    = st.selectbox(
        "Gaya Subtitle",
        ["🎬 TikTok — per kata, besar", "📝 Kalimat — klasik rapi"],
        disabled=not use_subs,
    )
    sub_position = st.selectbox("Posisi",      ["Bawah", "Atas"], disabled=not use_subs)
    sub_color    = st.selectbox("Warna Teks",  ["white", "yellow", "#FF3333", "#00FFFF"],
                                disabled=not use_subs)

    st.divider()
    st.subheader("🎣 Hook & BGM")
    use_hook    = st.checkbox("Hook Text (3 detik pertama)", value=True)
    custom_hook = st.text_input("Custom hook (kosong = otomatis)")
    use_bgm     = st.checkbox("BGM Latar", value=False)
    bgm_upload  = st.file_uploader("Upload BGM (.mp3)", type=["mp3"])
    if bgm_upload:
        with open(BGM_PATH, "wb") as fh:
            fh.write(bgm_upload.read())
        st.success("✅ BGM tersimpan!")
    st.caption("🎵 BGM aktif" if os.path.exists(BGM_PATH) else "Belum ada BGM.")

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
        chosen_wm = st.selectbox("Pilih watermark", ["(tidak pakai)"] + wm_files)
        st.session_state["watermark"] = (
            os.path.join(WM_DIR, chosen_wm) if chosen_wm != "(tidak pakai)" else None
        )
    else:
        st.caption("Belum ada watermark.")
        st.session_state.setdefault("watermark", None)

    st.divider()
    st.caption("**Platform yang didukung:** YouTube, Spotify (video), dan semua platform yang yt-dlp support.")


# ════════════════════════════════════════════════════════════════
#  MAIN — Input URL
# ════════════════════════════════════════════════════════════════
watermark_path = st.session_state.get("watermark")

if IS_CLOUD and not os.path.exists(COOKIES_FILE):
    st.warning("👈 Upload cookies.txt dulu di sidebar sebelum bisa tempel link YouTube.")
    st.stop()

st.subheader("🔗 Tempel Link YouTube / Podcast")

col_url, col_btn = st.columns([4, 1])
with col_url:
    input_url = st.text_input(
        "url", label_visibility="collapsed",
        placeholder="https://www.youtube.com/watch?v=...",
    )
with col_btn:
    btn_load = st.button("📡 Muat", use_container_width=True, type="primary")

if btn_load and input_url.strip():
    with st.spinner("📡 Mengambil info podcast..."):
        try:
            info = get_video_info(input_url.strip())
            st.session_state.update({
                "film_info":     info,
                "film_url":      input_url.strip(),
                "film_title":    info.get("title", "Unknown"),
                "film_duration": float(info.get("duration") or 0),
                "film_thumb":    info.get("thumbnail"),
                "film_channel":  info.get("channel") or info.get("uploader", ""),
            })
            for k in ["suggestions","segs","words","hashtags","video_url","audio_url"]:
                st.session_state.pop(k, None)
            st.rerun()
        except Exception as e:
            err = str(e)
            if "403" in err or "Forbidden" in err:
                st.error("❌ YouTube 403 — cookies.txt belum diupload atau sudah kadaluarsa.")
                st.info("Upload ulang cookies.txt di sidebar (export baru dari browser yang sudah login YouTube).")
            elif "Could not copy" in err or "cookie" in err.lower():
                st.error(
                    "❌ Gagal baca cookies browser (database sedang terkunci).\n\n"
                    "**Solusi:** Export cookies.txt secara manual menggunakan ekstensi "
                    "**Get cookies.txt LOCALLY** di Chrome/Edge, lalu upload di sidebar."
                )
            else:
                st.error(f"❌ Gagal memuat: {err}")

# ── Info podcast ──────────────────────────────────────────────────
if "film_title" in st.session_state:
    title    = st.session_state["film_title"]
    duration = st.session_state["film_duration"]
    thumb    = st.session_state.get("film_thumb")
    channel  = st.session_state.get("film_channel", "")
    url      = st.session_state["film_url"]

    st.markdown("---")
    col_t, col_m = st.columns([1, 3])
    with col_t:
        if thumb:
            st.image(thumb, use_container_width=True)
    with col_m:
        st.subheader(title)
        if channel:
            st.caption(f"📺 {channel}")
        dur_str = (
            f"{int(duration//3600)}j {int((duration%3600)//60)}m"
            if duration >= 3600
            else f"{int(duration//60)}m {int(duration%60)}d"
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("⏱️ Durasi",   dur_str)
        c2.metric("🔍 Analisis", f"{analyze_max} menit pertama")
        c3.metric("🖼️ WM",      "✅" if watermark_path else "❌")
        c4.metric("🔤 Font",     "✅" if FONT_PATH else "⚠️ Tidak ada")

    st.markdown("---")

    if st.button("🔍 Analisis Momen Terbaik (AI)", type="primary", use_container_width=True):
        try:
            with st.spinner(f"⏬ Mengunduh audio {analyze_max} menit pertama..."):
                audio_path = download_audio_only(url, duration, max_sec=analyze_max * 60)
                st.session_state["audio_path"] = audio_path

            with st.spinner("📡 Mengambil stream URL untuk render..."):
                v_url, a_url = get_stream_urls(url)
                st.session_state["video_url"] = v_url
                st.session_state["audio_url"] = a_url

            with st.spinner(f"🤖 Transkripsi AI ({model_size}) dengan koreksi ejaan..."):
                segs, words = transcribe_audio(audio_path, model_size, koreksi=koreksi_on)
                st.session_state["segs"]  = segs
                st.session_state["words"] = words

            with st.spinner("🎯 Penilaian momen terbaik..."):
                filter_kat = st.session_state.get("filter_kat", "semua")
                suggestions = score_clips(
                    audio_path, segs,
                    min(duration, analyze_max * 60),
                    n_clips, min_dur, max_dur,
                    filter_kategori=filter_kat,
                )
                hashtags = generate_hashtags(segs, title)
                st.session_state["suggestions"] = suggestions
                st.session_state["hashtags"]    = hashtags

            st.rerun()
        except Exception as e:
            st.error(f"❌ Analisis gagal: {e}")


# ── Hasil analisis ────────────────────────────────────────────────
if "suggestions" in st.session_state and "film_title" in st.session_state:
    suggestions = st.session_state["suggestions"]
    segs        = st.session_state.get("segs",  [])
    words       = st.session_state.get("words", [])
    hashtags    = st.session_state.get("hashtags", "")
    title       = st.session_state["film_title"]
    v_url       = st.session_state.get("video_url", "")
    a_url       = st.session_state.get("audio_url", "")
    duration    = st.session_state.get("film_duration", 0)
    url         = st.session_state["film_url"]

    # ── Caption & Hashtag FYP ─────────────────────────────────────
    caption_fyp = generate_caption_fyp(segs, title, url, fyp_info)
    hashtags    = generate_hashtags(segs, title)

    with st.container(border=True):
        t1, t2, t3 = st.tabs(["📋 Caption FYP Siap Pakai", "# Hashtag", "📊 Analisis Niche"])

        with t1:
            st.text_area("cap", caption_fyp, height=220, label_visibility="collapsed")
            st.caption("Salin langsung ke TikTok / Reels / YouTube Shorts")
            # Rekomendasi jam upload
            if cw:
                st.success(f"🔥 Sekarang jam FYP — **upload sekarang!** ({cw['label']})")
            else:
                jam_str = f"{nw['range'][0]:02d}:00" if nw else "—"
                st.info(f"⏳ Jadwalkan upload pukul **{jam_str} WIB** ({nw['label'] if nw else '—'}) untuk hasil terbaik.")

        with t2:
            st.text_area("ht", hashtags, height=120, label_visibility="collapsed")
            tags = [t for t in hashtags.split() if t.startswith("#")]
            c1, c2, c3 = st.columns(3)
            c1.metric("Total hashtag", len(tags))
            c2.metric("Niche terdeteksi", detect_niche(segs).capitalize())
            if c3.button("🔄 Generate Ulang"):
                st.session_state["hashtags"] = generate_hashtags(segs, title)
                st.rerun()

        with t3:
            niche = detect_niche(segs)
            st.markdown(f"**Niche konten:** `{niche.upper()}`")
            total_kw = sum(
                sum(1 for k in VIRAL_KEYWORDS if k in s["text"].lower())
                for s in segs
            )
            st.metric("Total kata viral terdeteksi", total_kw)
            if total_kw >= 15:
                st.success("🔥 Potensi viral tinggi!")
            elif total_kw >= 7:
                st.info("✅ Potensi viral sedang.")
            else:
                st.warning("⚠️ Kata viral sedikit — coba segmen yang lebih emosional.")

    # ── Preview transkripsi ───────────────────────────────────────
    if words:
        with st.expander(
            f"🔤 Preview Transkripsi — {len(words)} kata | {len(segs)} segmen (sudah dikoreksi EYD)",
            expanded=False,
        ):
            ca, cb = st.columns(2)
            ca.caption("**50 kata pertama + timing:**")
            ca.markdown(
                "  ".join(f"`{w['word']}` _{w['start']:.1f}d_" for w in words[:50])
                + (" …" if len(words) > 50 else "")
            )
            cb.caption("**Teks lengkap (600 karakter pertama):**")
            cb.caption(" ".join(s["text"] for s in segs)[:600] + "…")

    st.markdown("---")
    st.subheader(f"🎯 {len(suggestions)} Momen Terbaik Ditemukan")

    if not suggestions:
        st.warning("Tidak ada momen ditemukan. Coba kurangi durasi minimum atau tambah menit analisis.")
    else:
        def do_render(start, end, out_name):
            try:
                out = render_clip(
                    v_url, a_url, start, end, segs, words,
                    use_subs=use_subs,       sub_style=sub_style,
                    sub_position=sub_position, sub_color=sub_color,
                    use_grade=use_grade,     grade_style=grade_style,
                    use_hook=use_hook,       hook_text=custom_hook,
                    use_bgm=use_bgm,         watermark_path=watermark_path,
                    output_name=out_name,
                )
                st.success("✅ Selesai! Cek galeri di bawah.")
                st.balloons()
            except Exception as e:
                st.error(f"Render gagal: {e}")
                st.caption("Coba klik Muat ulang untuk memperbarui stream URL, lalu render lagi.")

        # Render semua sekaligus
        if len(suggestions) > 1 and st.button("🚀 Render SEMUA Klip Sekaligus", use_container_width=True):
            prog = st.progress(0, "Memulai...")
            for idx, sug in enumerate(suggestions):
                prog.progress(idx / len(suggestions), f"Merender klip #{idx+1}...")
                do_render(
                    sug["start"], sug["end"],
                    f"{re.sub(r'[^\\w]','_',title)[:25]}_klip{idx+1}",
                )
            prog.progress(1.0, "✅ Semua selesai!")
            st.balloons()
            st.rerun()

        # Per klip
        for i, sug in enumerate(suggestions):
            score_pct = int(sug["score"] * 100)
            kat       = sug.get("kategori", "campuran")
            emo_emoji = EMOTION_EMOJI.get(kat, "⭐")
            stars     = "⭐" * min(5, max(1, int(score_pct / 20)))

            with st.expander(
                f"**Klip #{i+1}** {emo_emoji} `{kat.upper()}` — {sug['label']} | {stars} {score_pct}%",
                expanded=(i == 0),
            ):
                # Baris metrik utama
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("⏱️ Durasi",     f"{int(sug['end']-sug['start'])} dtk")
                c2.metric("🎭 Emosi",      f"{int(sug.get('emosi',0)*100)}%")
                c3.metric("🔊 Energi",     f"{int(sug.get('energy',0)*100)}%")
                c4.metric("⚡ Spike",      f"{int(sug.get('spike',0)*100)}%")
                c5.metric("📊 Skor FYP",   f"{score_pct}%")

                # Breakdown kategori emosi terdeteksi
                cat_detail = sug.get("cat_detail", {})
                if cat_detail:
                    sorted_cats = sorted(cat_detail.items(), key=lambda x: -x[1])
                    badges = "  ".join(
                        f"{EMOTION_EMOJI.get(c,'⭐')} **{c}** ({w}pt)"
                        for c, w in sorted_cats[:4]
                    )
                    st.markdown(f"**Emosi terdeteksi:** {badges}")

                # Preview kalimat terkuat
                if sug.get("preview") and sug["preview"] != "—":
                    st.info(f'{emo_emoji} *"{sug["preview"]}"*')

                # Badge potensi FYP
                if score_pct >= 70:
                    st.success(f"🔥 Potensi viral TINGGI — prioritas upload! ({emo_emoji} {kat})")
                elif score_pct >= 45:
                    st.info(f"✅ Potensi sedang — layak diupload sebagai konten {kat}.")
                else:
                    st.warning("⚠️ Skor rendah — coba ganti filter kategori atau perluas menit analisis.")

                # Progress bar komponen
                with st.expander("🔬 Detail skor komponen", expanded=False):
                    komponen = {
                        "🎭 Emosi (40%)":       sug.get("emosi", 0),
                        "🔊 Energi audio (20%)": sug.get("energy", 0),
                        "💬 Kepadatan (15%)":    sug.get("density", 0),
                        "⚡ Lonjakan (15%)":     sug.get("spike", 0),
                        "📖 Struktur (10%)":     sug.get("struktur", 0),
                    }
                    for label, val in komponen.items():
                        st.progress(float(val), text=f"{label}: {int(val*100)}%")

                if st.button(f"🚀 Render Klip #{i+1}", key=f"r_{i}", use_container_width=True):
                    with st.spinner(f"Merender klip #{i+1}..."):
                        do_render(
                            sug["start"], sug["end"],
                            f"{re.sub(r'[^\\w]','_',title)[:25]}_klip{i+1}_{kat}",
                        )

        # Manual override
        st.markdown("---")
        with st.expander("✏️ Potong Manual — tentukan sendiri start & end"):
            cm1, cm2 = st.columns(2)
            m_s    = cm1.number_input("▶ Start (detik)", 0.0, float(duration or 9999), 0.0,  step=1.0, key="ms")
            m_e    = cm2.number_input("⏹ End (detik)",   0.0, float(duration or 9999), min(float(duration or 60), 90.0), step=1.0, key="me")
            m_name = st.text_input("Nama output", placeholder="nama_klip_kamu")
            if st.button("🚀 Render Manual", use_container_width=True):
                if m_e <= m_s:
                    st.error("End harus lebih besar dari Start!")
                else:
                    with st.spinner("Merender..."):
                        do_render(
                            m_s, m_e,
                            m_name.strip() or f"{re.sub(r'[^\\w]','_',title)[:25]}_manual",
                        )


# ════════════════════════════════════════════════════════════════
#  OUTPUT GALLERY
# ════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📁 Galeri Klip Hasil")

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
            c2.download_button(
                "⬇️ Unduh", fh, file_name=f,
                mime="video/mp4", key=f"dl_{f}", use_container_width=True,
            )
        if c3.button("🗑️ Hapus", key=f"del_{f}", use_container_width=True):
            os.remove(fpath)
            st.rerun()
