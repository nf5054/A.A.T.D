# A.A.T.D — Advanced Aerial Threat Detection

A fast desktop tool for aerial image and video threat detection, built with Python and a clean modern UI.

## What this project does

- Detects aerial threats in images, videos, and live camera feed
- Uses zero-shot object detection to find missiles, drones, rockets, fighter jets, fireballs, and more
- Records alerts with location-style metadata and confidence scores
- Exports reports and processed media
- Supports a photo gallery UI for your own screenshots and images

## Why this repo is here

This repo is set up to showcase your app and give users a clean entry point when they land on GitHub.
It includes:

- `README.md` with project description and UI screenshot placeholders
- `LICENSE` under MIT terms
- `.gitignore` for Python and local workspace files

## Recommended screenshots

Add your app screenshots to these paths and update the links if needed:

- `docs/screenshots/home.png` — main detection screen
- `docs/screenshots/alerts.png` — alerts review screen
- `docs/screenshots/gallery.png` — gallery UI screen

### Example image block

![Home Screen](docs/screenshots/home.png)

![Alerts Screen](docs/screenshots/alerts.png)

![Gallery Screen](docs/screenshots/gallery.png)

> Tip: create the `docs/screenshots` folder and upload real screenshots there so GitHub displays your UI in the README.

## How to run the app

1. Open `python/project.py`
2. Install required Python dependencies if needed
3. Run:
   ```bash
   python python/project.py
   ```

## Gallery instructions

The app has a built-in Gallery tab for UI and photo placement.

- Open the Gallery tab in the app
- Click `Add Photos`
- Select one or more images
- The selected photos appear in the gallery view

## Notes

- The app may download the Hugging Face model the first time it runs and cache it locally.
- `alerts_save.json` stores alert history locally.
- `photo_gallery.json` stores the gallery image list when you add photos.

## License

This project uses the MIT License. See `LICENSE` for full terms.
