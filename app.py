import os
import re
import zipfile
import shutil
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "temp_downloads"

def get_spotify_track_names(url):
    """Extracts track names directly from Spotify open embed metadata."""
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
        print("Metadata extraction error:", e)

    return track_queries


def download_audio_stream(query, save_path):
    """Downloads audio directly via open music API gateways, bypassing cloud IP blocks."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # Primary Gateway: Direct MP3 Music APIs (Zero IP Blocking)
    encoded_query = requests.utils.quote(query)
    music_apis = [
        f"https://saavn.dev/api/search/songs?query={encoded_query}",
        f"https://saavn.me/search/songs?query={encoded_query}",
        f"https://jiosaavn-api-private-us.vercel.app/search/songs?query={encoded_query}"
    ]

    for api_url in music_apis:
        try:
            res = requests.get(api_url, headers=headers, timeout=6)
            if res.status_code == 200:
                data = res.json()
                results = data.get('data', {}).get('results', []) or data.get('results', [])
                if results:
                    download_urls = results[0].get('downloadUrl', [])
                    target_url = None
                    
                    if isinstance(download_urls, list):
                        for item in reversed(download_urls):
                            if isinstance(item, dict) and 'url' in item:
                                target_url = item['url']
                                break
                    elif isinstance(download_urls, str):
                        target_url = download_urls

                    if target_url:
                        audio_res = requests.get(target_url, headers=headers, stream=True, timeout=20)
                        if audio_res.status_code == 200:
                            with open(save_path, 'wb') as f:
                                for chunk in audio_res.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            return True
        except Exception as e:
            print(f"Music API endpoint failed ({api_url}):", e)

    # Fallback Gateway: Piped API Network (YouTube Proxy)
    piped_instances = [
        "https://api.piped.private.coffee",
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.drgns.space"
    ]
    for instance in piped_instances:
        try:
            s_res = requests.get(f"{instance}/search", params={"q": query, "filter": "music_songs"}, timeout=5)
            if s_res.status_code == 200:
                items = s_res.json().get("items", [])
                if items:
                    v_url = items[0].get("url", "")
                    if "v=" in v_url:
                        video_id = v_url.split("v=")[-1]
                        st_res = requests.get(f"{instance}/streams/{video_id}", timeout=5)
                        if st_res.status_code == 200:
                            audio_streams = st_res.json().get("audioStreams", [])
                            if audio_streams:
                                a_url = audio_streams[0].get("url")
                                audio_res = requests.get(a_url, headers=headers, stream=True, timeout=20)
                                if audio_res.status_code == 200:
                                    with open(save_path, 'wb') as f:
                                        for chunk in audio_res.iter_content(chunk_size=8192):
                                            if chunk:
                                                f.write(chunk)
                                    return True
        except Exception as p_err:
            print("Piped API failed:", p_err)

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
        return jsonify({'error': 'Could not extract tracks from Spotify link.'}), 400

    for idx, query in enumerate(search_queries):
        safe_title = re.sub(r'[^\w\s-]', '', query).strip() or f"track_{idx}"
        output_file = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp3")
        download_audio_stream(query, output_file)

    downloaded_files = [
        f for f in os.listdir(DOWNLOAD_DIR)
        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)) and os.path.getsize(os.path.join(DOWNLOAD_DIR, f)) > 1024
    ]

    if not downloaded_files:
        return jsonify({'error': 'Audio download failed. Music source unavailable.'}), 404

    # Single track -> MP3
    if len(downloaded_files) == 1:
        file_path = os.path.join(DOWNLOAD_DIR, downloaded_files[0])
        return send_file(file_path, as_attachment=True, download_name=downloaded_files[0], mimetype='audio/mpeg')

    # Playlist -> ZIP file
    zip_path = "playlist.zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in downloaded_files:
            zipf.write(os.path.join(DOWNLOAD_DIR, file), file)

    return send_file(zip_path, as_attachment=True, download_name="playlist.zip", mimetype='application/zip')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
