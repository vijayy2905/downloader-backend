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
    """Extracts track names directly from Spotify's embed page."""
    track_queries = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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

    # Uses SoundCloud search first to avoid YouTube datacenter IP blocking
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'quiet': True,
        'no_warnings': True,
        'default_search': 'scsearch',  # Search SoundCloud to bypass YouTube bot challenge
        'noplaylist': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for query in search_queries:
                search_term = f"scsearch1:{query}"
                try:
                    ydl.download([search_term])
                except Exception as sc_err:
                    print("SoundCloud failed, trying YouTube fallback:", sc_err)
                    yt_opts = dict(ydl_opts)
                    yt_opts['default_search'] = 'ytsearch'
                    yt_opts['extractor_args'] = {'youtube': {'player_client': ['mweb', 'tv']}}
                    with yt_dlp.YoutubeDL(yt_opts) as ydl_yt:
                        ydl_yt.download([f"ytsearch1:{query} audio"])

        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
        if not files:
            return jsonify({'error': 'Audio download failed.'}), 404

        # Single Track -> MP3
        if len(files) == 1:
            file_path = os.path.join(DOWNLOAD_DIR, files[0])
            return send_file(file_path, as_attachment=True, download_name=files[0], mimetype='audio/mpeg')

        # Multiple Tracks -> ZIP
        zip_path = "playlist.zip"
        if os.path.exists(zip_path):
            os.remove(zip_path)
            
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files:
                zipf.write(os.path.join(DOWNLOAD_DIR, file), file)

        return send_file(zip_path, as_attachment=True, download_name="playlist.zip", mimetype='application/zip')

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
