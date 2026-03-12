
import os
import sys
import yaml
import adbutils
from loguru import logger

# 添加路径以便导入项目模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.device_mgr import DeviceManager
from core.driver_wrapper import DriverWrapper
from utils.human_sim import random_delay

def run_step_one():
    """
    第一步：打开指定 Resource ID 的评论区
    ID: com.ss.android.ugc.aweme:id/en1
    """
    target_id = "com.ss.android.ugc.aweme:id/en1"
    
    logger.info(f"--- Step 1: Opening comment area (ID: {target_id}) ---")
    
    try:
        # 1. 连接设备
        device_mgr = DeviceManager() # 默认连接第一个设备
        if not device_mgr.connect():
            logger.error("Failed to connect to device.")
            return False
        
        serial = device_mgr.serial
        logger.info(f"Using device: {serial}")
        
        # 2. 初始化驱动
        driver = DriverWrapper(device_mgr)
        
        # 3. 确保屏幕开启
        driver.ensure_screen_on()
        
        # 4. 执行点击操作
        logger.info(f"Attempting to click comment button: {target_id}")
        if driver.safe_click(target_id):
            logger.success(f"Successfully clicked comment button {target_id}")
            random_delay(1, 2)
            return True
        else:
            logger.error(f"Could not find or click comment button {target_id}. Please ensure TikTok is on video page.")
            return False
            
    except Exception as e:
        logger.exception(f"An error occurred during Step 1: {e}")
        return False

if __name__ == "__main__":
    run_step_one()
