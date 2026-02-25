#!/usr/bin/env python3
import os
import json
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog

APP_ID="opensensecam"
APP_DIR=f"/var/lib/{APP_ID}"
CONFIG_PATH = Path(f"/var/lib/{APP_ID}/config.json")

SERVICE_NAME = f"{APP_ID}.service"      # systemd unit name
WORKER_REL_PATH = Path(f"/usr/share/{APP_ID}/worker.py")       # script the service runs

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ModuleNotFoundError:
    PICAMERA_AVAILABLE = False

class ServiceController:
    """
    Helper for managing a systemd *system* service.

    Public methods:
      - ensure_installed()
      - start()
      - stop()
      - status()
    """

    def __init__(self, service_name: str, worker_rel_path: Path):
        from pathlib import Path
        import sys

        self.service_name = service_name

        # index.py is .../opensensecam/src, so app_root is one level up
        self._app_root = Path(__file__).resolve().parent.parent
        print(f"Setting service script to {worker_rel_path}")
        self._service_script = worker_rel_path

        # SYSTEM service location (requires root)
        self._unit_path = Path("/etc/systemd/system") / self.service_name
        self._python_exe = sys.executable

    # ---------- internal helpers ("private") ----------

    def _run_systemctl(self, *args):
        """
        Run `systemctl ...` and return (ok, output).

        NOTE: For system services, this usually needs to be run as root
        (e.g., script launched with sudo, or sudo/polkit setup).
        """
        import subprocess

        try:
            result = subprocess.run(
                ["systemctl", *args],
                text=True,
                capture_output=True
            )
            ok = (result.returncode == 0)
            output = (result.stdout.strip() or result.stderr.strip())
            return ok, output
        except FileNotFoundError:
            return False, "systemctl not found"
        except Exception as e:
            return False, str(e)

    def follow_logs_popen(self, lines=200):
        """
        Stream logs like: journalctl -u <service> -f
        Returns a subprocess.Popen object.
        """
        import subprocess
        
        cmd = [
            "journalctl",
            "-u", self.service_name,
            "-f",              # follow
            "-n", str(lines),  # show last N then follow
            "--no-pager",
            "-o", "short-iso", # nicer timestamps
        ]
        
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,         # line-buffered
        )

    # ---------- public API ----------

    def ensure_installed(self):
        """
        Ensure the service unit exists.
        Returns (ok: bool, message: str).

        NOTE: Writing /etc/systemd/system/* requires root.
        """
        if not self._service_script.exists():
            return False, f"Service script not found: {self._service_script}"
        else:
            # Already installed; ensure systemd knows about it
            # self._run_systemctl("daemon-reload")
            return True, f"Service already installed: {self._unit_path}"

    def start(self):
        """Install (if needed) and start the service."""
        ok, msg = self.ensure_installed()
        if not ok:
            return False, msg

        return self._run_systemctl("start", self.service_name)
        
    def restart(self):
        """Install (if needed) and start the service."""
        ok, msg = self.ensure_installed()
        if not ok:
            return False, msg
        
        return self._run_systemctl("restart", self.service_name)

    def stop(self):
        """Stop the service."""
        return self._run_systemctl("stop", self.service_name)

    def status(self):
        """
        Get status via `systemctl is-active`.
        Returns (ok: bool, message: str).
        """
        return self._run_systemctl("is-active", self.service_name)

from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass(frozen=True)
class CameraDevice:
    index: int
    display_name: str

@dataclass(frozen=True)
class CameraMode:
    size: Tuple[int, int]          # (width, height)
    fmt: str                       # libcamera format string (e.g., "SRGGB10", "RGB888", etc.)
    fps: Optional[float] = None    # may be absent depending on backend


class PiCamera2Catalog:
    """
    Enumerates cameras + sensor modes using Picamera2/libcamera.
    Keeps cameras closed except during brief queries.
    """

    def __init__(self):
        
        self._Picamera2 = Picamera2

        self.CAMERA_MODEL_ALIASES = {
            # Raspberry Pi official cameras
            "imx219": "Camera Module 2",
            "imx219_wide": "Camera Module 2 (Wide)",
        
            "imx708": "Camera Module 3",
            "imx708_wide": "Camera Module 3 Wide",
        
            "imx477": "HQ Camera",
        
            # USB / generic fallbacks
            "uvcvideo": "USB Camera",
        }

    def list_cameras(self):
        infos = self._Picamera2.global_camera_info()
        devices = []
        
        for i, info in enumerate(infos):
            model = (
                info.get("Model")
                or info.get("model")
                or info.get("Name")
                or "Camera"
            )
            location = info.get("Location") or info.get("location")
            pretty_model = self.CAMERA_MODEL_ALIASES.get(model, model)
            display = pretty_model
            if location:
                display += f" ({location})"
        
            devices.append(CameraDevice(
                index=i,
                display_name=display
            ))
        
        return devices
        

    def list_modes(self, camera_index: int) -> List[CameraMode]:
        cam = self._Picamera2(camera_index)
        try:
            # sensor_modes is a list of dicts with at least "size" and "format"
            raw_modes = getattr(cam, "sensor_modes", None) or []
            modes: List[CameraMode] = []

            for m in raw_modes:
                size = m.get("size")
                fmt = m.get("format")
                fps = m.get("fps", None)

                if not size or not fmt:
                    continue

                # size can be tuple-like; normalize
                w, h = int(size[0]), int(size[1])
                modes.append(CameraMode(size=(w, h), fmt=str(fmt), fps=float(fps) if fps is not None else None))

            # de-dupe (same size/format may appear)
            seen = set()
            uniq: List[CameraMode] = []
            for mode in modes:
                key = (mode.size, mode.fmt, mode.fps)
                if key not in seen:
                    seen.add(key)
                    uniq.append(mode)

            return uniq
        finally:
            # Important: release camera resources
            try:
                cam.close()
            except Exception:
                pass


class CameraSelectFrame(tk.LabelFrame):
    def __init__(self, master, catalog: PiCamera2Catalog, **kwargs):
        super().__init__(master, text="Camera", padx=10, pady=10, **kwargs)
        self.catalog = catalog

        self.camera_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="")

        self._index_to_camera_display = {}
        self._camera_display_to_index = {}
        self._mode_display_to_mode = {}

        tk.Label(self, text="Device:").grid(row=0, column=0, sticky="w")
        self.camera_combo = ttk.Combobox(self, textvariable=self.camera_var, state="readonly", width=48)
        self.camera_combo.grid(row=0, column=1, sticky="we", padx=(5, 0))

        tk.Label(self, text="Resolution:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.mode_combo = ttk.Combobox(self, textvariable=self.mode_var, state="readonly", width=48)
        self.mode_combo.grid(row=1, column=1, sticky="we", padx=(5, 0), pady=(8, 0))

        self.grid_columnconfigure(1, weight=1)

        self.camera_combo.bind("<<ComboboxSelected>>", self._on_camera_changed)

        self.refresh()

    def refresh(self):
        self._camera_display_to_index.clear()

        cams = self.catalog.list_cameras()
        if not cams:
            self.camera_combo["values"] = ["(no cameras detected)"]
            self.camera_var.set("(no cameras detected)")
            self.camera_combo.configure(state="disabled")

            self.mode_combo["values"] = []
            self.mode_var.set("")
            self.mode_combo.configure(state="disabled")
            return

        cam_values = []
        for cam in cams:
            cam_values.append(cam.display_name)
            self._camera_display_to_index[cam.display_name] = cam.index
            self._index_to_camera_display[cam.index] = cam.display_name

        self.camera_combo["values"] = cam_values
        self.camera_combo.configure(state="readonly")
        self.camera_var.set(cam_values[0])
        self._refresh_modes_for_selected_camera()

    def apply_config(self, cfg: dict):
        """
        cfg expects:
        camera_index: int
        camera_mode: {"width": int, "height": int, "format": str, "fps": float|None}
        """
        cam_index = cfg.get("camera_index", None)
        mode_cfg = cfg.get("camera_mode", None)
        
        # Ensure dropdowns are populated
        self.refresh()
        
        # Select camera by index (fallback to first)
        if cam_index in self._index_to_camera_display:
            self.camera_var.set(self._index_to_camera_display[cam_index])
        else:
            # fallback: keep whatever refresh() selected
            cam_index = self._camera_display_to_index.get(self.camera_var.get())
        
        # Refresh modes for that camera
        self._refresh_modes_for_selected_camera()
        
        # Select mode that matches config (fallback to first)
        if not mode_cfg:
            return
        
        target_w = mode_cfg.get("width")
        target_h = mode_cfg.get("height")
        target_fmt = mode_cfg.get("format")
        target_fps = mode_cfg.get("fps", None)
        
        best_label = None
        for label, m in self._mode_display_to_mode.items():
            if (m.size == (target_w, target_h)) and (m.fmt == target_fmt):
                # If fps is provided, prefer exact fps match
                if target_fps is None or m.fps is None or abs(m.fps - target_fps) < 1e-6:
                    best_label = label
                    break
                # Otherwise keep as candidate
                best_label = best_label or label
        
        if best_label:
            self.mode_var.set(best_label)

    def _on_camera_changed(self, event=None):
        self._refresh_modes_for_selected_camera()

    def _refresh_modes_for_selected_camera(self):
        self._mode_display_to_mode.clear()

        cam_index = self._camera_display_to_index.get(self.camera_var.get())
        if cam_index is None:
            self.mode_combo["values"] = []
            self.mode_var.set("")
            self.mode_combo.configure(state="disabled")
            return

        modes = self.catalog.list_modes(cam_index)
        if not modes:
            self.mode_combo["values"] = []
            self.mode_var.set("")
            self.mode_combo.configure(state="disabled")
            return

        labels = []
        for m in modes:
            w, h = m.size
            label = f"{w}x{h} ({m.fmt})" + (f" @ {m.fps:g}fps" if m.fps else "")
            labels.append(label)
            self._mode_display_to_mode[label] = m

        self.mode_combo["values"] = labels
        self.mode_combo.configure(state="readonly")
        self.mode_var.set(labels[0])

    def get_selection(self):
        """
        Returns (camera_index, CameraMode) or (None, None) if not available.
        """
        cam_index = self._camera_display_to_index.get(self.camera_var.get())
        mode = self._mode_display_to_mode.get(self.mode_var.get())
        return cam_index, mode

DEFAULT_CONFIG = {
    "folder": f"{APP_DIR}",
    "camera_index": 0,
    "interval": 10,
    "camera_mode": None, 
}

def load_config() -> dict:
    try:
        if not CONFIG_PATH.exists():
            return DEFAULT_CONFIG.copy()
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(data: dict) -> tuple[bool, str]:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True, "Saved"
    except Exception as e:
        return False, str(e)

# ---------- Tkinter GUI ----------

def main():
    controller = ServiceController(SERVICE_NAME, WORKER_REL_PATH)

    root = tk.Tk()
    root.title(f"{APP_ID} App")
    root.geometry("640x480")

    frame = tk.Frame(root, padx=10, pady=10)
    frame.pack(expand=True, fill="both")

    tk.Label(
        frame,
        text=f"{APP_ID}",
        font=("Arial", 14)
    ).pack(pady=(0, 10))
    
    cfg = load_config()
    
    folder_var = tk.StringVar(value=cfg.get("folder", f"{APP_DIR}"))
    mode_var = tk.StringVar(value=cfg.get("mode", "mode_a"))  # radio choice
    note_var = tk.StringVar(value=cfg.get("note", ""))        # text field
    interval_var = tk.IntVar(value=cfg.get("interval", 10))
    status_var = tk.StringVar(value="Status: (checking...)")

    def start_service():
        ok, msg = controller.start()
        if not ok:
            messagebox.showerror("Start failed", msg)
        else:
            if "Installed system service" in msg:
                messagebox.showinfo("Service Installed", msg)
        update_status()
        
    def restart_service():
        ok, msg = controller.restart()
        if not ok:
            messagebox.showerror("Restart failed", msg)
        else:
            if "Installed system service" in msg:
                messagebox.showinfo("Service Installed", msg)
        update_status()

    def stop_service():
        ok, msg = controller.stop()
        if not ok:
            messagebox.showerror("Stop failed", msg)
        update_status()

    def update_status():
        ok, msg = controller.status()
        if ok:
            status_var.set(f"Status: {msg}")
        else:
            status_var.set(f"Status: unknown ({msg})")

    # ---------- Config UI ----------
    cfg_frame = tk.LabelFrame(frame, text="Configuration", padx=10, pady=10)
    cfg_frame.pack(fill="x", pady=(10, 0))
    
    if PICAMERA_AVAILABLE:
        catalog = PiCamera2Catalog()
        cam_frame = CameraSelectFrame(cfg_frame, catalog)
        cam_frame.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 10))
        cam_frame.apply_config(cfg)
    
    # Choose the interval at which to take photos
    tk.Label(cfg_frame, text="Photo Interval (seconds):").grid(row=1, column=0, sticky="w")
    interval_entry = tk.Spinbox(cfg_frame, from_=1, to=99999, textvariable=interval_var, increment=1)
    interval_entry.grid(row=1, column=1, sticky="we", padx=(5, 5))
    
    # Folder picker row
    tk.Label(cfg_frame, text="Save Photos to:").grid(row=2, column=0, sticky="w")
    folder_entry = tk.Entry(cfg_frame, textvariable=folder_var, width=30, state="readonly")
    folder_entry.grid(row=2, column=1, sticky="we", padx=(5, 5))
    
    def browse_folder():
        initial = folder_var.get() or str(Path.home())
        selected = filedialog.askdirectory(initialdir=initial)
        if selected:
            folder_var.set(selected)
    
    # tk.Button(cfg_frame, text="Browse…", command=browse_folder).grid(row=1, column=2, sticky="e")
    
    # # Radio buttons row
    # tk.Label(cfg_frame, text="Mode:").grid(row=1, column=0, sticky="w", pady=(8, 0))
    # radio_row = tk.Frame(cfg_frame)
    # radio_row.grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 0))
    
    # tk.Radiobutton(radio_row, text="Mode A", variable=mode_var, value="mode_a").pack(side="left", padx=(0, 10))
    # tk.Radiobutton(radio_row, text="Mode B", variable=mode_var, value="mode_b").pack(side="left")
    
    # # Text field row
    # tk.Label(cfg_frame, text="Note:").grid(row=2, column=0, sticky="w", pady=(8, 0))
    # tk.Entry(cfg_frame, textvariable=note_var, width=30).grid(row=2, column=1, columnspan=2, sticky="we", pady=(8, 0))
    # 
    cfg_frame.grid_columnconfigure(1, weight=1)
    
    def on_save_config():
        
        camera_mode_cfg = None
        
        if PICAMERA_AVAILABLE:
            cam_index, cam_mode = cam_frame.get_selection()
            if cam_mode is not None:
                w, h = cam_mode.size
                camera_mode_cfg = {
                    "width": w,
                    "height": h,
                    "format": cam_mode.fmt,
                    "fps": cam_mode.fps,
                }
        
        data = {
            "folder": folder_var.get().strip(),
            "interval": int(interval_entry.get()),
            "camera_index": cam_index,
            "camera_mode": camera_mode_cfg,
        }

        ok, msg = save_config(data)
        if ok:
            pass
            # messagebox.showinfo("Config Saved", msg)
        else:
            messagebox.showerror("Config Save Failed", msg)
    
    # tk.Button(cfg_frame, text="Save Config", command=on_save_config).grid(row=3, column=0, columnspan=3, pady=(10, 0), sticky="w")
    
    def save_config_restart_service():
        on_save_config()
        restart_service()
        
    tk.Button(cfg_frame, text="Update & Restart Camera", command=save_config_restart_service).grid(row=4, column=0, columnspan=3, pady=(10, 0), sticky="e")
    
    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=5)
    
    tk.Button(
        btn_frame, text="Start Camera",
        width=14, command=start_service
    ).pack(side="left", padx=5)

    tk.Button(
        btn_frame, text="Stop Camera",
        width=14, command=stop_service
    ).pack(side="left", padx=5)

    status_label = tk.Label(frame, textvariable=status_var)
    status_label.pack(pady=(10, 0))
    
    log_q = queue.Queue()
    log_proc = None
    stop_log_event = threading.Event()
    
    log_frame = tk.LabelFrame(frame, text="Logs", padx=10, pady=10)
    log_frame.pack(fill="both", expand=True, pady=(10, 0))
    
    log_text = tk.Text(log_frame, height=12, wrap="none")
    log_text.pack(side="left", fill="both", expand=True)
    
    scroll_y = tk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
    scroll_y.pack(side="right", fill="y")
    log_text.configure(yscrollcommand=scroll_y.set)
    
    def _log_reader_thread():
        nonlocal log_proc
        try:
            log_proc = controller.follow_logs_popen(lines=200)
        except Exception as e:
            log_q.put(f"[log] failed to start journalctl: {e}\n")
            return
    
        for line in log_proc.stdout:
            if stop_log_event.is_set():
                break
            log_q.put(line)
    
    def start_log_stream():
        stop_log_event.clear()
        t = threading.Thread(target=_log_reader_thread, daemon=True)
        t.start()
    
    def stop_log_stream():
        stop_log_event.set()
        nonlocal log_proc
        if log_proc and log_proc.poll() is None:
            try:
                log_proc.terminate()
            except Exception:
                pass
        log_proc = None
        
    def pump_logs():
        appended = False
        while True:
            try:
                line = log_q.get_nowait()
            except queue.Empty:
                break
            log_text.insert("end", line)
            appended = True
        
        if appended:
            log_text.see("end")  # autoscroll
        
        root.after(100, pump_logs)  # ~10fps UI updates
    
    start_log_stream()
    pump_logs()

    def periodic_status():
        update_status()
        root.after(3000, periodic_status)

    periodic_status()
    
    def on_close():
        stop_log_stream()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_close)
    
    root.mainloop()


if __name__ == "__main__":
    main()