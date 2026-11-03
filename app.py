import os
import re
import zipfile
import shutil
import requests
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "temp_downloads"

def get_spotify_track_names(url):
    """Fetches track metadata using Spotify's public API token endpoint."""
    track_queries = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        # Get anonymous Spotify access token
        token_resp = requests.get('https://open.spotify.com/get_access_token', headers=headers, timeout=10)
        if token_resp.status_code != 200:
            return []
        
        token_data = token_resp.json()
        access_token = token_data.get('accessToken')
        if not access_token:
            return []

        api_headers = {'Authorization': f'Bearer {access_token}'}

        # Handle Playlist URL
        if "playlist" in url:
            playlist_id = url.split("playlist/")[1].split("?")[0]
            api_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
            resp = requests.get(api_url, headers=api_headers, timeout=10)
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                for item in items:
                    track = item.get('track')
                    if track:
                        artists = ", ".join([a['name'] for a in track['artists']])
                        track_queries.append(f"{track['name']} {artists}")

        # Handle Single Track URL
        elif "track" in url:
            track_id = url.split("track/")[1].split("?")[0]
            api_url = f"https://api.spotify.com/v1/tracks/{track_id}"
            resp = requests.get(api_url, headers=api_headers, timeout=10)
            if resp.status_code == 200:
                track = resp.json()
                artists = ", ".join([a['name'] for a in track['artists']])
                track_queries.append(f"{track['name']} {artists}")

        # Handle Album URL
        elif "album" in url:
            album_id = url.split("album/")[1].split("?")[0]
            api_url = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
            resp = requests.get(api_url, headers=api_headers, timeout=10)
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                for track in items:
                    artists = ", ".join([a['name'] for a in track['artists']])
                    track_queries.append(f"{track['name']} {artists}")

    except Exception as e:
        print("Spotify API extraction error:", e)

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
        return jsonify({'error': 'Failed to fetch tracks. Check if playlist is public.'}), 400

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
