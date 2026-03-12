import sys
import os

# 将项目根目录添加到路径，以便导入 shared_data
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

import time
import yaml
import random
import re
from loguru import logger
from core.device_mgr import DeviceManager
from shared_data.db_manager import DBManager

class ScoutController:
    def __init__(self, config_path=None, dept="general"):
        if config_path is None:
            # 默认路径：相对于当前文件的 config/scout_settings.yaml
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "scout_settings.yaml")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.dept = dept
        self.db = DBManager()
        self.device_mgr = DeviceManager(serial=self.config['device']['serial'])
        self.d = None # uiautomator2 device object
        self.last_share_token = None # 用于连续重复检测
        self.last_description = None # 新增：用于连续重复检测文案

    def start(self):
        if not self.device_mgr.connect():
            logger.error("Failed to connect device")
            return
        
        self.d = self.device_mgr.get_u2_device()
        logger.info(f"Scout started for dept: {self.dept}...")
        
        # 获取关键词队列
        keywords = self.config.get('search', {}).get('keywords', [])
        if not keywords:
            # 兼容旧配置
            old_keyword = self.config.get('search', {}).get('keyword')
            keywords = [old_keyword] if old_keyword else []
            
        if not keywords:
            logger.error("未设置采集关键词，任务结束")
            return

        logger.info(f"关键词队列: {keywords}")

        try:
            for keyword in keywords:
                logger.info(f"--- 开始采集关键词: {keyword} ---")
                self.current_keyword = keyword
                self.last_share_token = None # 每个关键词重置重复检测
                self.last_description = None 
                
                # 1. 打开抖音并进入搜索
                self._enter_search(keyword)
                
                # 2. 点击第一个视频进入全屏播放模式
                ui_ids = self.config.get('ui_ids', {})
                cover_id = ui_ids.get('first_video_cover', "com.ss.android.ugc.aweme:id/db_")
                # 优先使用 instance=0 的第一个视频
                first_video = self.d(resourceId="com.ss.android.ugc.aweme:id/db_", instance=0)
                if not first_video.exists:
                    first_video = self.d(resourceId=cover_id)
                
                if first_video.wait(timeout=5):
                    first_video.click()
                    logger.success(f"已进入关键词 [{keyword}] 的全屏播放模式")
                    time.sleep(3)
                    
                    # 3. 循环采集
                    self._crawl_loop(keyword)
                    
                    # 4. 采集完一个关键词，退回到搜索页，准备下一个
                    logger.info(f"关键词 [{keyword}] 采集完成，正在重置状态...")
                    self._reset_to_search_page()
                else:
                    logger.error(f"未找到关键词 [{keyword}] 的第一个视频，跳过")
                    self._reset_to_search_page()
                    continue

            logger.success("所有关键词队列任务已完成！")
            
        except KeyboardInterrupt:
            logger.warning("用户手动停止采集任务 (Ctrl+C)")
        except Exception as e:
            logger.exception(f"采集过程中出现异常: {e}")
        finally:
            logger.info("Scout 采集任务流程结束")

    def _reset_to_search_page(self):
        """从全屏播放模式退回到搜索结果页，甚至搜索输入页"""
        logger.info("正在退回到搜索页面...")
        # 连按两次返回键通常能回到搜索结果列表
        self.d.press("back")
        time.sleep(1)
        self.d.press("back")
        time.sleep(2)
        
        # 检查是否回到了搜索框页面，如果没有，可能需要更多次返回
        # 这里可以根据实际 UI 进一步优化

    def _apply_filters(self):
        """执行‘最新发布’筛选流程"""
        logger.info("正在执行筛选流程：最新发布")
        filter_btn_id = "com.ss.android.ugc.aweme:id/iwu"
        latest_btn_id = "com.ss.android.ugc.aweme:id/vao"
        
        filter_btn = self.d(resourceId=filter_btn_id)
        if filter_btn.wait(timeout=5):
            filter_btn.click()
            time.sleep(2)
            
            # 优先通过文字定位
            latest_btn = self.d(text="最新发布")
            if not latest_btn.exists:
                latest_btn = self.d(resourceId=latest_btn_id, instance=1)
            
            if latest_btn.wait(timeout=5):
                latest_btn.click()
                logger.success("已选择‘最新发布’")
                time.sleep(1)
                
                # 新增：检测并点击“还未看过” (登录用户工作流)
                unseen_btn = self.d(text="还未看过")
                if unseen_btn.exists:
                    unseen_btn.click()
                    logger.success("已选择‘还未看过’ (登录用户模式)")
                    time.sleep(1)
                
                # 再次点击筛选按钮或点击下方视频区域退出
                self.d.click(0.5, 0.8) 
                time.sleep(2)
            else:
                logger.warning("未找到‘最新发布’按钮")
        else:
            logger.warning("未找到筛选按钮")

    def _enter_search(self, keyword):
        """进入搜索界面并输入关键词"""
        logger.info(f"Searching for: {keyword}")
        
        ui_ids = self.config.get('ui_ids', {})
        
        # 1. 点击搜索图标 (使用 XPath 定位)
        search_xpath = '//*[@resource-id="com.ss.android.ugc.aweme:id/2px"]/android.widget.Button[1]/android.widget.FrameLayout[1]'
        search_btn = self.d.xpath(search_xpath)
        if not search_btn.exists:
            search_id = ui_ids.get('search_btn', "com.ss.android.ugc.aweme:id/ko6")
            search_btn = self.d(description="搜索") or self.d(resourceId=search_id)
            
        # 注意：XPath 对象没有 .wait() 方法，只有 .exists 属性
        # 如果是 Selector 对象，可以使用 .wait()
        is_exists = False
        if hasattr(search_btn, 'wait'):
            is_exists = search_btn.wait(timeout=5)
        else:
            is_exists = search_btn.exists
            
        if is_exists:
            search_btn.click()
            time.sleep(2)
        
        # 2. 输入关键词
        input_id = "com.ss.android.ugc.aweme:id/fl_intput_hint_container"
        search_input = self.d(resourceId=input_id)
        if not search_input.exists:
            input_class = ui_ids.get('search_input', "android.widget.EditText")
            search_input = self.d(className=input_class) if "." in input_class else self.d(resourceId=input_class)
            
        if search_input.wait(timeout=5):
            # 激活并清除输入
            search_input.click()
            time.sleep(1)
            self.d.set_fastinput_ime(True)
            self.d.clear_text()
            self.d.send_keys(keyword)
            self.d.set_fastinput_ime(False)
            logger.success(f"输入关键词成功: {keyword}")
            time.sleep(1)
            
            # 点击搜索按钮
            confirm_id = "com.ss.android.ugc.aweme:id/43u"
            search_confirm_btn = self.d(resourceId=confirm_id)
            if not search_confirm_btn.exists:
                confirm_id_old = ui_ids.get('search_confirm_btn', "com.ss.android.ugc.aweme:id/4v-")
                search_confirm_btn = self.d(text="搜索", resourceId=confirm_id_old)
                
            if search_confirm_btn.wait(timeout=3):
                search_confirm_btn.click()
            else:
                self.d.send_action("search")
            
            time.sleep(5) # 等待加载
        
        # 3. 切换到“视频”页签 (Instance 定位)
        logger.info("正在切换到‘视频’页签...")
        video_tab = self.d(resourceId="com.ss.android.ugc.aweme:id/yvu", instance=1)
        if not video_tab.exists:
            # XPath 兜底
            video_xpath = '//*[@resource-id="com.ss.android.ugc.aweme:id/wlv"]//android.widget.LinearLayout[1]/*[2]'
            video_tab = self.d.xpath(video_xpath)
            
        # 同样处理 XPath 和 Selector 的差异
        tab_exists = False
        if hasattr(video_tab, 'wait'):
            tab_exists = video_tab.wait(timeout=5)
        else:
            tab_exists = video_tab.exists
            
        if tab_exists:
            video_tab.click()
            logger.success("成功切换到视频页签")
            time.sleep(2)
            
            # 4. 执行筛选
            self._apply_filters()
        else:
            logger.error("未找到视频页签")

    def _crawl_loop(self, category):
        """无限循环滑动并提取链接"""
        video_count = 0
        
        logger.info(f"正在采集关键词 [{category}]...")
        while True:
            video_count += 1
            logger.info(f"正在采集第 {video_count} 个视频...")
            
            # 1. 提取当前视频链接、share_token 和文案
            result = self._get_current_video_link()
            if result:
                url, share_token, description = result
                
                # --- 最高优先级：连续重复检测 (Token 或 文案) ---
                is_duplicate = False
                if share_token and self.last_share_token and share_token == self.last_share_token:
                    logger.warning(f"检测到连续两次采集的 share_token 一致: {share_token}")
                    is_duplicate = True
                elif description and self.last_description and description == self.last_description:
                    logger.warning(f"检测到连续两次采集的视频文案一致: {description[:20]}...")
                    is_duplicate = True

                if is_duplicate:
                    logger.success("判定为采集任务已完成（到底或卡死），自动结束任务")
                    break
                
                # 更新上一次的状态
                self.last_share_token = share_token
                self.last_description = description
                
                # 存储到对应部门的数据库中
                added = self.db.add_task(url, category=category, dept=self.dept, share_token=share_token, description=description)
                if added:
                    logger.success(f"成功保存到 [{self.dept}] 任务详情: {url}")
                else:
                    logger.info(f"视频已存在 (URL/Token/文案重复)，跳过保存，但继续采集流程: {url}")
            
            # 2. 向上滑动到下一个视频
            self._swipe_next()
            
            # 从配置中读取停留时间间隔
            min_stay = self.config.get('crawler', {}).get('min_video_stay', 15)
            max_stay = self.config.get('crawler', {}).get('max_video_stay', 20)
            
            wait_time = random.uniform(min_stay, max_stay)
            logger.info(f"等待 {wait_time:.1f}s 后采集下一个...")
            time.sleep(wait_time)

    def _close_share_panel(self):
        """关闭分享面板"""
        logger.info("正在退出分享面板...")
        self.d.press("back")
        time.sleep(1)

    def _get_current_video_link(self):
        """点击分享 -> 复制链接 -> 获取剪贴板"""
        try:
            ui_ids = self.config.get('ui_ids', {})
            # 1. 查找分享按钮 (优先使用 zop)
            share_btn = self.d(resourceId="com.ss.android.ugc.aweme:id/zop")
            if not share_btn.exists:
                primary_share_id = ui_ids.get('share_btn', "com.ss.android.ugc.aweme:id/zhp")
                share_btn = self.d(resourceId=primary_share_id) or self.d(description="分享")
            
            if not share_btn.wait(timeout=5):
                logger.error("未找到分享按钮")
                return None
            
            share_btn.click()
            time.sleep(2)
            
            # 2. 检查分享面板是否打开
            panel_id = ui_ids.get('share_panel', "com.ss.android.ugc.aweme:id/function_container")
            container = self.d(resourceId=panel_id)
            if not container.wait(timeout=5):
                logger.error("分享面板未打开")
                return None
            
            # 3. 向左滑动定位复制链接
            bounds = container.info['bounds']
            center_y = (bounds['top'] + bounds['bottom']) / 2
            self.d.swipe(bounds['right']*0.8, center_y, bounds['right']*0.2, center_y, duration=0.2)
            time.sleep(1)
            
            copy_text = ui_ids.get('copy_link_text', "复制链接")
            copy_btn = self.d(text=copy_text)
            if not copy_btn.exists:
                copy_btn = self.d(text="分享链接")
            
            if copy_btn.wait(timeout=5):
                copy_btn.click()
                time.sleep(1.5)
                
                # 从剪贴板获取链接、share_token 和文案内容
                raw_text = self.d.clipboard
                url_match = re.search(r'https://v\.douyin\.com/[\w-]+/', raw_text)
                
                # 提取 share_token (URL 之后的部分，或者特定的正则模式)
                # 示例: 5.69 复制打开抖音，... https://v.douyin.com/xxx/ 02/19 hOK:/ p@q.re
                share_token = None
                description = None
                if url_match:
                    url = url_match.group(0)
                    
                    # 1. 提取文案 (URL 之前的所有文字，并去掉开头的随机数字)
                    # 示例: 7.94 复制打开抖音，看看【斑斑和煤球的作品】搞不懂玉米为啥...
                    full_desc = raw_text[:url_match.start()].strip()
                    # 使用正则去掉开头的数字和空格，保留“复制打开抖音”及其后的内容
                    description = re.sub(r'^[\d.\s]+', '', full_desc)
                    
                    # 2. 提取识别码 (share_token)
                    # 尝试匹配 URL 之后的识别码模式 (类似 02/19 hOK:/ p@q.re)
                    token_match = re.search(r'(\d{2}/\d{2}\s+[a-zA-Z0-9]{3,}:/\s+[\w@.]+)', raw_text)
                    if token_match:
                        share_token = token_match.group(1)
                    else:
                        # 兜底：如果正则没匹配到，取 URL 之后的所有非空内容
                        after_url = raw_text[url_match.end():].strip()
                        if after_url:
                            share_token = after_url
                    
                    self._close_share_panel()
                    return url, share_token, description
                else:
                    logger.warning("剪贴板中未找到有效链接")
            else:
                logger.error("未找到‘复制链接’按钮")

            self._close_share_panel()
            return None
        except Exception as e:
            logger.error(f"提取链接出错: {e}")
            return None

    def _swipe_next(self):
        """模拟人手向上滑动"""
        logger.info("正在向上滑动到下一个视频...")
        width, height = self.d.window_size()
        x = width // 2 + random.randint(-10, 10)
        y_start = int(height * 0.8) + random.randint(-20, 20)
        y_end = int(height * 0.2) + random.randint(-20, 20)
        self.d.swipe(x, y_start, x, y_end, duration=0.2)
        time.sleep(1)

if __name__ == "__main__":
    scout = ScoutController()
    scout.start()
