#!/usr/bin/env python3
import time
import json
from pathlib import Path

APP_ID="hello-pi"
CONFIG_PATH = Path(f"/var/lib/{APP_ID}/config.json")

def load_config() -> dict:
	try:
		with CONFIG_PATH.open("r", encoding="utf-8") as f:
			return json.load(f)
	except FileNotFoundError:
		return {}
	except Exception:
		return {}

def main():
	while True:
		cfg = load_config()
		folder = cfg.get("folder", "")
		mode = cfg.get("mode", "mode_a")
		note = cfg.get("note", "")

		print(f"Hello from worker service... folder={folder!r} mode={mode!r} note={note!r}")
		# Do real work here using cfg values...
		time.sleep(5)

if __name__ == "__main__":
	main()