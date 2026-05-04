import os
import sys
import warnings
import logging

# Suppress annoying huggingface offline warning about TRANSFORMERS_CACHE
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

# --- PYINSTALLER CERTIFICATE FIX ---
# This prevents the "Could not find a suitable TLS CA certificate bundle" error
# when running offline as a PyInstaller executable without certifi bundled.
if hasattr(sys, '_MEIPASS'):
    cert_dir = os.path.join(sys._MEIPASS, 'certifi')
    cert_path = os.path.join(cert_dir, 'cacert.pem')
    if not os.path.exists(cert_path):
        try:
            os.makedirs(cert_dir, exist_ok=True)
            with open(cert_path, 'w') as f:
                pass # Create dummy file to bypass the path check
        except Exception:
            pass
# -----------------------------------

# --- OFFLINE CACHE SETUP ---
# It will save and load the model from a 'model_cache' folder next to the script
# This MUST be set before importing transformers!
model_cache_path = os.path.join(os.getcwd(), "model_cache")
os.makedirs(model_cache_path, exist_ok=True)
os.environ["HF_HOME"] = model_cache_path
os.environ["HF_HUB_CACHE"] = model_cache_path
# ---------------------------

import threading
import multiprocessing
import cv2  # New: OpenCV for video processing
import numpy as np # New: For video export
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw
import scipy # Required by transformers for OWLv2 image processing
from transformers import pipeline
import tkinter.filedialog as fd
import torch # Required for GPU check
import json
import random
import urllib.request
import io
try:
    import winsound
except ImportError:
    winsound = None
import base64
import time

# --- USER CONFIGURATION ---
# IMPORTANT: Provide the path to your logo below.
# By default, it will look for a file named "logo.png" in the same folder as this script.
# Example: LOCAL_LOGO_PATH = "logo.png"
# If left empty or file not found, the app will show text "RSADF" instead of an image.
LOCAL_LOGO_PATH = "logo.png"
# --------------------------

_app_mode = "Dark"
try:
    with open("config.json", "r") as f:
        conf = json.load(f)
        _app_mode = conf.get("appearance", "Dark")
except:
    pass

if _app_mode == "Forest":
    ctk.set_appearance_mode("Dark")
else:
    ctk.set_appearance_mode(_app_mode)
    
ctk.set_default_color_theme("blue")

class ThreatDetectorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.current_appearance = _app_mode

        self.title("Advanced Aerial Threat Detection")
        self.geometry("1100x780")

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1) # Column 1 is main area now

        self.detector = None
        self.current_image_path = None
        self.current_video_path = None
        self.is_processing_video = False
        self.is_playing_smooth = False
        
        self.threat_labels = ["missile", "rocket", "drone", "fighter jet", "light streak", "fireball"] 
        self.ignore_labels = ["cloud", "bird", "airplane", "tree", "building", "sun", "sunset", "star", "moon"]
        self.all_labels = self.threat_labels + self.ignore_labels

        self.alerts_list = []
        self.alert_played = False
        self.sound_enabled = ctk.BooleanVar(value=True)
        self.camera_index = ctk.StringVar(value="0")

        self.setup_ui()
        self.load_model_thread()

    def setup_ui(self):
        # TOP BAR
        self.top_bar = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.top_bar.grid_propagate(False)
        self.top_bar.grid_columnconfigure(1, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.top_bar, text="RSADF")
        self.logo_label.grid(row=0, column=0, padx=20, pady=5, sticky="w")
        
        try:
            logo_path = LOCAL_LOGO_PATH
            if logo_path and os.path.exists(logo_path):
                img = Image.open(logo_path).convert("RGBA").resize((60, 60))
                self.logo_img_ref = ctk.CTkImage(light_image=img, dark_image=img, size=(60, 60))
                self.logo_label.configure(image=self.logo_img_ref, text="")
            else:
                self.logo_label.configure(text="RSADF")
        except Exception as e:
            print("Failed to load logo:", e)
            self.logo_label.configure(text="RSADF")

        self.title_label = ctk.CTkLabel(self.top_bar, text="Advanced Aerial Threat Detection", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.grid(row=0, column=1)

        self.status_label = ctk.CTkLabel(self.top_bar, text="● IDLE", text_color="green", font=ctk.CTkFont(size=14, weight="bold"))
        self.status_label.grid(row=0, column=2, padx=20, sticky="e")

        # LEFT NAV (Tabs)
        self.left_nav = ctk.CTkFrame(self, width=150, corner_radius=0, fg_color=("gray20", "gray8"))
        self.left_nav.grid(row=1, column=0, sticky="ns")
        self.left_nav.grid_propagate(False)

        self.nav_btns = {}
        for text, key in [("🏠 Home", "home"), ("🚨 Alerts", "alerts"), ("⚙️ Settings", "settings")]:
            btn = ctk.CTkButton(self.left_nav, text=text, command=lambda k=key: self.show_tab(k), fg_color="transparent", text_color="white", hover_color=("gray30", "gray18"))
            btn.pack(pady=10, padx=10, fill="x")
            self.nav_btns[key] = btn

        # MAIN CONTENT
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        self.frames = {}
        
        # TAB 1 - HOME
        self.frames["home"] = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.frames["home"].grid(row=0, column=0, sticky="nsew")

        self.banner = ctk.CTkLabel(self.frames["home"], text="⚠ THREAT DETECTED: [label]", fg_color="red", text_color="white", height=30, font=ctk.CTkFont(weight="bold"))
        self.banner.bind("<Button-1>", lambda e: self.banner.place_forget())

        self.image_label = ctk.CTkLabel(self.frames["home"], text="", width=700, height=420, fg_color="black")
        self.image_label.pack(pady=(20, 10))
        self.draw_radar()

        self.source_mode = ctk.StringVar(value="Image")
        self.source_seg = ctk.CTkSegmentedButton(self.frames["home"], values=["Image", "Video", "Live Camera"], variable=self.source_mode, command=self.on_mode_change)
        self.source_seg.pack(pady=5)

        row_controls = ctk.CTkFrame(self.frames["home"], fg_color="transparent")
        row_controls.pack(pady=10)

        self.btn_load = ctk.CTkButton(row_controls, text="Load Media", command=self.load_media, state="disabled")
        self.btn_load.pack(side="left", padx=10)

        self.btn_scan = ctk.CTkButton(row_controls, text="Scan", command=self.start_scan, state="disabled", fg_color="darkred", hover_color="red")
        self.btn_scan.pack(side="left", padx=10)

        self.btn_export = ctk.CTkButton(row_controls, text="Export Results", command=self.export_results, state="disabled")
        self.btn_export.pack(side="left", padx=10)

        self.progress_bar = ctk.CTkProgressBar(self.frames["home"], width=400)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(0, 5))
        self.progress_bar.pack_forget()

        self.eta_label = ctk.CTkLabel(self.frames["home"], text="ETA: --:--", text_color="gray", font=ctk.CTkFont(size=12))
        self.eta_label.pack(pady=(0, 10))
        self.eta_label.pack_forget()

        self.log_box = ctk.CTkTextbox(self.frames["home"], height=100)
        self.log_box.pack(pady=(15, 10), fill="x", padx=20)

        # TAB 2 - ALERTS
        self.frames["alerts"] = ctk.CTkScrollableFrame(self.main_area, fg_color="transparent")
        self.frames["alerts"].grid(row=0, column=0, sticky="nsew")
        ctk.CTkButton(self.frames["alerts"], text="🗑 Clear All", command=self.clear_alerts, fg_color="red").pack(anchor="ne", pady=5, padx=10)
        self.alerts_container = ctk.CTkFrame(self.frames["alerts"], fg_color="transparent")
        self.alerts_container.pack(fill="both", expand=True)

        # TAB 3 - SETTINGS
        self.frames["settings"] = ctk.CTkScrollableFrame(self.main_area, fg_color="transparent")
        self.frames["settings"].grid(row=0, column=0, sticky="nsew")
        
        self.lbl_sens = ctk.CTkLabel(self.frames["settings"], text="Sensitivity: 15%")
        self.lbl_sens.pack(pady=(20, 5))
        self.slider = ctk.CTkSlider(self.frames["settings"], from_=5, to=50, command=lambda v: self.lbl_sens.configure(text=f"Sensitivity: {int(v)}%"))
        self.slider.set(15)
        self.slider.pack(pady=5)

        ctk.CTkLabel(self.frames["settings"], text="Detection Labels").pack(pady=5)
        self.txt_threats = ctk.CTkTextbox(self.frames["settings"], height=80)
        self.txt_threats.insert("1.0", "\n".join(self.threat_labels))
        self.txt_threats.pack(fill="x", padx=20)

        ctk.CTkLabel(self.frames["settings"], text="Ignore Labels").pack(pady=5)
        self.txt_ignore = ctk.CTkTextbox(self.frames["settings"], height=80)
        self.txt_ignore.insert("1.0", "\n".join(self.ignore_labels))
        self.txt_ignore.pack(fill="x", padx=20)

        ctk.CTkCheckBox(self.frames["settings"], text="Enable Alert Sound", variable=self.sound_enabled).pack(pady=5)
        
        ctk.CTkLabel(self.frames["settings"], text="Camera Index").pack(pady=(10, 0))
        ctk.CTkEntry(self.frames["settings"], textvariable=self.camera_index).pack(pady=5)

        ctk.CTkLabel(self.frames["settings"], text="Appearance Mode (Applies on restart)").pack(pady=(10, 0))
        self.opt_appearance = ctk.CTkOptionMenu(self.frames["settings"], values=["Dark", "Light", "System", "Forest"], command=self.change_appearance)
        self.opt_appearance.set(self.current_appearance)
        self.opt_appearance.pack(pady=5)
        
        self.btn_save = ctk.CTkButton(self.frames["settings"], text="💾 Save Settings", command=self.save_settings)
        self.btn_save.pack(pady=10)
        ctk.CTkButton(self.frames["settings"], text="↺ Reset to Defaults", command=self.reset_settings).pack(pady=5)

        self.load_settings()
        self.load_alerts()
        self.show_tab("home")
        self.apply_forest_theme_if_needed()

    def apply_forest_theme_if_needed(self):
        if self.current_appearance == "Forest":
            self.configure(fg_color="#101c15") # Dark dark green
            self.top_bar.configure(fg_color="#0a120e")
            self.left_nav.configure(fg_color="#0a120e")
            for btn in self.nav_btns.values():
                if btn.cget("fg_color") != "#1b4028": # If not active
                    btn.configure(fg_color="transparent", text_color="#a8d5ba", hover_color="#142b1d")
            
            dark_green = "#1a5c32"
            dark_green_hover = "#124223"
            
            self.btn_load.configure(fg_color=dark_green, hover_color=dark_green_hover)
            self.btn_export.configure(fg_color=dark_green, hover_color=dark_green_hover)
            self.btn_save.configure(fg_color=dark_green, hover_color=dark_green_hover)
            
            self.slider.configure(button_color=dark_green, button_hover_color=dark_green_hover, progress_color=dark_green)
            self.source_seg.configure(selected_color=dark_green, selected_hover_color=dark_green_hover)
            self.opt_appearance.configure(fg_color=dark_green, button_color=dark_green, button_hover_color=dark_green_hover)
            
        else:
            # Revert to default CTk colors
            self.configure(fg_color=("gray95", "gray14"))
            self.top_bar.configure(fg_color=("gray88", "gray17"))
            self.left_nav.configure(fg_color=("gray20", "gray8"))
            for btn in self.nav_btns.values():
                if btn.cget("fg_color") != ("gray40", "gray25"): # If not active
                    btn.configure(fg_color="transparent", text_color="white", hover_color=("gray30", "gray18"))
            
            # Since theme is set to 'blue', revert colors to standard default so they pick up blue
            self.btn_load.configure(fg_color=["#3a7ebf", "#1f538d"], hover_color=["#325882", "#14375e"])
            self.btn_export.configure(fg_color=["#3a7ebf", "#1f538d"], hover_color=["#325882", "#14375e"])
            self.btn_save.configure(fg_color=["#3a7ebf", "#1f538d"], hover_color=["#325882", "#14375e"])
            
            self.source_seg.configure(selected_color=["#3a7ebf", "#1f538d"], selected_hover_color=["#325882", "#14375e"])
            self.slider.configure(button_color=["#3a7ebf", "#1f538d"], button_hover_color=["#325882", "#14375e"], progress_color=["#3a7ebf", "#1f538d"])
            self.opt_appearance.configure(fg_color=["#3a7ebf", "#1f538d"], button_color=["#325882", "#14375e"], button_hover_color=["#233f5e", "#102947"])
    
    def show_tab(self, key):
        active_color = "#1b4028" if self.current_appearance == "Forest" else ("gray40", "gray25")
        for btn in self.nav_btns.values():
            btn.configure(fg_color="transparent")
        self.nav_btns[key].configure(fg_color=active_color)
        
        for k, f in self.frames.items():
            if k == key:
                f.grid(row=0, column=0, sticky="nsew")
            else:
                f.grid_remove()

    def change_appearance(self, new_appearance_mode: str):
        self.current_appearance = new_appearance_mode
        self.save_settings()
        import sys
        import os
        os.execl(sys.executable, sys.executable, *sys.argv)

    def draw_radar(self):
        img = Image.new("RGB", (700, 420), "black")
        draw = ImageDraw.Draw(img)
        for i in range(0, 700, 40): draw.line([(i, 0), (i, 420)], fill="#003300", width=1)
        for i in range(0, 420, 40): draw.line([(0, i), (700, i)], fill="#003300", width=1)
        draw.line([(350, 0), (350, 420)], fill="#006600", width=2)
        draw.line([(0, 210), (700, 210)], fill="#006600", width=2)
        
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(700, 420))
        self.image_label.configure(image=ctk_img)
        self.image_label.image_ref = ctk_img

    def animate_banner(self, label):
        self.banner.configure(text=f"⚠ THREAT DETECTED: {label}")
        self.banner.lift()
        def drop(y):
            if y <= 10:
                self.banner.place(relx=0.5, y=y, anchor="n")
                self.after(20, lambda: drop(y+5))
        drop(-50)
        
        self.status_label.configure(text="● THREAT DETECTED", text_color="red")
        self.blink_status(0)

    def blink_status(self, count):
        if count >= 10:
            return
        colors = ["red", "white"]
        self.status_label.configure(text_color=colors[count % 2])
        self.after(300, lambda: self.blink_status(count+1))

    def reset_status(self):
        self.status_label.configure(text="● IDLE", text_color="green")
        self.banner.place_forget()

    def save_settings(self):
        self.threat_labels = [l.strip() for l in self.txt_threats.get("1.0", "end").splitlines() if l.strip()]
        self.ignore_labels = [l.strip() for l in self.txt_ignore.get("1.0", "end").splitlines() if l.strip()]
        self.all_labels = self.threat_labels + self.ignore_labels
        data = {
            "threats": self.threat_labels,
            "ignores": self.ignore_labels,
            "sound": self.sound_enabled.get(),
            "camera": self.camera_index.get(),
            "sensitivity": self.slider.get(),
            "appearance": self.opt_appearance.get()
        }
        with open("config.json", "w") as f:
            json.dump(data, f)
        self.btn_save.configure(text="Saved!")
        self.after(2000, lambda: self.btn_save.configure(text="💾 Save Settings"))

    def load_settings(self):
        try:
            with open("config.json", "r") as f:
                data = json.load(f)
                self.threat_labels = data.get("threats", self.threat_labels)
                self.ignore_labels = data.get("ignores", self.ignore_labels)
                self.all_labels = self.threat_labels + self.ignore_labels
                self.sound_enabled.set(data.get("sound", True))
                self.camera_index.set(data.get("camera", "0"))
                sens = data.get("sensitivity", 15)
                self.slider.set(sens)
                self.lbl_sens.configure(text=f"Sensitivity: {int(sens)}%")
                
                app_mode = data.get("appearance", "Dark")
                self.opt_appearance.set(app_mode)
                self.current_appearance = app_mode
                # change_appearance triggers a restart, so we ONLY want to set the values, NOT call it here, 
                # because we already handle the overall Appearance at the top of the file!
                
                self.txt_threats.delete("1.0", "end")
                self.txt_threats.insert("1.0", "\n".join(self.threat_labels))
                self.txt_ignore.delete("1.0", "end")
                self.txt_ignore.insert("1.0", "\n".join(self.ignore_labels))
        except Exception:
            pass

    def reset_settings(self):
        self.threat_labels = ["missile", "rocket", "drone", "fighter jet", "light streak", "fireball"] 
        self.ignore_labels = ["cloud", "bird", "airplane", "tree", "building", "sun", "sunset", "star", "moon"]
        self.txt_threats.delete("1.0", "end")
        self.txt_threats.insert("1.0", "\n".join(self.threat_labels))
        self.txt_ignore.delete("1.0", "end")
        self.txt_ignore.insert("1.0", "\n".join(self.ignore_labels))
        self.slider.set(15)
        self.lbl_sens.configure(text="Sensitivity: 15%")
        self.sound_enabled.set(True)
        self.camera_index.set("0")
        self.opt_appearance.set("Dark")
        self.change_appearance("Dark")
        self.save_settings()

    def add_alert(self, label, confidence, frame_image, video_path=None):
        if not self.alert_played and self.sound_enabled.get():
            self.alert_played = True
            try:
                if winsound:
                    def siren():
                        for _ in range(3):
                            winsound.Beep(2500, 200)
                            winsound.Beep(2000, 200)
                    threading.Thread(target=siren, daemon=True).start()
            except: pass
            
        import datetime
        dt_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lat = random.uniform(20.0, 30.0)
        lon = random.uniform(36.0, 56.0)
        aid = len(self.alerts_list)
        
        self.alerts_list.insert(0, {
            "id": aid, "dt": dt_str, "lat": lat, "lon": lon, 
            "label": label, "conf": confidence, "img": frame_image, "is_new": True,
            "video_path": video_path
        })
        self.save_alerts()
        self.render_alerts()

    def clear_alerts(self):
        self.alerts_list = []
        self.save_alerts()
        self.render_alerts()

    def delete_alert(self, alert):
        self.alerts_list.remove(alert)
        self.save_alerts()
        self.render_alerts()
        
    def save_alerts(self):
        alerts_data = []
        for a in self.alerts_list:
            if isinstance(a["img"], Image.Image):
                buffered = io.BytesIO()
                a["img"].save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            else:
                img_str = a.get("img_base64", "")
            
            alerts_data.append({
                "id": a["id"], "dt": a["dt"], "lat": a["lat"], "lon": a["lon"],
                "label": a["label"], "conf": a["conf"], "img_base64": img_str,
                "video_path": a.get("video_path"),
                "is_processed": a.get("is_processed", False)
            })
            
        threading.Thread(target=self._write_alerts_file, args=(alerts_data,), daemon=True).start()

    def _write_alerts_file(self, alerts_data):
        try:
            with open("alerts_save.json", "w") as f:
                json.dump(alerts_data, f)
        except Exception as e:
            print(f"Error saving alerts: {e}")
            
    def load_alerts(self):
        try:
            with open("alerts_save.json", "r") as f:
                alerts_data = json.load(f)
                for a in alerts_data:
                    img_bytes = base64.b64decode(a["img_base64"])
                    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    self.alerts_list.append({
                        "id": a["id"], "dt": a["dt"], "lat": a["lat"], "lon": a["lon"],
                        "label": a["label"], "conf": a["conf"], "img": img, "is_new": False,
                        "video_path": a.get("video_path"),
                        "is_processed": a.get("is_processed", False)
                    })
            self.render_alerts()
        except Exception:
            pass

    def render_alerts(self):
        for w in self.alerts_container.winfo_children(): w.destroy()
        
        for alert in self.alerts_list:
            row = ctk.CTkFrame(self.alerts_container)
            row.pack(fill="x", pady=2, padx=5)
            
            # Flashing
            is_new = alert.get("is_new", False)
            if is_new:
                alert["is_new"] = False
                def flash(r=row, c=0):
                    if not r.winfo_exists(): return
                    if c >= 6: 
                        r.configure(fg_color=("gray75", "gray25"))
                        return
                    r.configure(fg_color="darkred" if c%2==0 else ("gray75", "gray25"))
                    self.after(200, lambda: flash(r, c+1))
                flash()
                
            thumb = alert["img"].copy()
            thumb.thumbnail((60, 60))
            timg = ctk.CTkImage(thumb, size=(60, 60))
            l = ctk.CTkLabel(row, image=timg, text="")
            l.image = timg
            l.pack(side="left", padx=5, pady=5)
            
            info = f"{alert['dt']} | SA GPS: {alert['lat']:.4f}, {alert['lon']:.4f} | {alert['label'].upper()} ({alert['conf']*100:.1f}%)"
            ctk.CTkLabel(row, text=info).pack(side="left", padx=10)
            
            ctk.CTkButton(row, text="✕", width=30, fg_color="red", command=lambda a=alert: self.delete_alert(a)).pack(side="right", padx=5)
            ctk.CTkButton(row, text="👁 View", width=60, command=lambda a=alert: self.view_alert(a)).pack(side="right", padx=5)

    def view_alert(self, alert):
        try:
            top = ctk.CTkToplevel(self)
            top.title("Alert Report & Media")
            top.geometry("850x700")
            
            # Use grab_set and topmost to prevent it from disappearing
            top.grab_set()
            top.attributes("-topmost", True)
            self.after(500, lambda: top.attributes("-topmost", False))
            
            # Display image by default
            img = alert["img"].copy()
            img.thumbnail((700, 420))
            timg = ctk.CTkImage(img, size=(img.width, img.height))
            media_lbl = ctk.CTkLabel(top, image=timg, text="", width=700, height=420, bg_color="black")
            media_lbl.image = timg
            media_lbl.pack(pady=10)
            
            info = f"Date: {alert.get('dt', '')}\nLocation: {alert.get('lat', 0.0):.4f}, {alert.get('lon', 0.0):.4f}\nThreat: {alert.get('label', '').upper()}\nConfidence: {alert.get('conf', 0.0)*100:.1f}%"
            ctk.CTkLabel(top, text=info, justify="left", font=("Helvetica", 14, "bold")).pack(pady=5)
            
            # Export Buttons
            btn_frame = ctk.CTkFrame(top, fg_color="transparent")
            btn_frame.pack(pady=10)
            
            def export_txt():
                p = fd.asksaveasfilename(defaultextension=".txt", initialfile=f"alert_{alert['id']}.txt", filetypes=[("Text", "*.txt")])
                if p: 
                    with open(p, "w") as f: f.write(info)
                    
            def export_img():
                p = fd.asksaveasfilename(defaultextension=".png", initialfile=f"alert_{alert['id']}.png", filetypes=[("PNG", "*.png")])
                if p: alert['img'].save(p)

            ctk.CTkButton(btn_frame, text="📄 Export Text Report", command=export_txt).pack(side="left", padx=5)
            ctk.CTkButton(btn_frame, text="🖼 Export Image Frame", command=export_img).pack(side="left", padx=5)
            
            has_video = alert.get("video_path") and isinstance(alert["video_path"], str) and os.path.exists(alert["video_path"])
            
            if has_video:
                b_exp_vid = ctk.CTkButton(btn_frame, text="🎬 Export Processed Video", fg_color="#8B0000", hover_color="#600000")
                b_play_vid = ctk.CTkButton(btn_frame, text="▶ Play Video (Smooth)", fg_color="#00008B", hover_color="#000060")
                prog_bar = ctk.CTkProgressBar(top, width=400)
                prog_lbl = ctk.CTkLabel(top, text="")
                
                if alert["video_path"] == getattr(self, "current_video_path", None) and hasattr(self, "processed_frames") and self.processed_frames:
                    top.processed_frames = self.processed_frames
                else:
                    top.processed_frames = []
                top.is_processing = False
                top.play_idx = 0
                
                def analyze_video(p=None, play_after=False):
                    top.is_processing = True
                    b_exp_vid.configure(state="disabled")
                    b_play_vid.configure(state="disabled")
                    prog_bar.pack(pady=5)
                    prog_bar.set(0)
                    prog_lbl.pack(pady=5)
                    self.log("Analyzing Video... Please wait!")
                    
                    def worker():
                        try:
                            cap = cv2.VideoCapture(alert["video_path"])
                            total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            
                            w = w if w % 2 == 0 else w - 1
                            h = h if h % 2 == 0 else h - 1

                            out = None
                            if p: out = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*'mp4v'), 30.0, (w, h))

                            thresh = self.slider.get()/100.0
                            cur = 0
                            st = time.time()
                            top.processed_frames = []
                            
                            while cap.isOpened() and top.winfo_exists():
                                ret, frame = cap.read()
                                if not ret: break
                                cur += 1
                                imgV = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                                if hasattr(self, 'detector') and not alert.get("is_processed"):
                                    try:
                                        res = self.detector(imgV, candidate_labels=self.all_labels, threshold=thresh)
                                        draw = ImageDraw.Draw(imgV)
                                        for r in res:
                                            if r['score'] >= thresh:
                                                wb, hb = r['box']['xmax'] - r['box']['xmin'], r['box']['ymax'] - r['box']['ymin']
                                                if wb * hb <= imgV.width * imgV.height * 0.04 and wb <= imgV.width * 0.2 and hb <= imgV.height * 0.2:
                                                    b = r['box']
                                                    draw.rectangle([b['xmin'], b['ymin'], b['xmax'], b['ymax']], outline="red", width=4)
                                                    draw.text((b['xmin'], b['ymin']-15), f"{r['label']}: {r['score']:.2f}", fill="red")
                                    except Exception: pass
                                
                                top.processed_frames.append(imgV.copy())
                                if out:
                                    frame_bgr = cv2.cvtColor(np.array(imgV), cv2.COLOR_RGB2BGR)
                                    frame_bgr = cv2.resize(frame_bgr, (w, h))
                                    out.write(frame_bgr)
                                
                                if total_f > 0 and cur % 3 == 0:
                                    elp = time.time() - st
                                    fps = cur / elp if elp > 0 else 0
                                    eta = int((total_f - cur) / fps) if fps > 0 else 0
                                    def update_ui(pv, es, im):
                                        prog_bar.set(pv)
                                        prog_lbl.configure(text=f"Analyzing... ETA: {es//60:02d}:{es%60:02d}")
                                        im.thumbnail((700, 420))
                                        media_lbl.configure(image=ctk.CTkImage(im, size=(im.width, im.height)))
                                    try: top.after(0, lambda pv=cur/total_f, es=eta, im=imgV.copy(): update_ui(pv, es, im))
                                    except: pass
                                    
                            cap.release()
                            if out: out.release()
                            
                            def finish():
                                prog_bar.pack_forget()
                                prog_lbl.pack_forget()
                                b_exp_vid.configure(state="normal")
                                b_play_vid.configure(state="normal")
                                top.is_processing = False
                                if p: self.log(f"Exported to {p}")
                                if play_after: toggle_video()
                            try: top.after(0, finish)
                            except: pass
                        except Exception as e:
                            self.log(str(e))
                            top.is_processing = False
                    
                    threading.Thread(target=worker, daemon=True).start()

                def export_vid():
                    if top.is_processing: return
                    if alert.get("is_processed") and os.path.exists(alert["video_path"]):
                        p = fd.asksaveasfilename(defaultextension=".mp4", initialfile=f"alert_{alert['id']}_processed.mp4", filetypes=[("MP4", "*.mp4")])
                        if p:
                            import shutil
                            shutil.copy(alert["video_path"], p)
                            self.log(f"Export complete: {p}")
                        return
                    if top.processed_frames:
                        p = fd.asksaveasfilename(defaultextension=".mp4", initialfile=f"alert_{alert['id']}_exported.mp4", filetypes=[("MP4", "*.mp4")])
                        if not p: return
                        self.log("Exporting directly from cache... Please wait!")
                        def fast_export():
                            try:
                                w, h = top.processed_frames[0].width, top.processed_frames[0].height
                                w = w if w % 2 == 0 else w - 1
                                h = h if h % 2 == 0 else h - 1
                                out = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*'mp4v'), 30.0, (w, h))
                                for im in top.processed_frames:
                                    frame_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
                                    frame_bgr = cv2.resize(frame_bgr, (w, h))
                                    out.write(frame_bgr)
                                out.release()
                                self.log(f"Export complete: {p}")
                            except Exception as e: self.log(str(e))
                        threading.Thread(target=fast_export, daemon=True).start()
                        return

                    p = fd.asksaveasfilename(defaultextension=".mp4", initialfile=f"alert_{alert['id']}_processed.mp4", filetypes=[("MP4", "*.mp4")])
                    if p: analyze_video(p, False)

                top.play_video = False
                def play_loop_stream():
                    if not top.winfo_exists() or not top.play_video: return
                    ret, frame = getattr(top, "stream_cap", None).read() if hasattr(top, "stream_cap") else (False, None)
                    if not ret and hasattr(top, "stream_cap"):
                        top.stream_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = top.stream_cap.read()
                    if ret:
                        fi = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                        fi.thumbnail((700, 420), Image.NEAREST)
                        ci = ctk.CTkImage(fi, size=(fi.width, fi.height))
                        media_lbl.configure(image=ci)
                        media_lbl.image = ci
                    top.after(33, play_loop_stream)

                def play_loop():
                    if not top.winfo_exists() or not top.play_video: return
                    if hasattr(top, 'processed_frames') and top.processed_frames:
                        fi = top.processed_frames[top.play_idx].copy()
                        fi.thumbnail((700, 420), Image.NEAREST)
                        ci = ctk.CTkImage(fi, size=(fi.width, fi.height))
                        media_lbl.configure(image=ci)
                        media_lbl.image = ci
                        top.play_idx = (top.play_idx + 1) % len(top.processed_frames)
                    top.after(33, play_loop)

                def toggle_video():
                    if getattr(top, "is_processing", False): return
                    
                    if top.play_video:
                        top.play_video = False
                        media_lbl.configure(image=timg)
                        b_play_vid.configure(text="▶ Play Video (Smooth)")
                        return
                        
                    top.play_video = True
                    b_play_vid.configure(text="⏸ Pause Video")
                    
                    is_processed_flag = alert.get("is_processed") and os.path.exists(alert.get("video_path", ""))
                    if is_processed_flag:
                        if not hasattr(top, "stream_cap"):
                            top.stream_cap = cv2.VideoCapture(alert["video_path"])
                        play_loop_stream()
                        return

                    if not top.processed_frames:
                        top.play_video = False
                        b_play_vid.configure(text="▶ Play Video (Smooth)")
                        analyze_video(None, True)
                        return
                        
                    play_loop()
                        
                b_exp_vid.configure(command=export_vid)
                b_exp_vid.pack(side="left", padx=5)
                b_play_vid.configure(command=toggle_video)
                b_play_vid.pack(side="left", padx=5)
                
            def on_close():
                top.play_video = False
                if hasattr(top, "cap"): top.cap.release()
                if hasattr(top, "stream_cap"): top.stream_cap.release()
                top.destroy()
                
            top.protocol("WM_DELETE_WINDOW", on_close)
            
        except Exception as e:
            print(f"Error opening view: {e}")

    def on_mode_change(self, val):
        self.is_playing_smooth = False
        self.current_image_path = None
        self.current_video_path = None
        if val == "Image":
            self.btn_load.configure(text="📸 Load Image", state="normal")
        elif val == "Video":
            self.btn_load.configure(text="🎬 Load Video", state="normal")
        else:
            self.btn_load.configure(text="🎥 Connect Cam", state="normal")
        self.draw_radar()

    def load_media(self):
        self.is_playing_smooth = False
        val = self.source_mode.get()
        if val == "Image":
            p = fd.askopenfilename(filetypes=[("Image", "*.jpg *.jpeg *.png")])
            if p:
                self.current_image_path = p
                self.display_image(p)
                self.btn_scan.configure(state="normal")
        elif val == "Video":
            p = fd.askopenfilename(filetypes=[("Video", "*.mp4 *.avi *.mov")])
            if p:
                self.current_video_path = p
                self.btn_scan.configure(state="normal")
                cap = cv2.VideoCapture(p)
                ret, frame = cap.read()
                if ret:
                    self.display_image(None, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                cap.release()
        else:
            try:
                idx = int(self.camera_index.get())
            except:
                idx = 0
            self.current_video_path = idx
            self.btn_scan.configure(state="normal")
            cap = cv2.VideoCapture(idx)
            ret, frame = cap.read()
            if ret:
                self.display_image(None, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            cap.release()

    def log(self, text):
        def _append():
            self.log_box.insert("end", text + "\n")
            self.log_box.see("end")
        self.after(0, _append)

    def load_model_thread(self):
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        try:
            device = "cuda:0" if torch.cuda.is_available() else "mps" if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() else "cpu"
            
            gpu_name = "CPU Detected"
            if "cuda" in device:
                gpu_name = "NVIDIA GPU Detected"
            elif "mps" in device:
                gpu_name = "Apple GPU Detected"
            elif hasattr(torch.version, 'hip') and torch.version.hip is not None:
                gpu_name = "AMD GPU Detected"
                
            self.log(f"Loading Model on: {device} ({gpu_name})")
            
            try:
                self.detector = pipeline(model="google/owlv2-base-patch16", task="zero-shot-object-detection", device=device, use_safetensors=True, local_files_only=True)
                self.log("Model Ready (Loaded from Cache).")
            except Exception as cache_e:
                self.log("=========================================")
                self.log("⚠️ INTERNET REQUIRED FOR FIRST RUN ⚠️")
                self.log("Model not found in offline cache.")
                self.log("Attempting to download AI model (1+ GB)...")
                self.log("👉 CHECK YOUR TERMINAL FOR THE PROGRESS BAR 👈")
                self.log("This will take a few minutes depending on connection.")
                self.log("After downloading, it will be saved forever offline!")
                self.log("=========================================")
                self.after(0, lambda: self.progress_bar.pack(pady=(0, 5)))
                self.after(0, lambda: self.progress_bar.set(0))
                self.after(0, lambda: self.eta_label.pack(pady=(0, 10)))
                self.after(0, lambda: self.eta_label.configure(text="Downloading AI... See Terminal for %"))
                
                # Make the progress bar indeterminate to show it's doing something
                self.after(0, lambda: self.progress_bar.configure(mode="indeterminate"))
                self.after(0, lambda: self.progress_bar.start())
                
                try:
                    self.detector = pipeline(model="google/owlv2-base-patch16", task="zero-shot-object-detection", device=device, use_safetensors=True, local_files_only=False)
                    self.log("✅ Model downloaded and ready!")
                except Exception as down_e:
                    err_str = str(down_e).lower()
                    if "max tries" in err_str or "max retries" in err_str or "connection" in err_str or "resolution" in err_str:
                        self.log("CRITICAL ERROR: No Internet Connection!")
                        self.log("The AI model is not in your cache yet.")
                        self.log("You MUST connect to internet ONE TIME to download it.")
                        self.log("After that, you can run offline forever.")
                    else:
                        raise down_e
                finally:
                    self.after(0, lambda: self.progress_bar.stop())
                    self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                    self.after(0, lambda: self.progress_bar.pack_forget())
                    self.after(0, lambda: self.eta_label.pack_forget())
                    
            self.after(0, lambda: self.btn_load.configure(state="normal"))
            if self.source_mode.get() != "Image": self.after(0, lambda: self.on_mode_change(self.source_mode.get()))
        except Exception as e:
            self.log(f"Model Error: {e}")

    def display_image(self, p, img_obj=None):
        if not img_obj: img_obj = Image.open(p).convert("RGB")
        img_obj.thumbnail((700, 420))
        ctk_img = ctk.CTkImage(img_obj, size=(img_obj.width, img_obj.height))
        self.image_label.configure(image=ctk_img)
        self.image_label.image_ref = ctk_img

    def start_scan(self):
        if not self.detector: return
        self.is_playing_smooth = False
        self.alert_played = False
        self.reset_status()
        self.btn_scan.configure(state="disabled")
        
        if self.source_mode.get() == "Image" and self.current_image_path:
            threading.Thread(target=self._process_scan_image, daemon=True).start()
        elif self.current_video_path is not None:
            self.is_processing_video = True
            threading.Thread(target=self._process_scan_video, daemon=True).start()

    def apply_detection_logic(self, imgV, results, threshold):
        draw = ImageDraw.Draw(imgV)
        threats_found = 0
        img_area = imgV.width * imgV.height
        best_detections = []
        
        for r in results:
            if r['score'] < threshold: continue
            tb = r['box']
            w = tb['xmax'] - tb['xmin']
            h = tb['ymax'] - tb['ymin']
            if w * h > img_area * 0.04: continue
            if w > imgV.width * 0.2 or h > imgV.height * 0.2: continue
            
            matched = False
            for ex in best_detections:
                eb = ex['box']
                if abs(tb['xmin'] - eb['xmin']) < 50 and abs(tb['ymin'] - eb['ymin']) < 50:
                    matched = True
                    if r['score'] > ex['score']:
                        ex['score'], ex['label'] = r['score'], r['label']
                    break
            if not matched: best_detections.append(r)

        alert_to_trigger = None
        for r in best_detections:
            if r['label'] in self.threat_labels:
                threats_found += 1
                b = r['box']
                draw.rectangle([b['xmin'], b['ymin'], b['xmax'], b['ymax']], outline="red", width=4)
                draw.text((b['xmin'], b['ymin']-15), f"{r['label']}: {r['score']:.2f}", fill="red")
                
                should_alert = True
                if getattr(self, "is_processing_video", False):
                    if getattr(self, "video_has_alerted", False):
                        should_alert = False
                    else:
                        self.video_has_alerted = True
                        
                if should_alert and not alert_to_trigger:
                    alert_to_trigger = (r['label'], r['score'])
                    
        if alert_to_trigger:
            label, conf = alert_to_trigger
            v_path = self.current_video_path if getattr(self, "is_processing_video", False) and isinstance(self.current_video_path, str) else None
            self.after(0, lambda label=label, conf=conf, im=imgV.copy(), vp=v_path: (self.animate_banner(label), self.add_alert(label, conf, im, vp)))
                
        return threats_found

    def _process_scan_image(self):
        try:
            imgV = Image.open(self.current_image_path).convert("RGB")
            results = self.detector(imgV, candidate_labels=self.all_labels, threshold=0.01)
            self.apply_detection_logic(imgV, results, self.slider.get()/100.0)
            self.last_scanned_image = imgV.copy()
            self.after(0, lambda: self.display_image(None, imgV))
        except Exception as e:
            self.log(str(e))
        finally:
            self.after(0, lambda: self.btn_scan.configure(state="normal"))
            self.after(0, lambda: self.btn_export.configure(state="normal"))

    def _process_scan_video(self):
        self.video_has_alerted = False
        try:
            cap = cv2.VideoCapture(self.current_video_path)
            self.processed_frames = []
            thresh = self.slider.get()/100.0
            
            is_file = isinstance(self.current_video_path, str)
            total_frames = 0
            start_time = time.time()
            if is_file:
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    self.after(0, lambda: self.progress_bar.pack(pady=(0, 5)))
                    self.after(0, lambda: self.eta_label.pack(pady=(0, 10)))
                    self.after(0, lambda: self.progress_bar.set(0))
                    self.after(0, lambda: self.eta_label.configure(text="ETA: Calculating..."))
            
            current = 0
            while self.is_processing_video and cap.isOpened():
                ret, frame = cap.read()
                if not ret: break
                current += 1
                
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                imgV = Image.fromarray(frame_rgb)
                results = self.detector(imgV, candidate_labels=self.all_labels, threshold=0.01)
                threat_count = self.apply_detection_logic(imgV, results, thresh)
                
                self.last_scanned_image = imgV.copy()
                if is_file:
                    self.processed_frames.append(self.last_scanned_image)
                    if current == 1 or threat_count > 0 or current % 3 == 0: self.after(0, lambda im=imgV.copy(): self.display_image(None, im))
                    
                    if total_frames > 0 and current % 5 == 0:
                        elapsed = time.time() - start_time
                        fps = current / elapsed if elapsed > 0 else 0
                        remaining_frames = total_frames - current
                        eta_seconds = int(remaining_frames / fps) if fps > 0 else 0
                        mins, secs = divmod(eta_seconds, 60)
                        eta_str = f"ETA: {mins:02d}:{secs:02d}"
                        self.after(0, lambda p=current/total_frames: self.progress_bar.set(p))
                        self.after(0, lambda e=eta_str: self.eta_label.configure(text=e))
                else:
                    self.after(0, lambda im=imgV.copy(): self.display_image(None, im))
                    
            cap.release()
            self.log("Video processing complete.")
            
            if is_file and hasattr(self, "processed_frames") and self.processed_frames:
                try:
                    self.log("Auto-saving processed video to project folder...")
                    w, h = self.processed_frames[0].width, self.processed_frames[0].height
                    w = w if w % 2 == 0 else w - 1
                    h = h if h % 2 == 0 else h - 1
                    
                    # Sanitize folder and file
                    cwd = os.getcwd() # Project folder
                    bname = os.path.basename(self.current_video_path)
                    name, _ = os.path.splitext(bname)
                    auto_path = os.path.join(cwd, f"{name}_auto_processed.mp4")
                    
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    out = cv2.VideoWriter(auto_path, fourcc, 30.0, (w, h))
                    for im in self.processed_frames:
                        frame_bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
                        frame_bgr = cv2.resize(frame_bgr, (w, h))
                        out.write(frame_bgr)
                    out.release()
                    self.log(f"Auto-saved to: {auto_path}")
                    
                    # Update alerts
                    updated = False
                    for a in self.alerts_list:
                        if a.get("video_path") == self.current_video_path:
                            a["video_path"] = auto_path
                            a["is_processed"] = True
                            updated = True
                    if updated:
                        self.save_alerts()
                        self.after(0, self.render_alerts)
                except Exception as e:
                    self.log(f"Auto-save failed: {e}")

            if is_file and total_frames > 0:
                self.after(0, lambda: self.progress_bar.set(1.0))
                self.after(0, lambda: self.eta_label.configure(text="ETA: 00:00"))
                self.after(2000, lambda: self.progress_bar.pack_forget())
                self.after(2000, lambda: self.eta_label.pack_forget())
            
            if is_file and hasattr(self, "processed_frames") and len(self.processed_frames) > 0:
                self.is_playing_smooth = True
                self.playback_idx = 0
                self.after(0, self.play_smooth_loop)
                
        except Exception as e:
            self.log(str(e))
        finally:
            self.is_processing_video = False
            self.after(0, lambda: self.btn_scan.configure(state="normal"))
            self.after(0, lambda: self.btn_export.configure(state="normal"))

    def play_smooth_loop(self):
        if not self.is_playing_smooth or not getattr(self, "processed_frames", None) or self.source_mode.get() != "Video":
            return
        
        frame = self.processed_frames[self.playback_idx]
        self.display_image(None, frame.copy())
        
        self.playback_idx += 1
        if self.playback_idx >= len(self.processed_frames):
            self.playback_idx = 0
            
        self.after(33, self.play_smooth_loop)

    def export_results(self):
        is_video = bool(getattr(self, "processed_frames", None))
        
        if is_video and self.source_mode.get() == "Video":
            fmt = "Video"
        else:
            fmt = "CSV"
            
        if fmt == "Video":
            if not getattr(self, "processed_frames", None):
                self.log("No video frames to export!")
                return
            path = fd.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
            if path:
                self.log("Exporting Video... Please wait.")
                def do_export(pth):
                    try:
                        frames = self.processed_frames
                        if not frames: return
                        w, h = frames[0].width, frames[0].height
                        w = w if w % 2 == 0 else w - 1
                        h = h if h % 2 == 0 else h - 1
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        out = cv2.VideoWriter(pth, fourcc, 30.0, (w, h))
                        for imgf in frames:
                            frame_bgr = cv2.cvtColor(np.array(imgf), cv2.COLOR_RGB2BGR)
                            frame_bgr = cv2.resize(frame_bgr, (w, h))
                            out.write(frame_bgr)
                        out.release()
                        self.log("Video export complete!")
                    except Exception as e:
                        self.log(f"Export Error: {str(e)}")
                threading.Thread(target=do_export, args=(path,), daemon=True).start()
            return
            
        if fmt == "CSV":
            path = fd.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
            if path:
                with open(path, "w") as f:
                    f.write("Date Time,Lat,Lon,Label,Confidence\n")
                    for a in self.alerts_list:
                        f.write(f"{a['dt']},{a['lat']},{a['lon']},{a['label']},{a['conf']}\n")
        else:
            path = fd.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if path:
                with open(path, "w") as f:
                     json.dump([{"dt":a['dt'], "lat":a['lat'], "lon":a['lon'], "label":a['label'], "conf":float(a['conf'])} for a in self.alerts_list], f, indent=4)
        self.log(f"Exported to {path}")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = ThreatDetectorApp()
    app.mainloop()