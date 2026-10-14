# 🎵 YouTube Playlist / Video Downloader (Streamlit)

Paste a public YouTube video or playlist link, pick the videos, and download them as **MP3** or **MP4** — one by one or as a single ZIP.

## Features
- Works with single videos, playlists, and `watch?v=…&list=…` links
- MP3 (128–320 kbps, with cover art + tags) or MP4 (360p–1080p)
- Thumbnails, channel, duration, title filter, select all / none
- Live per-video progress bar + overall progress
- Download individual files or everything as a ZIP
- Optional `cookies.txt` upload for when YouTube asks to "confirm you're not a bot"

## Run locally
```bash
pip install -r requirements.txt
# also install ffmpeg (https://ffmpeg.org) and make sure it is on PATH
streamlit run app.py
```

## Deploy to Streamlit Community Cloud
1. Create a new **public GitHub repo** and upload these files:
   `app.py`, `requirements.txt`, `packages.txt`, `.streamlit/config.toml`, `README.md`
2. Go to **https://share.streamlit.io** → sign in with GitHub → **Create app**.
3. Pick your repo, branch `main`, main file `app.py` → **Deploy**.

`packages.txt` makes Streamlit Cloud install **ffmpeg** automatically.

## Known limitation on cloud hosting
YouTube often blocks requests from data-center IPs (including Streamlit Cloud) with
*"Sign in to confirm you're not a bot"*. If that happens, export your YouTube cookies
(e.g. with the "Get cookies.txt LOCALLY" browser extension while logged in), and upload
the file in the app's sidebar. Running locally usually avoids the problem entirely.

Only download content you own or have permission to download.
