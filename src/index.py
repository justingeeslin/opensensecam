#!/usr/bin/env python3
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

SERVICE_NAME = "hello-pi.service"      # systemd unit name
WORKER_REL_PATH = Path("src/worker.py")       # script the service runs


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
        self._service_script = self._app_root / worker_rel_path

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

    def stop(self):
        """Stop the service."""
        return self._run_systemctl("stop", self.service_name)

    def status(self):
        """
        Get status via `systemctl is-active`.
        Returns (ok: bool, message: str).
        """
        return self._run_systemctl("is-active", self.service_name)


# ---------- Tkinter GUI ----------

def main():
    controller = ServiceController(SERVICE_NAME, WORKER_REL_PATH)

    root = tk.Tk()
    root.title("Hello Pi System Service Control")
    root.geometry("360x190")

    frame = tk.Frame(root, padx=10, pady=10)
    frame.pack(expand=True, fill="both")

    tk.Label(
        frame,
        text="Hello Pi Background System Service",
        font=("Arial", 14)
    ).pack(pady=(0, 10))

    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=5)

    status_var = tk.StringVar(value="Status: (checking...)")

    def start_service():
        ok, msg = controller.start()
        if not ok:
            messagebox.showerror("Start failed", msg)
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

    tk.Button(
        btn_frame, text="Start Service",
        width=14, command=start_service
    ).pack(side="left", padx=5)

    tk.Button(
        btn_frame, text="Stop Service",
        width=14, command=stop_service
    ).pack(side="left", padx=5)

    status_label = tk.Label(frame, textvariable=status_var)
    status_label.pack(pady=(10, 0))

    def periodic_status():
        update_status()
        root.after(3000, periodic_status)

    periodic_status()
    root.mainloop()


if __name__ == "__main__":
    main()