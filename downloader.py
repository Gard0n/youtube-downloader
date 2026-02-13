#!/usr/bin/env python3
"""
YouTube Downloader - Télécharge des vidéos YouTube en MP3 ou MP4
"""

import yt_dlp
import os
import sys
from pathlib import Path


class YouTubeDownloader:
    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def get_video_info(self, url: str) -> dict:
        """Récupère les informations de la vidéo"""
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'channel': info.get('channel', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                }
            except Exception as e:
                raise Exception(f"Erreur lors de la récupération des infos: {e}")

    def download_mp3(self, url: str, quality: str = "192") -> str:
        """Télécharge la vidéo en MP3"""
        options = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality,
            }],
            'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
            'progress_hooks': [self._progress_hook],
        }

        return self._download(url, options)

    def download_mp4(self, url: str, quality: str = "best") -> str:
        """Télécharge la vidéo en MP4"""
        if quality == "best":
            format_str = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        elif quality == "720":
            format_str = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]'
        elif quality == "480":
            format_str = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]'
        elif quality == "360":
            format_str = 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]'
        else:
            format_str = 'best[ext=mp4]/best'

        options = {
            'format': format_str,
            'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'progress_hooks': [self._progress_hook],
        }

        return self._download(url, options)

    def _download(self, url: str, options: dict) -> str:
        """Effectue le téléchargement"""
        with yt_dlp.YoutubeDL(options) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                return info.get('title', 'Téléchargement terminé')
            except Exception as e:
                raise Exception(f"Erreur de téléchargement: {e}")

    def _progress_hook(self, d):
        """Affiche la progression du téléchargement"""
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', 'N/A')
            speed = d.get('_speed_str', 'N/A')
            print(f"\r  Téléchargement: {percent} à {speed}", end='', flush=True)
        elif d['status'] == 'finished':
            print(f"\n  Téléchargement terminé, conversion en cours...")


def print_banner():
    """Affiche le banner"""
    print("""
╔══════════════════════════════════════════╗
║       YouTube Downloader MP3/MP4         ║
╚══════════════════════════════════════════╝
    """)


def main():
    print_banner()
    downloader = YouTubeDownloader()

    while True:
        print("\nOptions:")
        print("  1. Télécharger en MP3 (audio)")
        print("  2. Télécharger en MP4 (vidéo)")
        print("  3. Voir les infos d'une vidéo")
        print("  4. Quitter")

        choice = input("\nChoix (1-4): ").strip()

        if choice == "4":
            print("Au revoir!")
            break

        if choice not in ["1", "2", "3"]:
            print("Choix invalide!")
            continue

        url = input("URL YouTube: ").strip()

        if not url:
            print("URL invalide!")
            continue

        try:
            if choice == "3":
                print("\nRécupération des informations...")
                info = downloader.get_video_info(url)
                print(f"\n  Titre: {info['title']}")
                print(f"  Chaîne: {info['channel']}")
                duration = info['duration']
                minutes, seconds = divmod(duration, 60)
                print(f"  Durée: {minutes}:{seconds:02d}")

            elif choice == "1":
                print("\nQualité audio:")
                print("  1. 128 kbps")
                print("  2. 192 kbps (recommandé)")
                print("  3. 320 kbps (meilleure qualité)")
                q = input("Choix (1-3, défaut=2): ").strip() or "2"
                quality = {"1": "128", "2": "192", "3": "320"}.get(q, "192")

                print(f"\nTéléchargement en MP3 ({quality} kbps)...")
                title = downloader.download_mp3(url, quality)
                print(f"\n  Fichier sauvegardé: downloads/{title}.mp3")

            elif choice == "2":
                print("\nQualité vidéo:")
                print("  1. 360p")
                print("  2. 480p")
                print("  3. 720p")
                print("  4. Meilleure qualité")
                q = input("Choix (1-4, défaut=4): ").strip() or "4"
                quality = {"1": "360", "2": "480", "3": "720", "4": "best"}.get(q, "best")

                print(f"\nTéléchargement en MP4 ({quality})...")
                title = downloader.download_mp4(url, quality)
                print(f"\n  Fichier sauvegardé: downloads/{title}.mp4")

        except Exception as e:
            print(f"\nErreur: {e}")


if __name__ == "__main__":
    main()
