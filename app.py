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
    """Extracts track names directly from Spotify's open embed page without requiring API keys."""
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
        print("Embed extraction error:", e)

    return track_queries


def download_via_piped(query, save_path):
    """Fetches audio stream via Piped API proxy network to bypass YouTube datacenter IP blocking."""
    piped_instances = [
        "https://api.piped.private.coffee",
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.drgns.space"
    ]
    
    for instance in piped_instances:
        try:
            # 1. Search track
            search_res = requests.get(
                f"{instance}/search", 
                params={"q": query, "filter": "music_songs"}, 
                timeout=5
            )
            if search_res.status_code != 200:
                continue
            
            items = search_res.json().get("items", [])
            if not items:
                continue
            
            # Extract video ID
            video_url = items[0].get("url", "")
            if "v=" not in video_url:
                continue
            video_id = video_url.split("v=")[-1]

            # 2. Get audio stream details
            stream_res = requests.get(f"{instance}/streams/{video_id}", timeout=5)
            if stream_res.status_code != 200:
                continue

            audio_streams = stream_res.json().get("audioStreams", [])
            if not audio_streams:
                continue

            audio_url = audio_streams[0].get("url")
            if not audio_url:
                continue

            # 3. Stream download directly to file
            audio_data = requests.get(audio_url, stream=True, timeout=15)
            with open(save_path, 'wb') as f:
                for chunk in audio_data.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return True
        except Exception as err:
            print(f"Piped instance {instance} failed:", err)
            continue
            
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
        return jsonify({'error': 'Failed to fetch tracks from Spotify link.'}), 400

    for idx, query in enumerate(search_queries):
        safe_title = re.sub(r'[^\w\s-]', '', query).strip() or f"track_{idx}"
        output_file = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp3")

        # Primary method: Piped API Proxy (Bypasses YouTube bot check)
        success = download_via_piped(query, output_file)

        # Fallback method: SoundCloud search (Explicitly forbidding YouTube scraper)
        if not success:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_file,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'quiet': True,
                'no_warnings': True,
                'allowed_extractors': ['soundcloud', 'soundcloud:search'],
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"scsearch1:{query}"])
            except Exception as sc_err:
                print("SoundCloud search failed:", sc_err)

    files = [f for f in os.listdir(DOWNLOAD_DIR) if os.path.exists(os.path.join(DOWNLOAD_DIR, f)) and os.path.getsize(os.path.join(DOWNLOAD_DIR, f)) > 0]
    if not files:
        return jsonify({'error': 'Audio download failed.'}), 404
