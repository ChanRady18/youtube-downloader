"""YouTube Playlist / Video Downloader — Streamlit edition.

Paste a video or playlist URL, pick the videos you want, choose MP3 or MP4,
and download them individually or as a single ZIP.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
import zipfile
from urllib.parse import parse_qs, urlparse

import streamlit as st
import yt_dlp

st.set_page_config(page_title="YouTube Downloader", page_icon="🎵", layout="wide")

MAX_VIDEOS = 200  # safety cap on playlist size shown


# ---------------------------------------------------------------- helpers
def fix_youtube_url(url: str) -> str:
    """Turn watch?v=...&list=... into a playlist URL when asked to."""
    query = parse_qs(urlparse(url).query)
    if "list" in query and st.session_state.get("whole_playlist", True):
        return f"https://www.youtube.com/playlist?list={query['list'][0]}"
    return url


def is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(h in host for h in ("youtube.com", "youtu.be", "music.youtube.com"))


def fmt_duration(seconds) -> str:
    if not seconds:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def safe_name(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]+', "_", name).strip() or "download"


def base_opts(cookie_path: str | None) -> dict:
    opts = {"quiet": True, "no_warnings": True, "ignoreerrors": True}
    if cookie_path:
        opts["cookiefile"] = cookie_path
    return opts


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_videos(url: str, cookie_path: str | None) -> tuple[str, list[dict]]:
    opts = base_opts(cookie_path) | {"extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return "", []

    title = info.get("title") or "Video"
    entries = [e for e in info.get("entries", [info]) if e][:MAX_VIDEOS]
    videos = []
    for v in entries:
        vid = v.get("id")
        if not vid:
            continue
        videos.append(
            {
                "id": vid,
                "title": v.get("title") or vid,
                "url": v.get("webpage_url")
                or (v.get("url") if str(v.get("url", "")).startswith("http") else None)
                or f"https://www.youtube.com/watch?v={vid}",
                "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                "duration": v.get("duration"),
                "channel": v.get("channel") or v.get("uploader") or "",
            }
        )
    return title, videos


class _ErrorLog:
    """Collects yt-dlp's own error/warning text so we can show the real reason."""

    def __init__(self):
        self.lines: list[str] = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.lines.append(str(msg))

    def error(self, msg):
        self.lines.append(str(msg))


def download_one(url: str, out_dir: str, fmt: str, quality: str, cookie_path, hook):
    log = _ErrorLog()
    opts = base_opts(cookie_path) | {
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "progress_hooks": [hook],
        "noplaylist": True,
        "restrictfilenames": False,
        "ignoreerrors": False,  # raise, so the real reason reaches the UI
        "no_warnings": False,
        "logger": log,
    }
    if fmt == "MP3 (audio)":
        opts |= {
            "format": "bestaudio/best",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality},
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail"},
            ],
            "writethumbnail": True,
        }
    else:
        height = quality.rstrip("p")
        opts |= {
            "format": f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/b[height<={height}][ext=mp4]/bv*[height<={height}]+ba/b",
            "merge_output_format": "mp4",
        }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as e:  # noqa: BLE001
        detail = log.lines[-1] if log.lines else str(e)
        raise RuntimeError(re.sub(r"\x1b\[[0-9;]*m", "", detail)) from e


# ---------------------------------------------------------------- state
ss = st.session_state
ss.setdefault("videos", [])
ss.setdefault("playlist_title", "")
ss.setdefault("results", [])  # list of (filename, bytes)
ss.setdefault("errors", [])

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    fmt = st.radio("Format", ["MP3 (audio)", "MP4 (video)"])
    if fmt == "MP3 (audio)":
        quality = st.select_slider("Audio bitrate (kbps)", ["128", "192", "256", "320"], value="192")
    else:
        quality = st.select_slider("Max video quality", ["360p", "480p", "720p", "1080p"], value="720p")

    st.toggle("Fetch whole playlist when a URL has `&list=`", value=True, key="whole_playlist")

    st.divider()
    st.caption(
        "If YouTube says *“Sign in to confirm you're not a bot”*, upload a "
        "`cookies.txt` exported from your browser (Netscape format)."
    )
    cookie_file = st.file_uploader("cookies.txt (optional)", type=["txt"])
    cookie_path = None
    if cookie_file is not None:
        cookie_path = os.path.join(tempfile.gettempdir(), f"yt_cookies_{id(ss)}.txt")
        with open(cookie_path, "wb") as f:
            f.write(cookie_file.getvalue())

    st.divider()
    if shutil.which("ffmpeg") is None:
        st.error("ffmpeg not found — MP3 conversion and HD merging need it.")
    else:
        st.success("ffmpeg detected ✓")

# ---------------------------------------------------------------- header + fetch
st.title("🎵 YouTube Playlist / Video Downloader")
st.write("Paste a public video or playlist link, pick what you want, and download as MP3 or MP4.")

with st.form("fetch"):
    c1, c2 = st.columns([5, 1])
    url = c1.text_input("URL", placeholder="https://www.youtube.com/playlist?list=…", label_visibility="collapsed")
    go = c2.form_submit_button("Fetch", width="stretch", type="primary")

if go:
    url = url.strip()
    if not url or not is_youtube_url(url):
        st.warning("Please paste a valid YouTube link.")
    else:
        with st.spinner("Fetching video list…"):
            try:
                title, vids = fetch_videos(fix_youtube_url(url), cookie_path)
            except Exception as e:  # noqa: BLE001
                title, vids = "", []
                st.error(f"Couldn't read that link: {e}")
        ss.videos, ss.playlist_title, ss.results, ss.errors = vids, title, [], []
        for v in vids:
            ss[f"sel_{v['id']}"] = True
        if not vids:
            st.warning("No videos found. Is the video/playlist public?")

# ---------------------------------------------------------------- list
videos = ss.videos
if videos:
    st.subheader(f"📃 {ss.playlist_title}  ·  {len(videos)} video{'s' * (len(videos) != 1)}")

    t1, t2, t3, t4 = st.columns([3, 1, 1, 1])
    search = t1.text_input("Filter", placeholder="Filter by title…", label_visibility="collapsed")
    if t2.button("Select all", width="stretch"):
        for v in videos:
            ss[f"sel_{v['id']}"] = True
    if t3.button("Select none", width="stretch"):
        for v in videos:
            ss[f"sel_{v['id']}"] = False
    if t4.button("Clear list", width="stretch"):
        ss.videos, ss.results, ss.errors = [], [], []
        st.rerun()

    shown = [v for v in videos if search.lower() in v["title"].lower()]
    cols = st.columns(4)
    for i, v in enumerate(shown):
        with cols[i % 4].container(border=True):
            st.image(v["thumbnail"], width="stretch")
            st.checkbox(f"**{v['title']}**", key=f"sel_{v['id']}")
            meta = " · ".join(x for x in (v["channel"], fmt_duration(v["duration"])) if x)
            st.caption(f"{meta}  \n[Open on YouTube]({v['url']})")

    selected = [v for v in videos if ss.get(f"sel_{v['id']}")]
    total = sum(v["duration"] or 0 for v in selected)
    st.info(f"**{len(selected)}** selected · total length {fmt_duration(total)}")

    if st.button(f"⬇️ Download {len(selected)} as {fmt.split()[0]}", type="primary", disabled=not selected):
        ss.results, ss.errors = [], []
        work = tempfile.mkdtemp()
        overall = st.progress(0.0, text="Starting…")
        current = st.empty()

        for n, v in enumerate(selected, 1):
            item_dir = os.path.join(work, str(n))
            os.makedirs(item_dir)
            bar = current.progress(0.0, text=f"{v['title']}")

            def hook(d, bar=bar, title=v["title"]):
                if d["status"] == "downloading":
                    tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    pct = min(d.get("downloaded_bytes", 0) / tot, 1.0) if tot else 0.0
                    bar.progress(pct, text=f"{title} — {pct:.0%}")
                elif d["status"] == "finished":
                    bar.progress(1.0, text=f"{title} — converting…")

            try:
                download_one(v["url"], item_dir, fmt, quality, cookie_path, hook)
            except Exception as e:  # noqa: BLE001
                ss.errors.append(f"{v['title']}: {e}")

            files = [f for f in os.listdir(item_dir) if f.endswith((".mp3", ".mp4"))]
            if files:
                with open(os.path.join(item_dir, files[0]), "rb") as fh:
                    ss.results.append((files[0], fh.read()))
            elif not any(v["title"] in err for err in ss.errors):
                ss.errors.append(f"{v['title']}: download failed (private, age-restricted or blocked).")
            overall.progress(n / len(selected), text=f"{n}/{len(selected)} done")

        current.empty()
        shutil.rmtree(work, ignore_errors=True)

# ---------------------------------------------------------------- results
if ss.results:
    st.success(f"✅ {len(ss.results)} file(s) ready.")
    if len(ss.results) > 1:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for name, data in ss.results:
                z.writestr(name, data)
        st.download_button(
            "📦 Download all as ZIP",
            buf.getvalue(),
            file_name=f"{safe_name(ss.playlist_title)}.zip",
            mime="application/zip",
            type="primary",
        )
    with st.expander("Individual files", expanded=len(ss.results) <= 5):
        for i, (name, data) in enumerate(ss.results):
            c1, c2 = st.columns([4, 1])
            c1.write(f"{name}  ·  {len(data) / 1_048_576:.1f} MB")
            c2.download_button(
                "Download",
                data,
                file_name=name,
                mime="audio/mpeg" if name.endswith(".mp3") else "video/mp4",
                key=f"dl_{i}",
                width="stretch",
            )

if ss.errors:
    with st.expander(f"⚠️ {len(ss.errors)} problem(s)"):
        for e in ss.errors:
            st.write("•", e)

st.divider()
st.caption("Only download content you own or have permission to download. Respect YouTube's Terms of Service.")
