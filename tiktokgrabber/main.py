from core.controller import Controller
from utils.logger import logger
import sys

import argparse

import subprocess
import adbutils
import time
from utils.logger import logger

import yaml
import os

def start_multi_workers(mode, dept="general"):
    """自动检测所有设备并为每个设备启动一个 Grabber 进程，排除 Scout 设备"""
    adb = adbutils.adb
    devices = adb.device_list()
    
    if not devices:
        logger.error("No Android devices found via ADB. Please connect your phones.")
        return

    # 尝试获取 Scout 的序列号以进行排除
    scout_serial = None
    scout_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tiktok_scout", "config", "scout_settings.yaml")
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
            
        logger.info(f"Starting worker for Grabber device: {serial} (Dept: {dept})")
        
        # 启动子进程运行 main.py
        p = subprocess.Popen([
            sys.executable, "main.py", mode, "--serial", serial, "--dept", dept
        ])
        processes.append(p)
        time.sleep(2)
    
    if not processes:
        logger.warning("No Grabber devices available (after excluding Scout).")
        return

    logger.success(f"Started {len(processes)} Grabber workers. Press Ctrl+C to stop all.")
    
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
    parser = argparse.ArgumentParser(description="DouyinLeadMiner Worker")
    parser.add_argument("mode", nargs="?", default="like", choices=["like", "dm", "reply", "comment"], help="运行模式")
    parser.add_argument("--serial", help="设备序列号 (adb devices 查看)")
    parser.add_argument("--multi", action="store_true", help="自动为所有连接的设备启动 Worker")
    parser.add_argument("--dept", default="general", help="所属部门")
    args = parser.parse_args()
    
    if args.multi:
        start_multi_workers(args.mode, args.dept)
        return

    mode = args.mode
    serial = args.serial
    dept = args.dept
    
    try:
        logger.info(f"DouyinLeadMiner started in [{mode}] mode (Dept: {dept})" + (f" on device {serial}" if serial else ""))
        controller = Controller(mode=mode, serial=serial, dept=dept)
        controller.start_task()
    except KeyboardInterrupt:
        logger.info("Task interrupted by user")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
    finally:
        logger.info("DouyinLeadMiner finished")

if __name__ == "__main__":
    main()
