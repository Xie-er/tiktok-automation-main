import adbutils
import subprocess

print("--- Checking via adbutils ---")
try:
    devices = adbutils.adb.device_list()
    print(f"adbutils found {len(devices)} devices")
    for d in devices:
        print(f"Device: {d.serial} - {d.info}")
except Exception as e:
    print(f"adbutils error: {e}")

print("\n--- Checking for ADB in common paths ---")
common_paths = [
    r"C:\platform-tools\adb.exe",
    r"D:\platform-tools\adb.exe",
    r"E:\platform-tools\adb.exe",
    r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
]

for path in common_paths:
    expanded_path = subprocess.run(f"echo {path}", shell=True, capture_output=True, text=True).stdout.strip()
    print(f"Checking {expanded_path}...")
    if subprocess.run(f"test -f {expanded_path}", shell=True).returncode == 0:
        print(f"Found ADB at {expanded_path}")
        res = subprocess.run(f"{expanded_path} devices", shell=True, capture_output=True, text=True)
        print(res.stdout)
