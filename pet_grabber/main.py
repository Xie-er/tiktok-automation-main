from core.controller import PetController
from utils.logger import logger
import sys
import argparse
import subprocess
import adbutils
import time
import yaml
import os

def start_multi_workers(mode, dept="pet"):
    """自动检测所有设备并为每个设备启动一个 Pet Grabber 进程"""
    adb = adbutils.adb
    devices = adb.device_list()
    
    if not devices:
        logger.error("No Android devices found via ADB. Please connect your phones.")
        return

    # 排除 Scout 设备
    scout_serial = None
    scout_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiktok_scout", "config", "scout_settings.yaml")
    if os.path.exists(scout_config_path):
        try:
            with open(scout_config_path, "r", encoding="utf-8") as f:
                scout_config = yaml.safe_load(f)
                scout_serial = scout_config.get("device", {}).get("serial")
        except Exception as e:
            logger.warning(f"Could not read Scout config: {e}")

    logger.info(f"Pet Grabber found {len(devices)} devices total.")
    
    processes = []
    for device in devices:
        serial = device.serial
        if serial == scout_serial:
            logger.info(f"Skipping Scout device: {serial}")
            continue
            
        logger.info(f"Starting worker for Pet Grabber device: {serial} (Dept: {dept})")
        p = subprocess.Popen([
            sys.executable, "main.py", mode, "--serial", serial, "--dept", dept
        ], cwd=os.path.dirname(os.path.abspath(__file__)))
        processes.append(p)
        time.sleep(2)
    
    try:
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        logger.warning("Stopping all Pet Grabber workers...")
        for p in processes:
            p.terminate()

def main():
    parser = argparse.ArgumentParser(description="Pet Department Grabber")
    # 兼容后端调用的 mode 参数，虽然宠物部门内部固定使用 translator
    parser.add_argument("mode", nargs="?", default="pet_translator", help="运行模式 (宠物部门固定为 translator)")
    parser.add_argument("--serial", help="设备序列号")
    parser.add_argument("--multi", action="store_true", help="自动启动多设备")
    parser.add_argument("--dept", default="pet", help="所属部门")
    args = parser.parse_args()
    
    # 宠物部门固定使用 translator 模式
    fixed_mode = "pet_translator"
    
    if args.multi:
        start_multi_workers(fixed_mode, args.dept)
        return

    try:
        # 添加详细启动日志
        logger.info("="*50)
        logger.info(f"Pet Grabber Starting Process...")
        logger.info(f"Args: serial={args.serial}, dept={args.dept}, mode={fixed_mode}")
        logger.info(f"Python Executable: {sys.executable}")
        logger.info(f"Current Working Directory: {os.getcwd()}")
        
        controller = PetController(serial=args.serial, dept=args.dept)
        logger.info("PetController initialized successfully")
        controller.start_task()
    except KeyboardInterrupt:
        logger.info("Pet Task interrupted by user")
    except Exception as e:
        logger.exception(f"Pet Unhandled exception in main: {e}")
    finally:
        logger.info("Pet Grabber process finished/exited")
        logger.info("="*50)

if __name__ == "__main__":
    main()
