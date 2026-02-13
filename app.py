#!/usr/bin/env python3
"""
YouTube Downloader - Version Web avec Playlists et Multi-téléchargement
Support optionnel Cloudinary pour stockage cloud
"""

from flask import Flask, render_template, request, jsonify, send_file, abort
from pathlib import Path
import yt_dlp
import os
import threading
import time
import zipfile
import re
import urllib.parse

app = Flask(__name__)

DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Configuration Cloudinary (optionnel)
CLOUDINARY_ENABLED = False
try:
    import cloudinary
    import cloudinary.uploader
    if os.environ.get('CLOUDINARY_URL'):
        CLOUDINARY_ENABLED = True
        print("Cloudinary activé")
except ImportError:
    pass

download_status = {}


def sanitize_filename(filename):
    """Nettoie le nom de fichier"""
    filename = re.sub(r'[<>:"/\\|?*\'\"]', '_', filename)
    filename = filename.replace('/', '_').replace('\\', '_')
    if len(filename) > 150:
        filename = filename[:150]
    return filename.strip()


def get_video_info(url):
    """Récupère les infos de la vidéo ou playlist"""
    options = {
        'quiet': True,
        'extract_flat': 'in_playlist',
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

        if 'entries' in info:
            videos = []
            for entry in info['entries']:
                if entry:
                    videos.append({
                        'id': entry.get('id', ''),
                        'title': entry.get('title', 'Unknown'),
                        'url': entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                        'duration': entry.get('duration', 0) or 0,
                    })
            return {
                'type': 'playlist',
                'title': info.get('title', 'Playlist'),
                'channel': info.get('channel', info.get('uploader', 'Unknown')),
                'count': len(videos),
                'videos': videos,
                'thumbnail': info.get('thumbnails', [{}])[-1].get('url', '') if info.get('thumbnails') else '',
            }
        else:
            duration = info.get('duration', 0) or 0
            minutes, seconds = divmod(duration, 60)
            return {
                'type': 'video',
                'title': info.get('title', 'Unknown'),
                'channel': info.get('channel', info.get('uploader', 'Unknown')),
                'duration': f"{minutes}:{seconds:02d}",
                'thumbnail': info.get('thumbnail', ''),
            }


def upload_to_cloud(file_path):
    """Upload vers Cloudinary si activé"""
    if not CLOUDINARY_ENABLED:
        return None
    try:
        result = cloudinary.uploader.upload(
            str(file_path),
            resource_type="auto",
            folder="youtube-downloads"
        )
        return result.get('secure_url')
    except Exception as e:
        print(f"Erreur upload Cloudinary: {e}")
        return None


def download_single(url, format_type, quality, task_id=None):
    """Télécharge une seule vidéo"""
    if task_id and task_id in download_status:
        download_status[task_id]['progress'] = 0

    # Générer un nom de fichier unique basé sur le timestamp
    timestamp = int(time.time() * 1000)
    ext = 'mp3' if format_type == 'mp3' else 'mp4'

    if format_type == 'mp3':
        options = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality,
            }],
            'outtmpl': str(DOWNLOAD_DIR / f'%(title)s.%(ext)s'),
            'noplaylist': True,  # Ne pas télécharger toute la playlist
        }
    else:
        if quality == "best":
            format_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        else:
            format_str = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]'

        options = {
            'format': format_str,
            'outtmpl': str(DOWNLOAD_DIR / f'%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'noplaylist': True,  # Ne pas télécharger toute la playlist
        }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'video')
        safe_title = sanitize_filename(title)

        # Trouver le fichier téléchargé (le plus récent avec la bonne extension)
        time.sleep(0.5)  # Attendre que le fichier soit écrit

        files = []
        for f in DOWNLOAD_DIR.iterdir():
            if f.is_file() and f.suffix == f'.{ext}':
                files.append((f, f.stat().st_mtime))

        if files:
            files.sort(key=lambda x: x[1], reverse=True)
            actual_file = files[0][0]
            actual_filename = actual_file.name
        else:
            actual_filename = f"{safe_title}.{ext}"

        # Upload cloud si activé
        cloud_url = None
        if CLOUDINARY_ENABLED:
            cloud_url = upload_to_cloud(DOWNLOAD_DIR / actual_filename)

        return {
            'title': title,
            'filename': actual_filename,
            'cloud_url': cloud_url
        }


def download_multiple(urls, format_type, quality, task_id, playlist_name=None):
    """Télécharge plusieurs vidéos et crée un ZIP"""
    results = []
    total = len(urls)
    downloaded_files = []

    download_status[task_id] = {
        'status': 'downloading',
        'total': total,
        'completed': 0,
        'current': '',
        'results': [],
        'zip_file': None
    }

    for i, url in enumerate(urls):
        url = url.strip()
        if not url:
            continue

        try:
            download_status[task_id]['current'] = f"Téléchargement {i+1}/{total}"
            result = download_single(url, format_type, quality, task_id)
            results.append({'success': True, **result})
            download_status[task_id]['results'].append({'success': True, **result})

            # Vérifier que le fichier existe avant de l'ajouter
            file_path = DOWNLOAD_DIR / result['filename']
            if file_path.exists():
                downloaded_files.append(result['filename'])
        except Exception as e:
            error_msg = str(e)[:100]
            results.append({'success': False, 'error': error_msg, 'url': url})
            download_status[task_id]['results'].append({'success': False, 'error': error_msg, 'url': url})

        download_status[task_id]['completed'] = i + 1

    # Créer le ZIP
    zip_filename = None
    if len(downloaded_files) >= 1:
        download_status[task_id]['current'] = "Création du ZIP..."

        # Nom simple pour le ZIP
        safe_name = sanitize_filename(playlist_name or "playlist")
        zip_filename = f"{safe_name}_{task_id[-8:]}.zip"
        zip_path = DOWNLOAD_DIR / zip_filename

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filename in downloaded_files:
                    file_path = DOWNLOAD_DIR / filename
                    if file_path.exists():
                        zf.write(file_path, filename)
                        print(f"Ajouté au ZIP: {filename}")

            print(f"ZIP créé: {zip_path} ({zip_path.stat().st_size} bytes)")

            # Upload ZIP vers cloud si activé
            if CLOUDINARY_ENABLED:
                cloud_url = upload_to_cloud(zip_path)
                download_status[task_id]['zip_cloud_url'] = cloud_url

        except Exception as e:
            print(f"Erreur création ZIP: {e}")
            zip_filename = None

    download_status[task_id]['status'] = 'completed'
    download_status[task_id]['zip_file'] = zip_filename
    download_status[task_id]['current'] = 'Terminé'

    return results


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/info', methods=['POST'])
def api_info():
    try:
        url = request.json.get('url')
        info = get_video_info(url)
        return jsonify({'success': True, 'data': info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/download', methods=['POST'])
def api_download():
    try:
        data = request.json
        urls = data.get('urls', [])
        format_type = data.get('format', 'mp3')
        quality = data.get('quality', '192')

        task_id = f"task_{int(time.time() * 1000)}"

        if len(urls) == 1:
            url = urls[0]
            # Vérifier si c'est une playlist
            if 'list=' in url or '/playlist' in url:
                # C'est une playlist, récupérer les vidéos
                info = get_video_info(url)
                if info['type'] == 'playlist':
                    video_urls = [v['url'] for v in info['videos']]
                    playlist_name = info['title']

                    thread = threading.Thread(
                        target=download_multiple,
                        args=(video_urls, format_type, quality, task_id, playlist_name)
                    )
                    thread.start()
                    return jsonify({
                        'success': True,
                        'task_id': task_id,
                        'total': len(video_urls),
                        'playlist_title': playlist_name
                    })

            # Vidéo simple
            result = download_single(url, format_type, quality)
            return jsonify({'success': True, 'data': result})
        else:
            thread = threading.Thread(
                target=download_multiple,
                args=(urls, format_type, quality, task_id, "Multi-Download")
            )
            thread.start()
            return jsonify({'success': True, 'task_id': task_id, 'total': len(urls)})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/download/playlist', methods=['POST'])
def api_download_playlist():
    try:
        data = request.json
        url = data.get('url')
        format_type = data.get('format', 'mp3')
        quality = data.get('quality', '192')
        selected = data.get('selected', [])

        task_id = f"playlist_{int(time.time() * 1000)}"

        info = get_video_info(url)

        if info['type'] != 'playlist':
            return jsonify({'success': False, 'error': 'Ce n\'est pas une playlist'})

        if selected:
            videos = [v for v in info['videos'] if v['id'] in selected]
        else:
            videos = info['videos']

        urls = [v['url'] for v in videos]
        playlist_name = info['title']

        thread = threading.Thread(
            target=download_multiple,
            args=(urls, format_type, quality, task_id, playlist_name)
        )
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'total': len(urls),
            'playlist_title': playlist_name
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/status/<task_id>')
def api_status(task_id):
    if task_id in download_status:
        return jsonify({'success': True, 'data': download_status[task_id]})
    return jsonify({'success': False, 'error': 'Tâche non trouvée'})


@app.route('/downloads/<path:filename>')
def serve_file(filename):
    """Sert les fichiers téléchargés"""
    # Décoder le nom de fichier
    filename = urllib.parse.unquote(filename)
    file_path = DOWNLOAD_DIR / filename

    print(f"Demande fichier: {filename}")
    print(f"Chemin complet: {file_path}")
    print(f"Existe: {file_path.exists()}")

    if not file_path.exists():
        # Lister les fichiers disponibles pour debug
        print("Fichiers disponibles:")
        for f in DOWNLOAD_DIR.iterdir():
            print(f"  - {f.name}")
        abort(404)

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename
    )


@app.route('/api/files')
def list_files():
    """Liste les fichiers téléchargés"""
    files = []
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and not f.name.startswith('.'):
            files.append({
                'name': f.name,
                'size': f.stat().st_size,
                'modified': f.stat().st_mtime,
                'is_zip': f.suffix == '.zip'
            })
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'success': True, 'files': files})


@app.route('/api/cloud-status')
def cloud_status():
    """Vérifie si le stockage cloud est activé"""
    return jsonify({
        'success': True,
        'cloudinary_enabled': CLOUDINARY_ENABLED
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
