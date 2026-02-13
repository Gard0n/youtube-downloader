#!/usr/bin/env python3
"""
YouTube Downloader - Interface graphique (Tkinter)
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from pathlib import Path
from downloader import YouTubeDownloader


class YouTubeDownloaderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("YouTube Downloader")
        self.root.geometry("500x400")
        self.root.resizable(False, False)

        self.downloader = YouTubeDownloader()
        self.is_downloading = False

        self.setup_ui()

    def setup_ui(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Titre
        title_label = ttk.Label(
            main_frame,
            text="YouTube Downloader",
            font=("Helvetica", 18, "bold")
        )
        title_label.pack(pady=(0, 20))

        # URL
        url_frame = ttk.LabelFrame(main_frame, text="URL YouTube", padding="10")
        url_frame.pack(fill=tk.X, pady=(0, 15))

        self.url_entry = ttk.Entry(url_frame, width=50)
        self.url_entry.pack(fill=tk.X)

        # Options
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 15))

        # Format
        format_frame = ttk.Frame(options_frame)
        format_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(format_frame, text="Format:").pack(side=tk.LEFT)
        self.format_var = tk.StringVar(value="mp3")
        ttk.Radiobutton(format_frame, text="MP3 (Audio)", variable=self.format_var,
                        value="mp3", command=self.update_quality_options).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(format_frame, text="MP4 (Vidéo)", variable=self.format_var,
                        value="mp4", command=self.update_quality_options).pack(side=tk.LEFT)

        # Qualité
        quality_frame = ttk.Frame(options_frame)
        quality_frame.pack(fill=tk.X)

        ttk.Label(quality_frame, text="Qualité:").pack(side=tk.LEFT)
        self.quality_var = tk.StringVar(value="192")
        self.quality_combo = ttk.Combobox(
            quality_frame,
            textvariable=self.quality_var,
            state="readonly",
            width=20
        )
        self.quality_combo.pack(side=tk.LEFT, padx=10)
        self.update_quality_options()

        # Boutons
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(0, 15))

        self.info_btn = ttk.Button(buttons_frame, text="Voir les infos", command=self.show_info)
        self.info_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.download_btn = ttk.Button(buttons_frame, text="Télécharger", command=self.start_download)
        self.download_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.folder_btn = ttk.Button(buttons_frame, text="Ouvrir dossier", command=self.open_folder)
        self.folder_btn.pack(side=tk.LEFT)

        # Progress
        self.progress_var = tk.StringVar(value="Prêt")
        self.progress_label = ttk.Label(main_frame, textvariable=self.progress_var)
        self.progress_label.pack(fill=tk.X)

        self.progress_bar = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, pady=(5, 15))

        # Info
        self.info_text = tk.Text(main_frame, height=6, state=tk.DISABLED)
        self.info_text.pack(fill=tk.BOTH, expand=True)

    def update_quality_options(self):
        if self.format_var.get() == "mp3":
            self.quality_combo['values'] = ["128 kbps", "192 kbps", "320 kbps"]
            self.quality_var.set("192 kbps")
        else:
            self.quality_combo['values'] = ["360p", "480p", "720p", "Meilleure qualité"]
            self.quality_var.set("Meilleure qualité")

    def get_url(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Attention", "Veuillez entrer une URL YouTube")
            return None
        return url

    def show_info(self):
        url = self.get_url()
        if not url:
            return

        def fetch_info():
            self.progress_var.set("Récupération des informations...")
            self.progress_bar.start()

            try:
                info = self.downloader.get_video_info(url)
                duration = info['duration']
                minutes, seconds = divmod(duration, 60)

                info_text = f"""Titre: {info['title']}
Chaîne: {info['channel']}
Durée: {minutes}:{seconds:02d}
"""
                self.update_info(info_text)
                self.progress_var.set("Informations récupérées")
            except Exception as e:
                self.progress_var.set("Erreur")
                messagebox.showerror("Erreur", str(e))
            finally:
                self.progress_bar.stop()

        threading.Thread(target=fetch_info, daemon=True).start()

    def start_download(self):
        if self.is_downloading:
            return

        url = self.get_url()
        if not url:
            return

        def download():
            self.is_downloading = True
            self.download_btn.config(state=tk.DISABLED)
            self.progress_bar.start()

            try:
                format_type = self.format_var.get()
                quality = self.quality_var.get()

                if format_type == "mp3":
                    q = quality.replace(" kbps", "")
                    self.progress_var.set(f"Téléchargement MP3 ({quality})...")
                    title = self.downloader.download_mp3(url, q)
                    self.update_info(f"Téléchargé: {title}.mp3")
                else:
                    q_map = {"360p": "360", "480p": "480", "720p": "720", "Meilleure qualité": "best"}
                    q = q_map.get(quality, "best")
                    self.progress_var.set(f"Téléchargement MP4 ({quality})...")
                    title = self.downloader.download_mp4(url, q)
                    self.update_info(f"Téléchargé: {title}.mp4")

                self.progress_var.set("Téléchargement terminé!")
                messagebox.showinfo("Succès", "Téléchargement terminé!")

            except Exception as e:
                self.progress_var.set("Erreur")
                messagebox.showerror("Erreur", str(e))

            finally:
                self.is_downloading = False
                self.download_btn.config(state=tk.NORMAL)
                self.progress_bar.stop()

        threading.Thread(target=download, daemon=True).start()

    def update_info(self, text):
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, text)
        self.info_text.config(state=tk.DISABLED)

    def open_folder(self):
        import subprocess
        import sys

        folder = Path("downloads").absolute()
        if sys.platform == "darwin":
            subprocess.run(["open", folder])
        elif sys.platform == "win32":
            subprocess.run(["explorer", folder])
        else:
            subprocess.run(["xdg-open", folder])

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = YouTubeDownloaderGUI()
    app.run()
