import os
import zipfile
import shutil
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "temp_downloads"

# REPLACE THESE TWO LINES WITH YOUR ACTUAL KEYS:
SPOTIPY_CLIENT_ID = "b6bb4b60b034493e8d5ca8f4e1791f00"
SPOTIPY_CLIENT_SECRET = "0e2d99d9b516413883a8dfcd65dfab14"

def get_spotify_track_names(url):
    """Uses official Spotify API client to fetch tracks securely."""
    track_queries = []
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)

                if "playlist" in url:
            playlist_id = url.split("playlist/")[1].split("?")[0]
            results = sp.playlist_tracks(playlist_id)
            tracks = results.get('items', [])
            while results.get('next'):
                results = sp.next(results)
                tracks.extend(results.get('items', []))
            
            for item in tracks:
                track = item.get('track')
                if track and track.get('name'):
                    artists = ", ".join([a['name'] for a in track['artists']])
                    track_queries.append(f"{track['name']} {artists}")

        elif "track" in url:
            track_id = url.split("track/")[1].split("?")[0]
            track = sp.track(track_id)
            if track:
                artists = ", ".join([a['name'] for a in track['artists']])
                track_queries.append(f"{track['name']} {artists}")

        elif "album" in url:
            album_id = url.split("album/")[1].split("?")[0]
            results = sp.album_tracks(album_id)
            tracks = results['items']
            while results.get('next'):
                results = sp.next(results)
                tracks.extend(results['items'])

            for track in tracks:
                artists = ", ".join([a['name'] for a in track['artists']])
                track_queries.append(f"{track['name']} {artists}")

    except Exception as e:
        print("Spotipy API Error:", e)

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
        return jsonify({'error': 'Failed to fetch tracks from Spotify API.'}), 400

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
