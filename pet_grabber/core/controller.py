import time
import yaml
import re
import sys
import os
from core.device_mgr import DeviceManager
from core.driver_wrapper import DriverWrapper
from utils.logger import logger
from utils.human_sim import random_delay
from core.actions.workflow_pet_translator import PetTranslatorWorkflow

# 添加路径以便导入 shared_data
ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_PATH)
try:
    from shared_data.db_manager import DBManager
    # 显式指定共享数据库路径
    SHARED_DB_PATH = os.path.join(ROOT_PATH, "shared_data", "tasks.db")
except ImportError:
    DBManager = None
    SHARED_DB_PATH = None
    logger.warning("Shared DBManager not found, running in standalone mode.")

class PetController:
    def __init__(self, serial=None, dept="pet"):
        self.device_mgr = DeviceManager(serial=serial)
        if not self.device_mgr.connect():
            raise RuntimeError("Pet Grabber: Failed to connect to device")
        
        self.db = DBManager(SHARED_DB_PATH) if DBManager else None
        self.serial = self.device_mgr.serial
        self.driver = DriverWrapper(self.device_mgr)
        self.config = self._load_config()
        self.dept = dept
        self.mode = "pet_translator" 

        # 初始化翻译软件专项工作流
        self.workflow = PetTranslatorWorkflow(self.driver, self.config)
        self.workflow.controller = self  # 建立反向引用，方便工作流访问数据库统计功能
        
    def _load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def start_task(self):
        logger.info(f"Pet Grabber Worker {self.serial} started (Dept: {self.dept}, Mode: {self.mode})")
        # 启动时确保屏幕点亮
        self.driver.ensure_screen_on()
        
        task_count = 0
        while True:
            task_count += 1
            logger.info(f"--- Pet Loop Cycle #{task_count} ---")
            # 每次循环前重新加载配置，确保话术更新实时生效
            try:
                self.config = self._load_config()
                # 更新工作流中的配置
                self.workflow.config = self.config
                self.workflow.wf_config = self.config.get('pet_translator_workflow', {})
                self.workflow.ui_ids = self.config.get('ui_ids', {})
                logger.debug("Config reloaded")
            except Exception as e:
                logger.warning(f"Failed to reload config: {e}")

            if self.db:
                # 领取特定部门的任务
                logger.info(f"Fetching pending task for serial={self.serial}, dept={self.dept}, mode={self.mode}")
                url = self.db.get_pending_task(self.serial, mode=self.mode, dept=self.dept)
            else:
                logger.info("Standalone mode: no tasks. Sleeping...")
                time.sleep(30)
                continue
            
            if not url:
                logger.info("No pending tasks found in DB. Sleeping 10s...")
                time.sleep(10)
                continue

            logger.info(f"Pet Department processing video: {url}")
            try:
                self.driver.ensure_screen_on()
                self.ensure_app_ready()
                self.navigate_to_video(url)
                
                if not self.verify_navigation_success():
                    logger.warning(f"Pet Grabber: Navigation verification failed for {url}, retrying...")
                    self.navigate_to_video(url)
                    if not self.verify_navigation_success():
                        logger.error(f"Pet Grabber: Persistent navigation failure for {url}")
                        self.db.report_status(url, "failed", mode=self.mode)
                        continue

                # 执行固定工作流
                logger.info(f"Pet Grabber: Executing translator workflow for {url}")
                success = self.workflow.execute(url)

                if success:
                    self.db.report_status(url, "done", mode=self.mode)
                    logger.success(f"Pet Task finished: {url}")
                    # 任务完成后返回，清理界面
                    # 确保多次返回直到回到信息流
                    for _ in range(3):
                        self.driver.press_back() 
                        random_delay(0.5, 1)
                    random_delay(1, 2)
                else:
                    # 如果失败了，让它回到 pending 状态
                    self.db.report_status(url, "pending", mode=self.mode)
                    
            except Exception as e:
                logger.error(f"Error processing pet task {url}: {e}")
                self.db.report_status(url, "failed", mode=self.mode)
                self.driver.press_back()
                self.driver.press_back()
            
            random_delay(5, 10)

    def navigate_to_video(self, url):
        logger.info(f"Navigating to {url}")
        self.driver.ensure_screen_on()
        
        current_pkg = self.driver.d.app_current().get('package')
        if current_pkg != "com.ss.android.ugc.aweme":
            logger.info("Pet Grabber: App not in foreground, restarting...")
            self.driver.d.app_start("com.ss.android.ugc.aweme", stop=True)
            time.sleep(5)
        
        video_id_match = re.search(r'video/(\d+)', url)
        if video_id_match:
            video_id = video_id_match.group(1)
            scheme_url = f"snssdk1128://feed/detail/{video_id}"
            self.driver.d.shell(f"am start -a android.intent.action.VIEW -d {scheme_url}")
        else:
            self.driver.d.open_url(url)
        
        # 等待页面加载
        max_wait = 20
        start_time = time.time()
        success = False
        
        # 实时获取最新的 UI ID
        comment_btn_id = self.workflow.ui_ids.get('comment_button', 'com.ss.android.ugc.aweme:id/enf')
        
        while time.time() - start_time < max_wait:
            current_pkg = self.driver.d.app_current().get('package')
            if current_pkg == "com.ss.android.ugc.aweme":
                if self.driver.d(text="打开").exists:
                    logger.info("Pet Grabber: Found 'Open' button, clicking...")
                    self.driver.d(text="打开").click()
                
                if self.driver.d(resourceId=comment_btn_id).exists:
                    logger.success(f"Pet Grabber: Navigation success, found comment button: {comment_btn_id}")
                    success = True
                    break
                else:
                    logger.debug(f"Pet Grabber: Waiting for comment button {comment_btn_id}...")
            else:
                logger.debug(f"Pet Grabber: Waiting for app foreground, current: {current_pkg}")
            time.sleep(2)
        random_delay(3, 5)
    
    def ensure_app_ready(self):
        """确保抖音 App 已启动并在前台"""
        current_pkg = self.driver.d.app_current().get('package')
        if current_pkg != "com.ss.android.ugc.aweme":
            self.driver.d.app_start("com.ss.android.ugc.aweme")
            time.sleep(5)
        
        popups = ["以后再说", "取消", "我知道了", "允许", "拒绝"]
        for text in popups:
            if self.driver.d(text=text).exists:
                self.driver.d(text=text).click()
                time.sleep(1)

    def verify_navigation_success(self, timeout=15):
        """验证导航是否成功"""
        start_time = time.time()
        comment_btn_id = self.workflow.ui_ids.get('comment_button', 'com.ss.android.ugc.aweme:id/enf')
        
        while time.time() - start_time < timeout:
            current_pkg = self.driver.d.app_current().get('package')
            if current_pkg == "com.ss.android.ugc.aweme":
                # 只要评论按钮在，或者已经在评论区了，都算导航成功
                if self.driver.d(resourceId=comment_btn_id).exists:
                    return True
                input_id = self.workflow.wf_config.get('comment_input_box')
                if input_id and self.driver.d(resourceId=input_id).exists:
                    return True
                if self.driver.d(text="打开").exists:
                    self.driver.d(text="打开").click()
            time.sleep(1.5)
        return False
