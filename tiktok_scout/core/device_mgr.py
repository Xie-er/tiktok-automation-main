import adbutils
from loguru import logger
import uiautomator2 as u2
import time

class DeviceManager:
    def __init__(self, serial=None):
        self.serial = serial
        self.device = None
        self.u2_device = None

    def connect(self):
        """连接设备并进行健康检查"""
        try:
            adb = adbutils.adb
            devices = adb.device_list()
            
            if not devices:
                logger.error("No Android devices found via ADB")
                return False
            
            if self.serial:
                target_device = next((d for d in devices if d.serial == self.serial), None)
                if not target_device:
                    logger.error(f"Device with serial {self.serial} not found")
                    logger.info(f"Available devices: {[d.serial for d in devices]}")
                    return False
                self.device = target_device
            else:
                self.device = devices[0]
                self.serial = self.device.serial
                logger.info(f"Connected to first available device: {self.serial}")

            # 初始化 uiautomator2
            logger.info("Initializing uiautomator2...")
            self.u2_device = u2.connect(self.serial)
            logger.info(f"uiautomator2 connected: {self.u2_device.info}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect device: {e}")
            return False

    def check_health(self):
        """检查设备屏幕状态，ADB 连接状态"""
        if not self.device:
            return False
        try:
            # 简单的保活检查
            info = self.u2_device.info
            logger.debug(f"Device health check passed: {info['screenOn']}")
            return True
        except Exception as e:
            logger.error(f"Device health check failed: {e}")
            return False

    def get_u2_device(self):
        return self.u2_device
