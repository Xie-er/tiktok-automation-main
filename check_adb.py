import adbutils
import subprocess

try:
    path = adbutils.adb_path()
    print(f"ADB Path: {path}")
    res = subprocess.run([path, "version"], capture_output=True, text=True)
    print(f"ADB Version Output: {res.stdout}")
except Exception as e:
    print(f"Error: {e}")
