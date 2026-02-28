# threads_gps_cam.py
import os, io, time, json, threading
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

GPS_AVAILABLE = False
adafruit_gps = None

try:
	import adafruit_gps  # type: ignore
	import board
	import busio
	GPS_AVAILABLE = True
except ModuleNotFoundError:
	GPS_AVAILABLE = False

APP_ID="opensensecam"
APP_DIR=f"/var/lib/{APP_ID}"
CONFIG_PATH = Path(f"/var/lib/{APP_ID}/config.json")

DEFAULT_CONFIG =  {
	"folder": f"{APP_DIR}",
	"camera_index": 0,
	"interval": 10,
	"camera_mode": None, 
}

def load_config() -> dict:
	try:
		with CONFIG_PATH.open("r", encoding="utf-8") as f:
			return json.load(f)
	except FileNotFoundError:
		return DEFAULT_CONFIG.copy()
	except Exception:
		return DEFAULT_CONFIG.copy()

if GPS_AVAILABLE:
	# Create a serial connection for the GPS connection using default speed and
	# a slightly higher timeout (GPS modules typically update once a second).
	# These are the defaults you should use for the GPS FeatherWing.
	# For other boards set RX = GPS module TX, and TX = GPS module RX pins.
	rx = board.RX  # Change to board.GP4 for Raspberry Pi Pico boards
	tx = board.TX  # Change to board.GP5 for Raspberry Pi Pico boards
	# uart = busio.UART(rx, tx, baudrate=9600, timeout=10)
	
	# for a computer, use the pyserial library for uart access
	# import serial
	# uart = serial.Serial("/dev/ttyUSB0", baudrate=9600, timeout=10)
	
	# If using I2C, we'll create an I2C interface to talk to using default pins
	i2c = board.I2C()  #uses board.SCL and board.SDA
	# i2c = board.STEMMA_I2C()  For using the built-in STEMMA QT connector on a microcontroller
	
	# Create a GPS module instance.
	# gps = adafruit_gps.GPS(uart, debug=False)  # Use UART/pyserial
	gps = adafruit_gps.GPS_GtopI2C(i2c, debug=False)  # Use I2C interface

try:
	from picamera2 import Picamera2
	from PIL import Image
	PICAMERA2 = True
except Exception:
	PICAMERA2 = False

try:
	import piexif
	EXIF_OK = True
except Exception:
	EXIF_OK = False

cfg = load_config()
folder = cfg.get("folder", APP_DIR)
mode = cfg.get("mode", "mode_a")
note = cfg.get("note", "")
interval = cfg.get("interval", "10")
camera_mode = cfg.get("camera_mode")
	
IMAGE_DIR = os.path.expanduser(folder)
os.makedirs(IMAGE_DIR, exist_ok=True)

# ---------- helpers ----------
def _rat(x, max_den=1_000_000):
	f = Fraction(x).limit_denominator(max_den)
	return (f.numerator, f.denominator)

def _deg_to_dms(dd):
	dd = abs(dd)
	d = int(dd)
	m_float = (dd - d) * 60
	m = int(m_float)
	s = (m_float - m) * 60
	return (_rat(d), _rat(m), _rat(s))

def _combine_date_time(date_str, time_str):
	"""
	Your parser returns date like 'YYYY-MM-DD' (RMC) and time like 'HH:MM:SS' (GGA/RMC).
	Return a timezone-aware UTC datetime. If date is missing, use today (UTC).
	"""
	if time_str is None and date_str is None:
		return datetime.now(timezone.utc)
	if date_str:
		y, m, d = map(int, date_str.split("-"))
	else:
		now = datetime.now(timezone.utc)
		y, m, d = now.year, now.month, now.day
	hh, mm, ss = (0, 0, 0) if not time_str else map(int, time_str.split(":"))
	return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)

def make_exif(now_local_dt, fix):
	# if not EXIF_OK:
	#     return None
	exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "Interop": {}}
	dt_str = now_local_dt.strftime('%Y:%m:%d %H:%M:%S')
	
	# Core datetime tags
	exif["0th"][piexif.ImageIFD.DateTime] = dt_str
	exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_str
	exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str
	
	# Camera/software info (optional but nice to have)
	exif["0th"][piexif.ImageIFD.Make] = "Raspberry Pi"
	exif["0th"][piexif.ImageIFD.Model] = "Camera Module 3"
	exif["0th"][piexif.ImageIFD.Software] = "OpenSenseCam Script"
	exif["0th"][piexif.ImageIFD.DateTime] = dt_str

	# Optional custom tags
	exif["Exif"][piexif.ExifIFD.UserComment] = b"ASCII\0\0\0" + json.dumps(
		{"project": "OpenSenseCam"}, separators=(",", ":")
	).encode("ascii", "ignore")

	if GPS_AVAILABLE:
		lat = gps.latitude
		lon = gps.longitude
		alt = gps.altitude_m
		
		if (lat is None):
			print("No GPS in EXIF..")
			return exif
		
		exif["GPS"][piexif.GPSIFD.GPSLatitudeRef]  = "N" if lat >= 0 else "S"
		exif["GPS"][piexif.GPSIFD.GPSLatitude]     = _deg_to_dms(lat)
		exif["GPS"][piexif.GPSIFD.GPSLongitudeRef] = "E" if lon >= 0 else "W"
		exif["GPS"][piexif.GPSIFD.GPSLongitude]    = _deg_to_dms(lon)
		if alt is not None:
			exif["GPS"][piexif.GPSIFD.GPSAltitudeRef] = 0 if alt >= 0 else 1
			exif["GPS"][piexif.GPSIFD.GPSAltitude] = _rat(abs(alt), 1000)
	
	
		ts_utc = datetime.now(timezone.utc)
		exif["GPS"][piexif.GPSIFD.GPSDateStamp] = ts_utc.strftime('%Y:%m:%d')
		exif["GPS"][piexif.GPSIFD.GPSTimeStamp] = (_rat(gps.timestamp_utc.tm_hour), _rat(gps.timestamp_utc.tm_min), _rat(gps.timestamp_utc.tm_sec))
			
	return exif

# ---------- shared state ----------
class SharedState:
	def __init__(self):
		self._lock = threading.Lock()
		self._latest_fix = None  # dict from your parse_sentence + computed _ts_utc_dt

	def set_fix(self, fix_dict):
		with self._lock:
			if self._latest_fix.fix_quality <= fix_dict.fix_quality:
				print(f"This latest GPS fix ({fix_dict.fix_quality}) is not better than the current ({self._latest_fix.fix_quality}). Skipping.. ")
				
			else:
				
				self._latest_fix = dict(fix_dict)

	def get_fix(self):
		with self._lock:
			return dict(self._latest_fix) if self._latest_fix else None

# ---------- threads ----------
class GPSPoller(threading.Thread):
	"""
	Uses your GPSModule.read_sentence() and parse_sentence().
	Keeps the latest merged fix (RMC typically has date/speed/course; GGA has altitude/fix_quality).
	"""
	def __init__(self, state: SharedState, interface="I2C", interval=0.25):
		super().__init__(daemon=True)
		self.state = state
		self.interface = interface
		self.interval = interval
		self._stop_event = threading.Event()

	def stop(self):
		print("Stopping GPS thread..")
		self._stop_event.set()

	def run(self):
		global gps
		while not self._stop_event.is_set():
			# Make sure to call gps.update() every loop iteration and at least twice
			# as fast as data comes from the GPS unit (usually every second).
			# This returns a bool that's true if it parsed new data (you can ignore it
			# though if you don't care and instead look at the has_fix property).
			gps.update()
			print(f"Getting a new GPS fix... {gps.latitude}")
			if gps.has_fix:
				# We have a fix! (gps.has_fix is true)
				# Print out details about the fix like location, date, etc.
				print("=" * 40)  # Print a separator line.
				print(
					"Fix timestamp: {}/{}/{} {:02}:{:02}:{:02}".format(  # noqa: UP032
						gps.timestamp_utc.tm_mon,  # Grab parts of the time from the
						gps.timestamp_utc.tm_mday,  # struct_time object that holds
						gps.timestamp_utc.tm_year,  # the fix time.  Note you might
						gps.timestamp_utc.tm_hour,  # not get all data like year, day,
						gps.timestamp_utc.tm_min,  # month!
						gps.timestamp_utc.tm_sec,
					)
				)
				print(f"Latitude: {gps.latitude:.6f} degrees")
				print(f"Longitude: {gps.longitude:.6f} degrees")
				print(f"Precise Latitude: {gps.latitude_degrees} degs, {gps.latitude_minutes:2.4f} mins")
				print(f"Precise Longitude: {gps.longitude_degrees} degs, {gps.longitude_minutes:2.4f} mins")
				print(f"Fix quality: {gps.fix_quality}")
				# Some attributes beyond latitude, longitude and timestamp are optional
				# and might not be present.  Check if they're None before trying to use!
				if gps.satellites is not None:
					print(f"# satellites: {gps.satellites}")
				if gps.altitude_m is not None:
					print(f"Altitude: {gps.altitude_m} meters")
				if gps.speed_knots is not None:
					print(f"Speed: {gps.speed_knots} knots")
				if gps.speed_kmh is not None:
					print(f"Speed: {gps.speed_kmh} km/h")
				if gps.track_angle_deg is not None:
					print(f"Track angle: {gps.track_angle_deg} degrees")
				if gps.horizontal_dilution is not None:
					print(f"Horizontal dilution: {gps.horizontal_dilution}")
				if gps.height_geoid is not None:
					print(f"Height geoid: {gps.height_geoid} meters")
			else:
				print("[GPS] Waiting for fix...")
			
			# Sleep until next poll
			time.sleep(self.interval)


class CameraPoller(threading.Thread):
	"""
	Captures JPEGs on its own cadence.
	If Picamera2 is present, embeds EXIF using the latest GPS fix from SharedState.
	"""
	def __init__(self, state: SharedState, interval=10.0, resolution=(2304, 1296), jpeg_quality=90):
		super().__init__(daemon=True)
		self.state = state
		self.interval = interval
		print(f"Polling the camera at {self.interval} seconds")
		self.resolution = resolution
		print(f"Photo resolution: {self.resolution}")
		self.jpeg_quality = jpeg_quality
		self._stop = threading.Event()
		self._pc2 = None

		if PICAMERA2:
			try:
				self._pc2 = Picamera2()
				cfg = self._pc2.create_still_configuration(main={"size": self.resolution})
				self._pc2.configure(cfg)
				self._pc2.start()
			except Exception:
				self._pc2 = None  # fallback to libcamera-still

	def stop(self):
		self._stop.set()

	def _capture_picamera2(self):
		buf = io.BytesIO()
		self._pc2.capture_file(buf, format="jpeg")
		buf.seek(0)
		return buf


	def run(self):
		try:
			while not self._stop.is_set():
				now_local = datetime.now()  # for general EXIF DateTime
				fname = now_local.strftime("photo_%Y%m%d_%H%M%S.jpg")
				out_path = os.path.join(IMAGE_DIR, fname)
				fix = self.state.get_fix()

				if PICAMERA2 and self._pc2 is not None:
					print("Taking a photo..")
					img_bytes = self._capture_picamera2()
					exif_bytes = None
					exif_dict = None
 
					exif_dict = make_exif(now_local, fix)
					# print(f"Here's the exif dict {exif_dict}")
					if exif_dict:
						exif_bytes = piexif.dump(exif_dict)

					from PIL import Image  # import here in case PIL isn't installed
					with Image.open(img_bytes) as im:
						if exif_bytes:
							im.save(out_path, format="JPEG", exif=exif_bytes)
						else:
							im.save(out_path, format="JPEG")
						if GPS_AVAILABLE:
							print(f"[Camera] Saved {out_path} with EXIF data Fix: {exif_dict} GPS {gps}")
						else:
							print(f"[Camera] Saved {out_path} with EXIF data Fix: {exif_dict}")
				else:
					print("[Camera] No camera found..")

				
				self._stop.wait(self.interval)
		finally:
			if self._pc2 is not None:
				try:
					self._pc2.close()
				except Exception:
					pass

# ---------- main ----------
def main():
	
	if not PICAMERA2:
		print("Camera not found..")
		return 1
	
	state = SharedState()
	if GPS_AVAILABLE:
		gps_thread = GPSPoller(state, interface="I2C", interval=5.0)   # ~4 Hz read of sentences
	else:
		print("GPS unavailable.")
		
	cam_thread = CameraPoller(state, interval=interval, resolution=(camera_mode.get("width"), camera_mode.get("height")), jpeg_quality=90)

	if GPS_AVAILABLE:
		gps_thread.start()
		
	cam_thread.start()
	
	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		pass
	finally:
		if GPS_AVAILABLE:
			gps_thread.stop(); 
			gps_thread.join(timeout=2); 
			
		cam_thread.stop()
		cam_thread.join(timeout=2)

if __name__ == "__main__":
	main()