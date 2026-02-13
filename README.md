# YouTube Downloader MP3/MP4

Téléchargeur YouTube avec interface web. Supporte les vidéos, playlists et téléchargements multiples.

## Fonctionnalités

- Téléchargement MP3 (128, 192, 320 kbps)
- Téléchargement MP4 (360p, 480p, 720p, best)
- Support des playlists YouTube
- Multi-téléchargement (plusieurs URLs)
- Création automatique de ZIP
- Stockage cloud optionnel (Cloudinary)

## Installation locale

```bash
# Prérequis: FFmpeg
brew install ffmpeg  # macOS

# Installation
cd youtube-downloader
pip install -r requirements.txt

# Lancer
python app.py
```

Ouvrir http://localhost:5000

## Déploiement (Render.com - Gratuit)

1. **Créer un compte Cloudinary** (gratuit): https://cloudinary.com
   - Copier l'URL `CLOUDINARY_URL` depuis le dashboard

2. **Déployer sur Render**:
   - Connecter ton repo GitHub sur https://render.com
   - Créer un "Web Service"
   - Ajouter la variable d'environnement `CLOUDINARY_URL`

3. **Alternative - Railway.app**:
   ```bash
   npm install -g @railway/cli
   railway login
   railway init
   railway up
   ```

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| `CLOUDINARY_URL` | URL Cloudinary pour stockage cloud |

## Structure

```
youtube-downloader/
├── app.py              # Application Flask
├── templates/
│   └── index.html      # Interface web
├── downloads/          # Fichiers téléchargés
├── requirements.txt
├── Procfile            # Pour Heroku/Render
├── render.yaml         # Config Render
└── .env.example
```

## Note légale

Usage personnel uniquement. Respectez les droits d'auteur.
