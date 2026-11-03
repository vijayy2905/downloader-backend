import os
import re
import zipfile
import shutil
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "temp_downloads"

def get_spotify_track_names(url):
    """Fetches track titles and artists directly from Spotify open metadata."""
    track_queries = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    try:
        clean_url = url.split('?')[0]
        if "embed" not in clean_url:
            clean_url = clean_url.replace("open.spotify.com/", "open.spotify.com/embed/")

        response = requests.get(clean_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            script_tag = soup.find('script', id='initial-state') or soup.find('script', id='session')
            if script_tag and script_tag.string:
                raw_text = script_tag.string
                matches = re.findall(r'"name":"([^"]+)","artists":\[{"name":"([^"]+)"', raw_text)
                for track, artist in matches:
                    query = f"{track} {artist}"
                    if query not in track_queries:
                        track_queries.append(query)

            if not track_queries:
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text().replace(' | Spotify', '').replace(' - song and lyrics by', '')
                    track_queries.append(title_text)

    except Exception as e:
        print("Metadata error:", e)

    return track_queries


def download_single_track(query, output_template):
    """Downloads audio without requiring system FFmpeg binary."""
    # Attempt 1: SoundCloud search (bypasses YouTube bot block)
    sc_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'allowed_extractors': ['soundcloud', 'soundcloud:search']
    }
    try:
        with yt_dlp.YoutubeDL(sc_opts) as ydl:
            ydl.download([f"scsearch1:{query}"])
            return True
    except Exception as sc_e:
        print("SoundCloud search failed, trying YouTube fallback:", sc_e)

    # Attempt 2: YouTube fallback with Android client emulation
    yt_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'mweb']
            }
        }
    }
    try:
        with yt_dlp.YoutubeDL(yt_opts) as ydl:
            ydl.download([f"ytsearch1:{query} audio"])
            return True
    except Exception as yt_e:
        print("YouTube download failed:", yt_e)

    return False


@app.route('/download', methods=['POST'])
def handle_download():
    data = request.get_json()
    url = data.get('url') if data else None

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
    os.makedirs(DOWNLOAD_DIR)

    search_queries = get_spotify_track_names(url)

    if not search_queries:
        return jsonify({'error': 'Could not extract track metadata from URL.'}), 400

    for idx, query in enumerate(search_queries):
        output_tmpl = os.path.join(DOWNLOAD_DIR, f"%(title)s.%(ext)s")
        download_single_track(query, output_tmpl)

    downloaded_files = [
        f for f in os.listdir(DOWNLOAD_DIR)
        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)) and os.path.getsize(os.path.join(DOWNLOAD_DIR, f)) > 0
    ]

    if not downloaded_files:
        return jsonify({'error': 'Audio download failed. Cloud server IP blocked.'}), 404

    # Single track download
    if len(downloaded_files) == 1:
        file_path = os.path.join(DOWNLOAD_DIR, downloaded_files[0])
        return send_file(file_path, as_attachment=True, download_name=downloaded_files[0])

    # Multiple tracks (playlist) -> ZIP archive
    zip_path = "playlist.zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in downloaded_files:
            zipf.write(os.path.join(DOWNLOAD_DIR, file), file)

    return send_file(zip_path, as_attachment=True, download_name="playlist.zip", mimetype='application/zip')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
