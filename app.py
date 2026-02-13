#!/usr/bin/env python3
"""
YouTube Downloader - Version Web avec Playlists, Historique et Progression
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
import json
from datetime import datetime

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
HISTORY_FILE = BASE_DIR / "history.json"

# Status des téléchargements en cours
download_status = {}


def load_history():
    """Charge l'historique depuis le fichier JSON"""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []


def save_history(history):
    """Sauvegarde l'historique dans le fichier JSON"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def add_to_history(title, filename, format_type, url="", is_playlist=False, playlist_name=""):
    """Ajoute une entrée à l'historique"""
    history = load_history()
    entry = {
        'id': int(time.time() * 1000),
        'title': title,
        'filename': filename,
        'format': format_type,
        'url': url,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'is_playlist': is_playlist,
        'playlist_name': playlist_name
    }
    history.insert(0, entry)
    # Garder les 100 dernières entrées
    history = history[:100]
    save_history(history)
    return entry


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


def download_single(url, format_type, quality, task_id=None, update_progress=None):
    """Télécharge une seule vidéo"""
    ext = 'mp3' if format_type == 'mp3' else 'mp4'

    def progress_hook(d):
        if d['status'] == 'downloading' and update_progress:
            percent_str = d.get('_percent_str', '0%').strip()
            speed_str = d.get('_speed_str', 'N/A')
            update_progress(percent_str, speed_str)

    if format_type == 'mp3':
        options = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality,
            }],
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'noplaylist': True,
            'progress_hooks': [progress_hook],
        }
    else:
        if quality == "best":
            format_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        else:
            format_str = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]'

        options = {
            'format': format_str,
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'progress_hooks': [progress_hook],
        }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'video')

        # Attendre que le fichier soit écrit
        time.sleep(0.3)

        # Trouver le fichier le plus récent avec la bonne extension
        files = [(f, f.stat().st_mtime) for f in DOWNLOAD_DIR.iterdir()
                 if f.is_file() and f.suffix == f'.{ext}' and not f.name.endswith('.zip')]

        if files:
            files.sort(key=lambda x: x[1], reverse=True)
            actual_file = files[0][0]
            actual_filename = actual_file.name
        else:
            actual_filename = f"{sanitize_filename(title)}.{ext}"

        return {
            'title': title,
            'filename': actual_filename,
            'url': url
        }


def download_multiple(urls, format_type, quality, task_id, playlist_name=None):
    """Télécharge plusieurs vidéos avec progression et crée un ZIP"""
    total = len(urls)
    downloaded_files = []
    results = []

    download_status[task_id] = {
        'status': 'downloading',
        'total': total,
        'completed': 0,
        'current_title': '',
        'current_progress': '0%',
        'current_speed': '',
        'results': [],
        'zip_file': None
    }

    def update_progress(percent, speed):
        download_status[task_id]['current_progress'] = percent
        download_status[task_id]['current_speed'] = speed

    for i, url in enumerate(urls):
        url = url.strip()
        if not url:
            continue

        download_status[task_id]['current_title'] = f"Vidéo {i+1}/{total}"
        download_status[task_id]['current_progress'] = '0%'

        try:
            result = download_single(url, format_type, quality, task_id, update_progress)
            results.append({'success': True, **result})
            download_status[task_id]['results'].append({'success': True, **result})

            # Vérifier que le fichier existe
            file_path = DOWNLOAD_DIR / result['filename']
            if file_path.exists():
                downloaded_files.append(result['filename'])
                # Ajouter à l'historique
                add_to_history(
                    result['title'],
                    result['filename'],
                    format_type,
                    url,
                    is_playlist=True,
                    playlist_name=playlist_name or "Multi-Download"
                )
        except Exception as e:
            error_msg = str(e)[:100]
            results.append({'success': False, 'error': error_msg, 'url': url})
            download_status[task_id]['results'].append({'success': False, 'error': error_msg})

        download_status[task_id]['completed'] = i + 1

    # Créer le ZIP
    zip_filename = None
    if len(downloaded_files) >= 1:
        download_status[task_id]['current_title'] = "Création du ZIP..."
        download_status[task_id]['current_progress'] = ''

        safe_name = sanitize_filename(playlist_name or "download")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"{safe_name}_{timestamp}.zip"
        zip_path = DOWNLOAD_DIR / zip_filename

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filename in downloaded_files:
                    file_path = DOWNLOAD_DIR / filename
                    if file_path.exists():
                        zf.write(file_path, filename)

            # Vérifier que le ZIP a été créé
            if zip_path.exists() and zip_path.stat().st_size > 0:
                print(f"ZIP créé: {zip_filename} ({zip_path.stat().st_size} bytes)")
            else:
                zip_filename = None
        except Exception as e:
            print(f"Erreur ZIP: {e}")
            zip_filename = None

    download_status[task_id]['status'] = 'completed'
    download_status[task_id]['zip_file'] = zip_filename
    download_status[task_id]['current_title'] = 'Terminé!'

    return results


# ============ ROUTES ============

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

            # Ajouter à l'historique
            add_to_history(result['title'], result['filename'], format_type, url)

            return jsonify({'success': True, 'data': result})
        else:
            # Multi-téléchargement
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
    filename = urllib.parse.unquote(filename)
    file_path = DOWNLOAD_DIR / filename

    if not file_path.exists():
        abort(404)

    return send_file(file_path, as_attachment=True, download_name=filename)


@app.route('/api/files')
def list_files():
    """Liste les fichiers téléchargés"""
    files = []
    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and not f.name.startswith('.') and f.name != '.gitkeep':
            files.append({
                'name': f.name,
                'size': f.stat().st_size,
                'modified': f.stat().st_mtime,
                'is_zip': f.suffix == '.zip'
            })
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'success': True, 'files': files})


@app.route('/api/history')
def get_history():
    """Retourne l'historique des téléchargements"""
    history = load_history()
    return jsonify({'success': True, 'history': history})


@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    """Efface l'historique"""
    save_history([])
    return jsonify({'success': True})


@app.route('/api/files/delete', methods=['POST'])
def delete_file():
    """Supprime un fichier"""
    filename = request.json.get('filename')
    if filename:
        file_path = DOWNLOAD_DIR / filename
        if file_path.exists():
            file_path.unlink()
            return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Fichier non trouvé'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
