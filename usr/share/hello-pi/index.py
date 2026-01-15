#!/usr/bin/env python3
import os
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog

APP_ID="hello-pi"
APP_DIR=f"/var/lib/{APP_ID}"
CONFIG_PATH = Path(f"/var/lib/{APP_ID}/config.json")

SERVICE_NAME = f"{APP_ID}.service"      # systemd unit name
WORKER_REL_PATH = Path(f"/usr/share/{APP_ID}/worker.py")       # script the service runs


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

        # index.py is .../hello-pi/src, so app_root is one level up
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


DEFAULT_CONFIG = {"folder": "~/", "mode": "mode_a", "note": ""}

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
    root.title("Hello Pi App")
    root.geometry("640x480")

    frame = tk.Frame(root, padx=10, pady=10)
    frame.pack(expand=True, fill="both")

    tk.Label(
        frame,
        text="Hello Pi Background System Service",
        font=("Arial", 14)
    ).pack(pady=(0, 10))

    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=5)
    
    cfg = load_config()
    
    folder_var = tk.StringVar(value=cfg.get("folder", ""))
    mode_var = tk.StringVar(value=cfg.get("mode", "mode_a"))  # radio choice
    note_var = tk.StringVar(value=cfg.get("note", ""))        # text field

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
    cfg_frame = tk.LabelFrame(frame, text="Service Config", padx=10, pady=10)
    cfg_frame.pack(fill="x", pady=(10, 0))
    
    # Folder picker row
    tk.Label(cfg_frame, text="Folder:").grid(row=0, column=0, sticky="w")
    folder_entry = tk.Entry(cfg_frame, textvariable=folder_var, width=30)
    folder_entry.grid(row=0, column=1, sticky="we", padx=(5, 5))
    
    def browse_folder():
        initial = folder_var.get() or str(Path.home())
        selected = filedialog.askdirectory(initialdir=initial)
        if selected:
            folder_var.set(selected)
    
    tk.Button(cfg_frame, text="Browse…", command=browse_folder).grid(row=0, column=2, sticky="e")
    
    # Radio buttons row
    tk.Label(cfg_frame, text="Mode:").grid(row=1, column=0, sticky="w", pady=(8, 0))
    radio_row = tk.Frame(cfg_frame)
    radio_row.grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 0))
    
    tk.Radiobutton(radio_row, text="Mode A", variable=mode_var, value="mode_a").pack(side="left", padx=(0, 10))
    tk.Radiobutton(radio_row, text="Mode B", variable=mode_var, value="mode_b").pack(side="left")
    
    # Text field row
    tk.Label(cfg_frame, text="Note:").grid(row=2, column=0, sticky="w", pady=(8, 0))
    tk.Entry(cfg_frame, textvariable=note_var, width=30).grid(row=2, column=1, columnspan=2, sticky="we", pady=(8, 0))
    
    cfg_frame.grid_columnconfigure(1, weight=1)
    
    def on_save_config():
        data = {
            "folder": folder_var.get().strip(),
            "mode": mode_var.get().strip(),
            "note": note_var.get().strip(),
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
        
    tk.Button(cfg_frame, text="Update", command=save_config_restart_service).grid(row=3, column=0, columnspan=3, pady=(10, 0), sticky="w")

    # tk.Button(
    #     btn_frame, text="Start Service",
    #     width=14, command=start_service
    # ).pack(side="left", padx=5)
# 
    # tk.Button(
    #     btn_frame, text="Stop Service",
    #     width=14, command=stop_service
    # ).pack(side="left", padx=5)

    status_label = tk.Label(frame, textvariable=status_var)
    status_label.pack(pady=(10, 0))

    def periodic_status():
        update_status()
        root.after(3000, periodic_status)

    periodic_status()
    root.mainloop()


if __name__ == "__main__":
    main()