import time
import yaml
import re
import sys
import os
from core.device_mgr import DeviceManager
from core.driver_wrapper import DriverWrapper
from utils.parser import UIParser
from utils.logger import logger
from utils.human_sim import random_delay
from data.storage import Storage
from core.actions.like_interaction import LikeInteraction
from core.actions.dm_interaction import DMInteraction
from core.actions.reply_interaction import ReplyInteraction
from core.actions.comment_interaction import CommentInteraction

# 添加路径以便导入 shared_data
ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(ROOT_PATH)
from shared_data.db_manager import DBManager
# 显式指定共享数据库路径
SHARED_DB_PATH = os.path.join(ROOT_PATH, "shared_data", "tasks.db")

class Controller:
    def __init__(self, mode="like", serial=None, dept="general"):
        self.device_mgr = DeviceManager(serial=serial)
        if not self.device_mgr.connect():
            raise RuntimeError("Failed to connect to device")
        
        self.db = DBManager(SHARED_DB_PATH)
        self.serial = self.device_mgr.serial
        self.driver = DriverWrapper(self.device_mgr)
        self.config = self._load_config()
        self.storage = Storage()
        self.mode = mode # 运行模式：like, dm, reply, comment
        self.dept = dept
        
        # 初始化交互动作模块
        self.actions = {
            "like": LikeInteraction(self.driver, self.config),
            "dm": DMInteraction(self.driver, self.config),
            "reply": ReplyInteraction(self.driver, self.config),
            "comment": CommentInteraction(self.driver, self.config)
        }
        
    def _load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def start_task(self):
        """
        开始执行任务，循环从数据库获取
        """
        logger.info(f"Worker {self.serial} started, waiting for tasks...")
        
        while True:
            # 每次任务开始前重新加载配置，确保话术更新实时生效
            try:
                self.config = self._load_config()
                # 更新所有交互动作的配置
                for action_name in self.actions:
                    self.actions[action_name].config = self.config
            except Exception as e:
                logger.warning(f"Failed to reload config: {e}")

            # 1. 从数据库获取一个待处理任务
            # 传入当前模式，以便只获取该模式未完成的任务
            # 仅领取指定部门的任务
            url = self.db.get_pending_task(self.serial, mode=self.mode, dept=self.dept)
            
            if not url:
                # logger.debug("No pending tasks, sleeping...")
                time.sleep(10)
                continue

            logger.info(f"Processing video ({self.mode}): {url}")
            try:
                self.navigate_to_video(url)
                
                # 执行特定模式的操作
                success = False
                no_target_found = False
                
                if self.mode == "like":
                    # 1. 先给当前视频点赞
                    self.actions["like"].execute()
                    logger.info("Main video liked, now processing comments for user interaction...")
                    
                    # 2. 打开评论区并遍历用户
                    if self.open_comment_section():
                        # 点赞模式下，process_comments 会遍历所有用户
                        success = self.process_comments(url)
                    else:
                        logger.warning(f"Could not open comment section for {url}, task considered done as main video liked.")
                        success = True

                elif self.mode == "comment" or self.mode == "reply":
                    # 打开评论区并处理
                    if self.open_comment_section():
                        success = self.process_comments(url)
                        if not success:
                            # 如果执行返回 False，且当前是回复模式，说明可能没找到目标
                            no_target_found = True
                    else:
                        logger.warning(f"Could not open comment section for {url}")
                elif self.mode == "dm":
                    # 私信逻辑
                    success = self.actions["dm"].execute()

                # 汇报完成
                if success:
                    self.db.report_status(url, "done", mode=self.mode)
                    logger.success(f"Task finished ({self.mode}): {url}")
                elif no_target_found and self.mode == "reply":
                    # 特殊处理回复模式：未发现目标也视为“已完成”，防止死循环
                    self.db.report_status(url, "done", mode=self.mode)
                    logger.info(f"No target customers found for reply in {url}. Marking as done to avoid loop.")
                else:
                    logger.error(f"Failed to execute {self.mode} for {url}")
                    # 如果失败了，标记为 pending 以后再试
                    self.db.report_status(url, "pending", mode=self.mode)
                
            except Exception as e:
                logger.error(f"Error processing video {url}: {e}")
                self.db.report_status(url, "failed", mode=self.mode)
                # 尝试恢复
                self.driver.press_back()
                self.driver.press_back()
            
            # 每个视频处理完后随机休息
            random_delay(5, 10)

    def navigate_to_video(self, url):
        """
        跳转到指定视频，优化为优先使用 Scheme 协议
        """
        logger.info(f"Navigating to {url}")
        
        # 尝试从长链接中提取 video_id
        video_id_match = re.search(r'video/(\d+)', url)
        if video_id_match:
            video_id = video_id_match.group(1)
            scheme_url = f"snssdk1128://feed/detail/{video_id}"
            logger.info(f"Using scheme url: {scheme_url}")
            self.driver.d.shell(f"am start -a android.intent.action.VIEW -d {scheme_url}")
        else:
            # 如果不是标准长链，尝试直接用 open_url
            self.driver.d.open_url(url)
            
        # 针对老旧机型增加等待时间，确保页面加载完成
        logger.info("Waiting for video to load...")
        random_delay(15, 20)
    
    def open_comment_section(self):
        """
        点击评论按钮打开评论区
        """
        # 尝试查找评论按钮
        btn_id = self.config['ui_ids']['comment_button']
        logger.info("Opening comment section...")
        if self.driver.safe_click(btn_id):
            random_delay(2, 4) # 等待评论区弹出
            return True
        return False

    def process_comments(self, current_video_url):
        """
        处理评论区逻辑
        """
        logger.info("Start processing comments...")
        
        # 如果是 comment 模式，直接在当前页面执行即可，不需要解析列表
        if self.mode == "comment":
            return self.actions["comment"].execute({"url": current_video_url})

        # 限制处理条数或页数
        # 如果是 like 模式，我们要遍历所有用户，所以增加滚动次数限制
        max_scrolls = 100 if self.mode == "like" else 10
        scroll_count = 0
        last_dump_hash = ""
        no_change_count = 0
        
        # 标记是否至少执行了一次互动（仅对非 like 模式重要，like 模式只要跑完流程就算成功）
        has_interaction = False

        while scroll_count < max_scrolls:
            # 1. Dump UI
            xml = self.driver.dump_hierarchy()
            
            # 检查是否到底
            current_hash = hash(xml)
            if current_hash == last_dump_hash:
                no_change_count += 1
                if no_change_count >= 3:
                    logger.info("Reached bottom of comments")
                    break
            else:
                no_change_count = 0
            last_dump_hash = current_hash
            
            # 2. Parse
            parser = UIParser(xml)
            comments = parser.extract_comments(self.config['ui_ids'])
            
            logger.info(f"Found {len(comments)} comments on screen")
            
            # 3. Filter & Interact
            for comment in comments:
                content = comment['content']
                
                # 如果是 like 模式，跳过关键词匹配，视为匹配成功
                if self.mode == "like":
                    matched_kw = "ALL_USERS_MODE"
                else:
                    matched_kw = parser.match_keywords(content, self.config['keywords'])
                
                if matched_kw:
                    if self.mode != "like":
                        logger.info(f"触达客户：命中关键词 '{matched_kw}'")
                        # 记录到数据库统计表
                        self.db.add_hit_count(dept=self.dept)
                    
                    user_key = str(hash(content))
                    
                    if not self.storage.has_interacted(user_key):
                        if self.interact_user(comment):
                            self.storage.log_interaction(user_key, current_video_url, matched_kw)
                            has_interaction = True
                            
                            # 按照用户要求：
                            # 如果不是 like 模式，完成一个任务即返回 True
                            # 如果是 like 模式，继续遍历
                            if self.mode != "like":
                                return True
                        
                        random_delay(1, 2)
                    else:
                        logger.debug(f"User {user_key} already interacted, skipping")
            
            # 4. Scroll
            self.driver.human_scroll("up")
            random_delay(2, 4)
            scroll_count += 1
        
        # 循环结束
        # 如果是 like 模式，只要遍历完了（无论有没有互动），都算成功
        if self.mode == "like":
            return True
            
        return False

    def interact_user(self, comment_data):
        """
        根据配置调用相应的交互动作
        """
        action_name = self.mode 
        
        if action_name in self.actions:
            # 记录互动，防止重复
            # 对于私信和回复，我们可以根据 uid + action 组合去重
            # 这里简化处理，仍使用 comment content hash
            user_key = f"{str(hash(comment_data['content']))}_{action_name}"
            
            if not self.storage.has_interacted(user_key):
                success = self.actions[action_name].execute(comment_data)
                if success:
                    self.storage.log_interaction(user_key, "N/A", action_name)
                return success
            else:
                logger.debug(f"User already interacted with {action_name}, skipping")
                return False
        else:
            logger.error(f"Action {action_name} not found")
            return False
