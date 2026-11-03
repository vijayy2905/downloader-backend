import os
import re
import zipfile
import shutil
import urllib.request
import json
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "temp_downloads"

def get_spotify_tracks(url):
    """Extracts song titles and artists from a Spotify link using Spotify's embed API."""
    try:
        # Standardize URL to embed endpoint
        if "playlist" in url:
            playlist_id = url.split("playlist/")[1].split("?")[0]
            embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        elif "track" in url:
            track_id = url.split("track/")[1].split("?")[0]
            embed_url = f"https://open.spotify.com/embed/track/{track_id}"
        elif "album" in url:
            album_id = url.split("album/")[1].split("?")[0]
            embed_url = f"https://open.spotify.com/embed/album/{album_id}"
        else:
            return [url] # Fallback to raw query if not a standard Spotify link

        req = urllib.request.Request(embed_url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')

        # Parse JSON state inside Spotify embed page
        match = re.search(r'<script id="session" type="application/json">(.*?)</script>', html)
        if match:
            data = json.loads(match.group(1))
            # Handle tracks in playlist
            if 'data' in data and 'entity' in data['data']:
                entity = data['data']['entity']
                if 'trackList' in entity:
                    return [f"{track['title']} {track['subtitle']}" for track in entity['trackList']]
                elif 'title' in entity:
                    return [f"{entity['title']} {entity.get('subtitle', '')}"]

        # Alternative extraction using meta tags if JSON parse fails
        title_match = re.findall(r'<meta property="og:title" content="(.*?)"', html)
        if title_match:
            return [title_match[0]]

    except Exception as e:
        print("Spotify Metadata Error:", e)

    return [url]


@app.route('/download', methods=['POST'])
def handle_download():
    data = request.get_json()
    url = data.get('url') if data else None

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
    os.makedirs(DOWNLOAD_DIR)

    # Convert Spotify link to searchable query strings
    search_queries = get_spotify_tracks(url)

    if not search_queries:
        return jsonify({'error': 'Could not extract songs from Spotify link'}), 400

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
        'default_search': 'ytsearch',
        'noplaylist': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for query in search_queries:
                search_term = f"ytsearch1:{query} audio"
                ydl.download([search_term])

        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
        if not files:
            return jsonify({'error': 'No tracks found or download failed'}), 404

        # Single Track -> send MP3 directly
        if len(files) == 1:
            file_path = os.path.join(DOWNLOAD_DIR, files[0])
            return send_file(file_path, as_attachment=True, download_name=files[0], mimetype='audio/mpeg')

        # Playlist -> package into ZIP
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
