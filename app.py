from flask import Flask, render_template, request, jsonify, Response
from flask import stream_with_context
from werkzeug.wsgi import FileWrapper
import yt_dlp
import os
import tempfile
import shutil
import re
import time

app = Flask(__name__)
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), 'downloads')
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)
def sanitize_filename(name):
    """Removes characters that aren't allowed in filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

@app.route('/')
def index():
    # This renders your index.html file
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration_string')
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/search', methods=['POST'])
def search_videos():
    query = request.json.get('query')
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        # Search for the top 5 results
        ydl_opts = {
            'quiet': True,
            'extract_flat': True, # Faster: doesn't load full video info
            'force_generic_extractor': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 'ytsearch5:' tells yt-dlp to find 5 results on YouTube
            search_results = ydl.extract_info(f"ytsearch5:{query}", download=False)
            
            videos = []
            for entry in search_results.get('entries', []):
                videos.append({
                    'id': entry.get('id'),
                    'title': entry.get('title'),
                    'url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                    'thumbnail': entry.get('thumbnails')[0]['url'] if entry.get('thumbnails') else '',
                    'duration': entry.get('duration_string') or "N/A"
                })
            
            return jsonify({'results': videos})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
        

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    f_type = data.get('format')
    quality = data.get('quality')

    request_id = re.sub(r'\D', '', str(os.urandom(4).hex())) 
    save_path = os.path.join(DOWNLOAD_FOLDER, request_id)
    os.makedirs(save_path, exist_ok=True)

    simple_name = "download_file" 
    ext = 'mp3' if f_type == 'mp3' else 'mp4'
    downloaded_path = os.path.join(save_path, f"{simple_name}.{ext}")
    
    try:
        ydl_opts = {
            'outtmpl': f'{save_path}/{simple_name}.%(ext)s',
            'noplaylist': True,
            'quiet': True,
            # No cookiefile here unless you have a cookies.txt uploaded
        }

        if f_type == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': str(quality),
                }],
            })
        else:
            # Optimized format selection to reduce server strain
            ydl_opts.update({
                'format': f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]/best',
                'merge_output_format': 'mp4',
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            original_title = info.get('title', 'download')
            video_title = f"{sanitize_filename(original_title)}.{ext}"

        # Verification check
        if not os.path.exists(downloaded_path):
            files = os.listdir(save_path)
            downloaded_path = os.path.join(save_path, files[0]) if files else None
            if not downloaded_path: raise FileNotFoundError("Download failed.")

        file_size = os.path.getsize(downloaded_path)

        @stream_with_context
        def generate():
            try:
                with open(downloaded_path, 'rb') as f:
                    while True:
                        chunk = f.read(1024 * 1024) # 1MB chunks for stability
                        if not chunk: break
                        yield chunk
            finally:
                # Give the system a second to close the file handle before deleting
                time.sleep(2)
                if os.path.exists(save_path):
                    shutil.rmtree(save_path)

        return Response(
            generate(),
            mimetype='application/octet-stream',
            headers={
                "Content-Disposition": f"attachment; filename=\"{video_title}\"",
                "Content-Length": str(file_size)
            }
        )

    except Exception as e:
        if os.path.exists(save_path): shutil.rmtree(save_path)
        return jsonify({'error': str(e)}), 400
        
if __name__ == '__main__':
    app.run(debug=True)
