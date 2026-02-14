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
from datetime import datetime, timedelta

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
HISTORY_FILE = BASE_DIR / "history.json"
SETTINGS_FILE = BASE_DIR / "settings.json"

# Status des téléchargements en cours
download_status = {}


def load_settings():
    """Charge les paramètres depuis le fichier JSON"""
    default_settings = {
        'auto_cleanup_enabled': False,
        'cleanup_days': 7
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return {**default_settings, **settings}
        except:
            return default_settings
    return default_settings


def save_settings(settings):
    """Sauvegarde les paramètres dans le fichier JSON"""
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def cleanup_old_files(days=7):
    """Supprime les fichiers plus vieux que X jours"""
    cutoff = datetime.now() - timedelta(days=days)
    deleted = []

    for f in DOWNLOAD_DIR.iterdir():
        if f.is_file() and f.name != '.gitkeep':
            file_time = datetime.fromtimestamp(f.stat().st_mtime)
            if file_time < cutoff:
                try:
                    f.unlink()
                    deleted.append(f.name)
                except:
                    pass

    return deleted


def auto_cleanup_if_enabled():
    """Exécute le nettoyage si activé"""
    settings = load_settings()
    if settings.get('auto_cleanup_enabled', False):
        days = settings.get('cleanup_days', 7)
        cleanup_old_files(days)


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
    audio_formats = {'mp3', 'wav'}
    ext = format_type if format_type in audio_formats else 'mp4'

    def progress_hook(d):
        if d['status'] == 'downloading' and update_progress:
            percent_str = d.get('_percent_str', '0%').strip()
            speed_str = d.get('_speed_str', 'N/A')
            update_progress(percent_str, speed_str)

    if format_type in audio_formats:
        options = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type,
                'preferredquality': quality,
            }],
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'noplaylist': True,
            'progress_hooks': [progress_hook],
        }
    else:
        quality_map = {
            '4k': 2160,
            '1440': 1440,
            '1080': 1080,
            '720': 720,
            '480': 480,
            '360': 360,
        }
        height = quality_map.get(quality)

        if quality == "best" or not height:
            format_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        else:
            format_str = f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}]'

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


@app.route('/api/settings')
def get_settings():
    """Retourne les paramètres"""
    settings = load_settings()
    return jsonify({'success': True, 'settings': settings})


@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Met à jour les paramètres"""
    data = request.json
    settings = load_settings()
    settings.update(data)
    save_settings(settings)
    return jsonify({'success': True, 'settings': settings})


@app.route('/api/cleanup', methods=['POST'])
def api_cleanup():
    """Nettoie les vieux fichiers"""
    days = request.json.get('days', 7)
    deleted = cleanup_old_files(days)
    return jsonify({'success': True, 'deleted': deleted, 'count': len(deleted)})


@app.route('/api/convert', methods=['POST'])
def convert_file():
    """Convertit un fichier existant vers un autre format"""
    import subprocess

    filename = request.json.get('filename', '')
    target_format = request.json.get('target_format', 'mp3')

    if not filename:
        return jsonify({'success': False, 'error': 'Fichier non spécifié'})

    source_path = DOWNLOAD_DIR / filename
    if not source_path.exists():
        return jsonify({'success': False, 'error': 'Fichier non trouvé'})

    name_without_ext = source_path.stem
    output_path = DOWNLOAD_DIR / f"{name_without_ext}.{target_format}"

    try:
        cmd = ['ffmpeg', '-i', str(source_path), '-y']
        if target_format == 'mp3':
            cmd += ['-vn', '-ab', '192k', str(output_path)]
        elif target_format == 'wav':
            cmd += ['-vn', str(output_path)]
        elif target_format == 'mp4':
            cmd += [str(output_path)]

        subprocess.run(cmd, capture_output=True, check=True)
        return jsonify({'success': True, 'filename': output_path.name})
    except subprocess.CalledProcessError as e:
        return jsonify({'success': False, 'error': f'Erreur FFmpeg: {e.stderr.decode()[:200]}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/search', methods=['POST'])
def search_youtube():
    """Recherche sur YouTube"""
    try:
        query = request.json.get('query', '')
        max_results = request.json.get('max_results', 10)

        if not query:
            return jsonify({'success': False, 'error': 'Requête vide'})

        options = {
            'quiet': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            # Recherche YouTube
            search_url = f"ytsearch{max_results}:{query}"
            info = ydl.extract_info(search_url, download=False)

            results = []
            for entry in info.get('entries', []):
                if entry:
                    duration = int(entry.get('duration', 0) or 0)
                    minutes, seconds = divmod(duration, 60)
                    video_id = entry.get('id', '')
                    thumbnail = entry.get('thumbnail', '')
                    if not thumbnail and video_id:
                        thumbnail = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
                    results.append({
                        'id': video_id,
                        'title': entry.get('title', 'Unknown'),
                        'channel': entry.get('channel', entry.get('uploader', 'Unknown')),
                        'duration': f"{minutes}:{seconds:02d}",
                        'thumbnail': thumbnail,
                        'url': f"https://www.youtube.com/watch?v={video_id}",
                        'views': entry.get('view_count', 0),
                    })

            return jsonify({'success': True, 'results': results})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
