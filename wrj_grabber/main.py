import os
import sys
import time
import argparse
import subprocess
import adbutils
import yaml

# 修复导入路径
wrj_root = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for path in [wrj_root, project_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

from utils.logger import logger
from core.controller import WRJController

def start_multi_workers(mode, dept="wrj_general"):
    """自动检测所有设备并为每个设备启动一个 Grabber 进程"""
    adb = adbutils.adb
    devices = adb.device_list()
    
    if not devices:
        logger.error("No Android devices found via ADB. Please connect your phones.")
        return

    logger.info(f"Found {len(devices)} devices total.")
    
    processes = []
    for device in devices:
        serial = device.serial
        logger.info(f"Starting worker for WRJ Grabber device: {serial} (Dept: {dept})")
        
        # 启动子进程运行 main.py
        p = subprocess.Popen([
            sys.executable, "main.py", mode, "--serial", serial, "--dept", dept
        ], cwd=os.path.dirname(os.path.abspath(__file__)))
        processes.append(p)
        time.sleep(2)
    
    if not processes:
        logger.warning("No Grabber devices available.")
        return

    logger.info(f"Started {len(processes)} WRJ Grabber workers. Press Ctrl+C to stop all.")
    
    try:
        # 等待所有进程结束
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        logger.warning("Stopping all workers...")
        for p in processes:
            p.terminate()
        logger.info("All workers stopped.")

def main():
    parser = argparse.ArgumentParser(description="无人机执行端 (Grabber)")
    parser.add_argument("mode", nargs="?", default="like", choices=["like", "comment"], help="运行模式")
    parser.add_argument("--serial", help="设备序列号")
    parser.add_argument("--multi", action="store_true", help="自动为所有连接的设备启动 Worker")
    parser.add_argument("--dept", default="uav", help="所属部门")
    args = parser.parse_args()

    if args.multi:
        start_multi_workers(args.mode, args.dept)
        return

    try:
        logger.info(f"WRJ Grabber started in [{args.mode}] mode (Dept: {args.dept})" + (f" on device {args.serial}" if args.serial else ""))
        controller = WRJController(mode=args.mode, serial=args.serial, dept=args.dept)
        controller.start_task()
    except KeyboardInterrupt:
        logger.info("Task interrupted by user")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
    finally:
        logger.info("WRJ Grabber finished")

if __name__ == "__main__":
    main()
