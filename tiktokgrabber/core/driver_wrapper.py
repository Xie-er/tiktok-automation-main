import yaml
import time
import random
from core.device_mgr import DeviceManager
from utils.human_sim import generate_human_scroll_trajectory, random_delay, get_random_point_in_bounds
from utils.logger import logger

class DriverWrapper:
    def __init__(self, device_mgr: DeviceManager):
        self.d = device_mgr.get_u2_device()
        self.config = self._load_config()
        self.width, self.height = self.d.window_size()
        logger.info(f"Screen resolution: {self.width}x{self.height}")

    def _load_config(self):
        with open("config/settings.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def safe_click(self, selector, timeout=10):
        """
        拟人化点击：
        1. 查找元素
        2. 计算可视区域内的随机点
        3. 随机延迟
        4. 点击
        """
        # selector 可以是 resource-id, text, description 等
        # 这里简化处理，假设传入的是 key=value 形式或者直接是 resourceId
        
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
            # 支持 XPath
            xpath_str = selector.replace("xpath=", "")
            ele = self.d.xpath(xpath_str)
        else:
            # 默认为 resourceId
            ele = self.d(resourceId=selector)
            
        # 统一使用 wait 等待元素出现，避免 exists 属性不可调用的问题 (特别是 XPath)
        is_found = False
        try:
            if hasattr(ele, 'wait'):
                # 支持 timeout 的等待
                is_found = bool(ele.wait(timeout=timeout))
            else:
                # 回退到 exists 属性 (不支持 timeout，只能检查当前状态)
                is_found = bool(ele.exists)
        except Exception as e:
            logger.warning(f"Error checking existence for {selector}: {e}")
            is_found = False

        if is_found:
            try:
                bounds = ele.info['visibleBounds']
                x, y = get_random_point_in_bounds(bounds)
                
                logger.debug(f"Clicking element {selector} at ({x}, {y})")
                # 随机延迟
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
        """
        拟人化滑动
        direction: "up" (手指上滑，内容下滚), "down" (手指下滑，内容上滚)
        """
        # 定义滑动区域 (屏幕中间 50% 区域)
        start_x_range = (int(self.width * 0.3), int(self.width * 0.7))
        
        if direction == "up":
            start_y_range = (int(self.height * 0.7), int(self.height * 0.9))
            end_y_range = (int(self.height * 0.2), int(self.height * 0.4))
        else:
            start_y_range = (int(self.height * 0.2), int(self.height * 0.4))
            end_y_range = (int(self.height * 0.7), int(self.height * 0.9))
            
        start_x = random.randint(*start_x_range)
        start_y = random.randint(*start_y_range)
        
        end_x = start_x + random.randint(-50, 50) # 允许轻微横向偏移
        end_y = random.randint(*end_y_range)
        
        duration = random.randint(300, 600)
        
        logger.debug(f"Scrolling {direction} from ({start_x}, {start_y}) to ({end_x}, {end_y})")
        
        # 生成轨迹
        trajectory = generate_human_scroll_trajectory((start_x, start_y), (end_x, end_y), duration)
        
        # 执行滑动
        try:
            self.d.touch.down(trajectory[0][0], trajectory[0][1])
            # 采样执行，避免点太多导致卡顿
            for point in trajectory[1::3]: # 每3个点取一个
                self.d.touch.move(point[0], point[1])
                # 极短的 sleep 可能导致 adb 阻塞，u2 内部可能处理不好，这里暂时不加 sleep，依靠通信延迟
                
            self.d.touch.move(trajectory[-1][0], trajectory[-1][1])
            self.d.touch.up(trajectory[-1][0], trajectory[-1][1])
            return True
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            return False

    def input_text(self, selector, text):
        """
        增强版文本输入：
        1. 尝试 u2 set_text
        2. 失败尝试 adb input text
        3. 支持中文 (adb 需要 ADBKeyboard 支持，这里暂时只支持非中文或依赖 u2)
        """
        try:
            # 1. 点击聚焦
            ele = self.d(resourceId=selector)
            if not ele.exists:
                logger.error(f"Input field {selector} not found")
                return False
                
            ele.click()
            random_delay(0.5, 1)
            
            # 2. 尝试 set_text
            logger.debug(f"Inputting text: {text}")
            ele.set_text(text)
            random_delay(0.5, 1)
            
            # 3. 检查是否输入成功
            current_text = ele.get_text()
            if current_text != text:
                logger.warning("set_text failed or incomplete, trying adb input...")
                # 再次点击聚焦
                ele.click()
                # 4. 尝试 adb input (仅适用英文/数字，中文需要特殊处理)
                # 注意：adb input text 不支持空格，需要替换为 %s
                safe_text = text.replace(" ", "%s")
                self.d.shell(f"input text {safe_text}")
                random_delay(0.5, 1)
            
            return True
        except Exception as e:
            logger.error(f"Input text failed: {e}")
            return False

    def click_percent(self, x_pct, y_pct):
        """
        根据百分比坐标点击
        """
        x = int(self.width * x_pct)
        y = int(self.height * y_pct)
        # 加微小随机偏移
        x += random.randint(-5, 5)
        y += random.randint(-5, 5)
        logger.debug(f"Clicking percent ({x_pct}, {y_pct}) -> ({x}, {y})")
        self.d.click(x, y)

    def dump_hierarchy(self):
        return self.d.dump_hierarchy()

    def press_back(self):
        random_delay(0.5, 1.0)
        self.d.press("back")
        logger.info("Pressed Back")

    def start_app(self, package_name):
        self.d.app_start(package_name)
        logger.info(f"App {package_name} started")

    def stop_app(self, package_name):
        self.d.app_stop(package_name)
        logger.info(f"App {package_name} stopped")
