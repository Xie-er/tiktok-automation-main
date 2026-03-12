import os
import sys
import time
import argparse
import subprocess
import adbutils
import yaml
from utils.logger import logger
from core.controller import XHSController

def start_multi_workers(mode, dept="xhs_general"):
    """自动检测所有设备并为每个设备启动一个 Grabber 进程，排除 Scout 设备"""
    adb = adbutils.adb
    devices = adb.device_list()
    
    if not devices:
        logger.error("No Android devices found via ADB. Please connect your phones.")
        return

    # 尝试获取 Scout 的序列号以进行排除
    scout_serial = None
    scout_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xhs_scout", "config", "settings.yaml")
    if os.path.exists(scout_config_path):
        try:
            with open(scout_config_path, "r", encoding="utf-8") as f:
                scout_config = yaml.safe_load(f)
                scout_serial = scout_config.get("device", {}).get("serial")
                if scout_serial:
                    logger.info(f"Identified Scout device serial: {scout_serial}. It will be excluded from Grabber tasks.")
        except Exception as e:
            logger.warning(f"Could not read Scout config to exclude serial: {e}")

    logger.info(f"Found {len(devices)} devices total.")
    
    processes = []
    for device in devices:
        serial = device.serial
        
        # 排除 Scout 设备
        if serial == scout_serial:
            logger.info(f"Skipping Scout device: {serial}")
            continue
            
        logger.info(f"Starting worker for XHS Grabber device: {serial} (Dept: {dept})")
        
        # 启动子进程运行 main.py
        p = subprocess.Popen([
            sys.executable, "main.py", mode, "--serial", serial, "--dept", dept
        ], cwd=os.path.dirname(os.path.abspath(__file__)))
        processes.append(p)
        time.sleep(2)
    
    if not processes:
        logger.warning("No Grabber devices available (after excluding Scout).")
        return

    logger.info(f"Started {len(processes)} XHS Grabber workers. Press Ctrl+C to stop all.")
    
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
    parser = argparse.ArgumentParser(description="小红书执行端 (Grabber)")
    parser.add_argument("mode", nargs="?", default="like", choices=["like", "comment"], help="运行模式")
    parser.add_argument("--serial", help="设备序列号")
    parser.add_argument("--multi", action="store_true", help="自动为所有连接的设备启动 Worker")
    parser.add_argument("--dept", default="xhs_general", help="所属部门")
    args = parser.parse_args()

    if args.multi:
        start_multi_workers(args.mode, args.dept)
        return

    try:
        logger.info(f"XHS Grabber started in [{args.mode}] mode (Dept: {args.dept})" + (f" on device {args.serial}" if args.serial else ""))
        controller = XHSController(mode=args.mode, serial=args.serial, dept=args.dept)
        controller.start_task()
    except KeyboardInterrupt:
        logger.info("Task interrupted by user")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
    finally:
        logger.info("XHS Grabber finished")

if __name__ == "__main__":
    main()
