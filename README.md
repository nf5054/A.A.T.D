# Advanced Aerial Threat Detection

A high-performance desktop application for aerial image and video analysis, built with Python, CustomTkinter, OpenCV, and Hugging Face transformers.

## Overview

This project is designed to detect aerial threats in images, video, and live camera feeds. It includes:

- Zero-shot object detection for missiles, rockets, drones, fighter jets, fireballs, and more
- Real-time alert reporting with actionable metadata
- Exportable reports and processed media
- A clean UI with tabs for analysis, alerts, gallery, and settings

## UI Showcase

Below you can place screenshots from your app UI after you export the project to GitHub:

### Home / Analysis

![Home Screen](docs/screenshots/home.png)

### Alerts and Reports

![Alerts Screen](docs/screenshots/alerts.png)

### Photo Gallery

![Gallery Screen](docs/screenshots/gallery.png)

> Replace the example image paths above with your actual screenshot file paths once you upload them.

## How to Use

1. Open `python/project.py`
2. Install dependencies if needed
3. Run the app with:
   ```bash
   python python/project.py
   ```
4. Use the app tabs to load media, scan for threats, review alerts, and add your own gallery photos.

## Photo Gallery Instructions

The app contains a **Gallery** tab where you can add your own UI screenshots:

- Click `Add Photos` in the Gallery tab
- Select screenshots or sample images from your system
- The selected images will appear in the app gallery view

## Notes

- `photo_gallery.json` is used by the app to remember the images you add to the gallery.
- The app may download a Hugging Face model on first run and cache it locally.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
