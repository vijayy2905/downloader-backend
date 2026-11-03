import os
import zipfile
import shutil
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "temp_downloads"

@app.route('/download', methods=['POST'])
def handle_download():
    data = request.get_json()
    url = data.get('url') if data else None

    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
    os.makedirs(DOWNLOAD_DIR)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'quiet': True,
        'no_warnings': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
        if not files:
            return jsonify({'error': 'No tracks found or download failed'}), 404

        # Single song -> send MP3 directly
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
