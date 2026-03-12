import sys
import os
import argparse
from loguru import logger

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scout_controller import ScoutController

def main():
    parser = argparse.ArgumentParser(description="Tiktok Scout Robot")
    parser.add_argument("--serial", help="设备序列号 (adb devices 查看)")
    parser.add_argument("--dept", default="general", help="所属部门")
    args = parser.parse_args()

    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "scout.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logger.add(log_path, rotation="10 MB")
    logger.info(f"Starting Scout Robot for dept: {args.dept}...")
    
    try:
        # 如果命令行提供了 serial，则覆盖配置中的 serial
        scout = ScoutController(dept=args.dept)
        if args.serial:
            scout.device_mgr.serial = args.serial
            
        scout.start()
    except KeyboardInterrupt:
        logger.info("Scout stopped by user")
    except Exception as e:
        logger.exception(f"Fatal error in Scout: {e}")

if __name__ == "__main__":
    main()
