import yaml
import time
import random
import os
from core.device_mgr import DeviceManager
from utils.human_sim import generate_human_scroll_trajectory, random_delay, get_random_point_in_bounds
from utils.logger import logger

class DriverWrapper:
    def __init__(self, device_mgr: DeviceManager):
        self.d = device_mgr.get_u2_device()
        self.config = self._load_config()
        self.width, self.height = self.d.window_size()
        logger.info(f"Pet Grabber Screen resolution: {self.width}x{self.height}")

    def _load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.yaml")
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def safe_click(self, selector, timeout=10):
        """拟人化点击"""
        ele = None
        if "=" in selector and not selector.startswith("//") and not selector.startswith("xpath="):
            k, v = selector.split("=", 1)
            v = v.strip("'\"")
            if k == "text":
                ele = self.d(text=v)
            elif k == "desc":
                ele = self.d(description=v)
            elif k == "id":
                ele = self.d(resourceId=v)
        elif selector.startswith("//") or selector.startswith("xpath="):
            xpath_str = selector.replace("xpath=", "")
            ele = self.d.xpath(xpath_str)
        else:
            ele = self.d(resourceId=selector)
            
        is_found = False
        try:
            if hasattr(ele, 'wait'):
                is_found = bool(ele.wait(timeout=timeout))
            else:
                is_found = bool(ele.exists)
        except Exception as e:
            logger.warning(f"Error checking existence for {selector}: {e}")
            is_found = False

        if is_found:
            try:
                # 处理 XPath 选择器的情况
                if selector.startswith("//") or selector.startswith("xpath="):
                    # u2 的 xpath 对象 click() 方法本身就支持拟人化点击中心点
                    ele.click()
                    return True

                bounds = ele.info['visibleBounds']
                x, y = get_random_point_in_bounds(bounds)
                logger.debug(f"Pet Grabber clicking element {selector} at ({x}, {y})")
                random_delay(0.2, 0.8)
                self.d.click(x, y)
                return True
            except Exception as e:
                logger.error(f"Error clicking {selector}: {e}")
                return False
        else:
            logger.warning(f"Element {selector} not found within {timeout}s")
            return False

    def human_scroll(self, direction="up"):
        """拟人化滑动"""
        start_x_range = (int(self.width * 0.3), int(self.width * 0.7))
        if direction == "up":
            start_y_range = (int(self.height * 0.7), int(self.height * 0.9))
            end_y_range = (int(self.height * 0.2), int(self.height * 0.4))
        else:
            start_y_range = (int(self.height * 0.2), int(self.height * 0.4))
            end_y_range = (int(self.height * 0.7), int(self.height * 0.9))
            
        start_x = random.randint(*start_x_range)
        start_y = random.randint(*start_y_range)
        end_x = start_x + random.randint(-50, 50)
        end_y = random.randint(*end_y_range)
        
        trajectory = generate_human_scroll_trajectory((start_x, start_y), (end_x, end_y))
        self.d.swipe_points(trajectory, duration=0.5)
        random_delay(0.5, 1.5)

    def ensure_screen_on(self):
        """确保屏幕点亮并解锁（如果没密码）"""
        if not self.d.info.get('screenOn'):
            logger.info("Pet Grabber: Screen is off, turning it on...")
            self.d.screen_on()
            time.sleep(1)
            # 尝试向上滑动解锁（针对无密码设备）
            self.d.swipe(self.width // 2, int(self.height * 0.8), self.width // 2, int(self.height * 0.2), duration=0.2)
            time.sleep(1)

    def dump_hierarchy(self):
        """获取当前 UI 布局 XML"""
        logger.debug("Pet Grabber: Dumping UI hierarchy")
        return self.d.dump_hierarchy()

    def press_back(self):
        """物理返回键"""
        logger.debug("Pet Grabber: Pressing back button")
        self.d.press("back")
        random_delay(0.8, 1.5)

    def click_percent(self, x_pct, y_pct):
        """按比例点击"""
        x = int(self.width * x_pct)
        y = int(self.height * y_pct)
        logger.debug(f"Pet Grabber: Clicking at {x_pct*100}%, {y_pct*100}% ({x}, {y})")
        self.d.click(x, y)
        random_delay(0.5, 1.0)

    def input_text(self, selector, text):
        """输入文本"""
        logger.debug(f"Pet Grabber: Inputting text into {selector}")
        try:
            # 如果是 xpath 选择器，需要特殊处理
            if selector.startswith("//") or selector.startswith("xpath="):
                xpath_str = selector.replace("xpath=", "")
                self.d.xpath(xpath_str).set_text(text)
            else:
                self.d(resourceId=selector).set_text(text)
            return True
        except Exception as e:
            logger.error(f"Pet Grabber: Error inputting text: {e}")
            return False
