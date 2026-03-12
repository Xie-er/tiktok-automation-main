import os
import sys
import time
import uiautomator2 as u2

# 修复导入路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
wrj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for path in [project_root, wrj_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

from utils.logger import logger
from shared_data.db_manager import DBManager
from shared_data.fans_db_manager import FansDBManager

class WRJController:
    def __init__(self, mode="like", serial=None, dept="uav"):
        self.mode = mode
        self.serial = serial or "default_worker"
        self.dept = dept
        self.current_blogger = "unknown" # 当前正在处理的博主
        
        # 数据库路径：E:\tiktok\shared_data\tasks.db
        self.db_path = os.path.join(project_root, "shared_data", "tasks.db")
        self.db = DBManager(self.db_path)
        
        # 粉丝数据库：E:\tiktok\shared_data\fans.db
        self.fans_db = FansDBManager()
        
        # 潜在客户关键词
        self.potential_customer_keywords = [
            "多少钱", "多钱", "多少米", "几米", "价格", "报价", "啥价", 
            "咋卖", "怎么卖", "卖多少", "报个价", "底价", "最低多少", 
            "一台多少", "一套多少"
        ]
        
        try:
            logger.info(f"Connecting to device: {self.serial}")
            self.d = u2.connect(self.serial)
            logger.info(f"Device {self.serial} connected.")
        except Exception as e:
            logger.error(f"Failed to connect to device {self.serial}: {e}")
            self.d = None

    def navigate_to_video(self, url):
        """第一步：领取到视频任务后，跳转到视频页面"""
        if not self.d:
            return False

        # 深度清洗 URL，去除首尾空格、反引号、引号
        url = url.strip().replace('`', '').replace('"', '').strip()
        logger.info(f"Navigating to video URL: {url}")
        
        try:
            # 1. 尝试使用 Intent 直接跳转（最快最准）
            cmd = f'am start -a android.intent.action.VIEW -d "{url}" com.ss.android.ugc.aweme'
            self.d.shell(cmd)
            
            # 2. 尝试同步剪贴板作为备份
            # 针对 Android 13+ 的 SecurityException (Package android does not belong to 2000) 进行静默处理
            try:
                self.d.set_clipboard(url)
            except Exception as ce:
                # 如果是权限问题，记录简短警告而非堆栈信息
                if "SecurityException" in str(ce):
                    logger.debug("Clipboard sync skipped due to system permission restrictions (SecurityException).")
                else:
                    logger.warning(f"Clipboard sync failed: {str(ce)[:100]}")
            
            # 等待视频加载，处理可能的弹窗
            max_wait = 20
            start_time = time.time()
            while time.time() - start_time < max_wait:
                # 检查头像 ID 是否出现
                if self.d(resourceId="com.ss.android.ugc.aweme:id/user_avatar").exists:
                    logger.info("Landed on video page.")
                    return True
                
                # 自动点击常见的跳转确认弹窗
                for text in ["允许", "我知道了", "打开", "立即查看"]:
                    btn = self.d(textContains=text)
                    if btn.exists:
                        btn.click()
                        break
                time.sleep(1)
            
            return self.d(resourceId="com.ss.android.ugc.aweme:id/user_avatar").exists
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return False

    def process_potential_customers(self):
        """
        Step 1.5: 在进入博主主页前，先扫描当前视频评论区，寻找潜在客户并互动
        参考 pet_grabber 的遍历逻辑：通过头像坐标去重，并匹配关键词
        """
        logger.info("Starting potential customer scan in comments...")
        
        # 1. 打开评论区
        # 尝试使用 wrj 现有的评论按钮 ID
        comment_btn = self.d(resourceId="com.ss.android.ugc.aweme:id/eog")
        if not comment_btn.exists(timeout=5):
            # 备份 ID (参考 pet_grabber)
            comment_btn = self.d(resourceId="com.ss.android.ugc.aweme:id/en1")
            
        if not comment_btn.exists:
            logger.warning("Comment button not found, skipping potential customer scan.")
            return False
        
        comment_btn.click()
        time.sleep(2)
        
        # 2. 遍历评论区
        processed_coords = [] # 记录已处理过的头像坐标，防止滑动后重复点击
        scroll_count = 0
        
        while True:
            # 获取当前屏幕上的所有头像和评论文本
            avatars = self.d(resourceId="com.ss.android.ugc.aweme:id/avatar")
            comment_texts = self.d(resourceId="com.ss.android.ugc.aweme:id/content")
            
            count = avatars.count
            logger.info(f"Scan comments: found {count} avatars in current view (Scroll {scroll_count}).")
            
            for i in range(count):
                try:
                    # 规则：如果是第一页的第一个，跳过
                    if scroll_count == 0 and i == 0:
                        continue
                        
                    avatar = avatars[i]
                    if not avatar.exists: continue
                    
                    # 获取坐标用于去重
                    bounds = avatar.info['visibleBounds']
                    cx = (bounds['left'] + bounds['right']) // 2
                    cy = (bounds['top'] + bounds['bottom']) // 2
                    
                    # 检查是否处理过
                    is_processed = False
                    for px, py in processed_coords:
                        if abs(px - cx) < 15 and abs(py - cy) < 15:
                            is_processed = True
                            break
                    if is_processed: continue
                    
                    processed_coords.append((cx, cy))
                    
                    # 获取对应的评论文本
                    comment_text = ""
                    if i < comment_texts.count:
                        comment_text = comment_texts[i].get_text()
                    
                    if not comment_text:
                        continue
                        
                    # 检查关键词
                    is_potential = False
                    for kw in self.potential_customer_keywords:
                        if kw in comment_text:
                            logger.success(f"Potential customer found! Comment: '{comment_text}' (Keyword: {kw})")
                            is_potential = True
                            break
                    
                    if is_potential:
                        # 点击头像进入主页
                        avatar.click()
                        time.sleep(2)
                        self.interact_with_potential_customer_profile()
                        time.sleep(1)
                        
                        # 重新获取元素列表
                        avatars = self.d(resourceId="com.ss.android.ugc.aweme:id/avatar")
                        comment_texts = self.d(resourceId="com.ss.android.ugc.aweme:id/content")
                            
                except Exception as e:
                    logger.error(f"Error processing comment {i}: {e}")
                    continue
            
            # 检查是否到底：仅根据“暂时没有更多了”判定
            if self.d.xpath('//*[@text="暂时没有更多了"]').exists:
                logger.success("Reached the end of comments: '暂时没有更多了' detected.")
                break
            
            # 向上滑动
            logger.info(f"Scrolling comments (Total scrolls: {scroll_count + 1})...")
            self.d.swipe(500, 1500, 500, 1000, steps=30)
            time.sleep(1.5)
            scroll_count += 1
            
            # 安全冗余：如果滑动次数过多（如 100 次）仍未检测到结束语，强制退出防止死循环
            if scroll_count > 100:
                logger.warning("Reached safety limit of 100 scrolls. Ending scan to avoid infinite loop.")
                break
        
        # 3. 关闭评论区
        logger.info("Closing comments section.")
        self.d.press("back")
        time.sleep(1.5)
        return True

    def interact_with_potential_customer_profile(self):
        """
        潜在客户互动：进入主页 -> 点开第一个视频 -> 点赞 -> 返回
        """
        logger.info("Interacting with potential customer profile...")
        
        # 寻找第一个作品
        # 兼容两种常见的作品容器 ID
        first_work = self.d(resourceId="com.ss.android.ugc.aweme:id/cover")
        if not first_work.exists:
            first_work = self.d(resourceId="com.ss.android.ugc.aweme:id/container")
        
        if not first_work.exists:
            # 尝试通过层级定位
            first_work = self.d(className="android.widget.FrameLayout", descriptionContains="作品").child(className="android.view.View", instance=0)
            
        if first_work.exists(timeout=3):
            first_work.click()
            time.sleep(2)
            
            # 双击点赞
            screen_width = self.d.info['displayWidth']
            screen_height = self.d.info['displayHeight']
            # 在中心位置双击
            cx, cy = screen_width // 2, screen_height // 2
            self.d.click(cx, cy)
            time.sleep(0.05)
            self.d.click(cx, cy)
            
            logger.info("Liked potential customer's first video.")
            time.sleep(1.5)
            
            # 返回两次回到评论页
            logger.info("Returning to comments list...")
            self.d.press("back") # 从视频回主页
            time.sleep(1.5)
            self.d.press("back") # 从主页回评论列表
            time.sleep(1.5)
            return True
        else:
            logger.info("No works found on potential customer profile. Returning...")
            self.d.press("back")
            time.sleep(1.5)
            return False

    def click_avatar(self):
        """第二步：进入博主主页（通过从右向左滑动，避免进入直播间）"""
        logger.info("Entering blogger profile via swipe (right to left)...")
        
        # 检查是否在视频播放页
        avatar = self.d(resourceId="com.ss.android.ugc.aweme:id/user_avatar")
        if avatar.exists(timeout=5):
            # 获取博主昵称作为标识（在滑动前获取）
            try:
                nickname_el = self.d(resourceId="com.ss.android.ugc.aweme:id/title")
                if nickname_el.exists:
                    self.current_blogger = nickname_el.get_text()
                else:
                    self.current_blogger = f"blogger_{int(time.time())}"
            except:
                self.current_blogger = "unknown_blogger"
                
            try:
                # 执行从右向左滑动进入主页
                screen_width = self.d.info['displayWidth']
                screen_height = self.d.info['displayHeight']
                
                start_x = int(screen_width * 0.9)
                end_x = int(screen_width * 0.1)
                y = int(screen_height * 0.5)
                
                logger.info(f"Swiping to enter {self.current_blogger}'s profile...")
                self.d.swipe(start_x, y, end_x, y, duration=0.2)
                time.sleep(2)
                
                # 验证是否进入主页
                if self.d(resourceId="com.ss.android.ugc.aweme:id/593").exists(timeout=5):
                    logger.info(f"Entered blogger profile successfully: {self.current_blogger}")
                    return True
            except Exception as e:
                logger.error(f"Swipe error: {e}")

        logger.warning("Failed to enter profile via swipe.")
        return False

    def click_followers_list(self):
        """第三步：点开粉丝状况"""
        logger.info("Clicking followers status (com.ss.android.ugc.aweme:id/593)...")
        followers_btn = self.d(resourceId="com.ss.android.ugc.aweme:id/593")
        if followers_btn.exists(timeout=5):
            # 记录点击前的状态：博主主页的特有按钮
            # 我们用粉丝按钮本身的存在作为“还在主页”的证据
            followers_btn.click()
            time.sleep(3) # 给一点时间让弹窗消失或页面跳转
            
            # 逻辑改进：如果点击后，粉丝按钮依然存在且可见
            # 说明页面没有跳转到粉丝列表页，极有可能是因为隐私弹窗（弹窗通常不阻塞 UI 查找）
            if self.d(resourceId="com.ss.android.ugc.aweme:id/593").exists:
                logger.warning("Still on blogger profile after clicking followers button. Likely privacy restricted.")
                # 额外检查一下是否有 viewpager 隐私框
                privacy_box = self.d(resourceId="com.ss.android.ugc.aweme:id/viewpager")
                if privacy_box.exists and self.d(textContains="为保护该创作者隐私").exists:
                    logger.warning("Privacy protection box detected.")
                return "privacy"

            logger.info("Successfully navigated away from profile to followers list.")
            return True
        logger.warning("Followers button (id/593) not found on page.")
        return False

    def interact_with_fan_profile(self):
        """处理粉丝主页互动：有作品则点赞评论，无作品则返回"""
        logger.info("Checking for works on fan profile...")
        
        # 1. 判定是否有作品
        # 抖音主页作品列表通常在 "作品" 标签下，第一个作品通常可以被定位到
        # 我们寻找列表中的第一个作品项 (通常包含 'desc' 属性或特定的 layout)
        first_work = self.d(resourceId="com.ss.android.ugc.aweme:id/cover") # 常见作品封面 ID
        if not first_work.exists:
            # 尝试通过位置定位（作品列表的第一行第一列）
            first_work = self.d(className="android.widget.FrameLayout", descriptionContains="作品").child(className="android.view.View", instance=0)
            
        if first_work.exists(timeout=3):
            logger.info("Works found. Starting interaction...")
            # A. 点击进入第一个作品
            first_work.click()
            time.sleep(2) # 等待 2s
            
            # B. 双击点赞
            screen_width = self.d.info['displayWidth']
            screen_height = self.d.info['displayHeight']
            center_x, center_y = screen_width // 2, screen_height // 2
            logger.info(f"Double clicking to like at ({center_x}, {center_y})...")
            self.d.double_click(center_x, center_y, duration=0.1)
            time.sleep(1)
            
            # C. 评论互动
            # 打开评论区按钮
            comment_btn = self.d(resourceId="com.ss.android.ugc.aweme:id/eog")
            if comment_btn.exists(timeout=3):
                comment_btn.click()
                time.sleep(1.5)
                
                # 点击评论框并输入 [旺柴]
                comment_input = self.d(resourceId="com.ss.android.ugc.aweme:id/emn")
                if comment_input.exists(timeout=3):
                    comment_input.click()
                    time.sleep(1)
                    # 输入文字
                    self.d.send_keys("[旺柴]", clear=True)
                    time.sleep(1)
                    
                    # 点击发送按钮
                    send_btn = self.d(resourceId="com.ss.android.ugc.aweme:id/eq0")
                    if send_btn.exists(timeout=3):
                        send_btn.click()
                        logger.info("Comment '[旺柴]' sent successfully.")
                        time.sleep(2)
                    else:
                        logger.warning("Send button not found.")
                else:
                    logger.warning("Comment input not found.")
            else:
                logger.warning("Comment button not found.")
                
            # D. 固定返回三次回到粉丝列表页
            logger.info("Returning to fan list page (3 times back)...")
            for i in range(3):
                self.d.press("back")
                time.sleep(1.5)
                logger.debug(f"Back press {i+1}/3")
            return True
        else:
            logger.info("No works found on this profile. Returning (1 time back)...")
            self.d.press("back")
            time.sleep(2)
            return True
            
        return False

    def process_followers_list(self):
        """第四步：处理粉丝列表，滚动并点击所有粉丝条目进入主页"""
        logger.info(f"Processing followers list for {self.current_blogger}...")
        
        # 获取屏幕尺寸供后续使用
        screen_width = self.d.info['displayWidth']
        screen_height = self.d.info['displayHeight']
        
        # 等待列表加载
        time.sleep(4)
        
        processed_fans = set()  # 用于记录已处理的粉丝（根据其 content-desc 或 文本标识）
        last_processed_xpath = None  # 记录上一次成功处理的粉丝 Xpath
        consecutive_duplicates = 0  # 连续发现已处理粉丝的计数
        max_duplicates = 30  # 增加容错，连续发现 30 个已处理粉丝才考虑退出
        scroll_count = 0  # 记录滑动次数
        consecutive_no_new_swipes = 0 # 连续多少次滑动没有发现新粉丝
        
        try:
            while True:
                # 1. 定位粉丝条目
                items = None
                viewpager = self.d(resourceId="com.ss.android.ugc.aweme:id/viewpager")
                
                if viewpager.exists:
                    items = viewpager.child(descriptionMatches="^[^头像]+$") 
                    if items.count == 0:
                        items = viewpager.child(descriptionMatches=".+")
                
                if items is None or items.count == 0:
                    items = self.d(descriptionMatches="^[^头像]+$")
                
                count = items.count
                logger.debug(f"Found {count} potential fan entries in current view.")
                
                if count == 0:
                    # 检查是否到底
                    if self.d(textContains="暂时没有更多了").exists or self.d(textContains="隐私设置").exists:
                        logger.info("Confirmed end of list via text.")
                        break
                    
                    logger.warning("No fan entries found. Trying a small scroll to refresh...")
                    self.d.swipe(screen_width // 2, screen_height // 2, screen_width // 2, screen_height // 3, duration=0.5)
                    time.sleep(2)
                    consecutive_no_new_swipes += 1
                    if consecutive_no_new_swipes > 3:
                        logger.warning("Still no entries after 3 refresh swipes. Breaking.")
                        break
                    continue
                
                found_new_in_this_view = False
                
                # 遍历当前屏幕可见的条目
                for i in range(count):
                    item = items[i]
                    if not item.exists:
                        continue
                        
                    # 检查条目是否显示完整
                    try:
                        bounds = item.info['bounds']
                        if bounds['bottom'] > screen_height * 0.95:
                            logger.debug(f"Fan entry #{i+1} is too close to bottom, skipping to scroll...")
                            break 
                    except:
                        pass
                        
                    # 获取描述作为唯一标识
                    try:
                        info = item.info
                        desc = info.get('contentDescription', '')
                    except Exception as ie:
                        continue
                        
                    if not desc or "头像" in desc or len(desc) < 2:
                        continue
                        
                    # 构造粉丝标识
                    fan_xpath = f'//*[@content-desc="{desc}"]'
                    
                    # 检查数据库是否已处理过
                    if self.fans_db.is_fan_processed(self.current_blogger, fan_xpath) or desc in processed_fans:
                        consecutive_duplicates += 1
                        continue
                    
                    # 发现新粉丝
                    found_new_in_this_view = True
                    consecutive_duplicates = 0
                    consecutive_no_new_swipes = 0
                    processed_fans.add(desc)
                    
                    # 保存到粉丝数据库
                    fan_nickname = desc.split(',')[0] if ',' in desc else desc[:10]
                    self.fans_db.save_fan(self.current_blogger, fan_nickname, desc, fan_xpath)
                    
                    logger.info(f"Processing new fan: {fan_nickname}...")
                    
                    # 2. 点击进入主页
                    inner_btn = item.child(resourceId="com.ss.android.ugc.aweme:id/18a")
                    if inner_btn.exists:
                        inner_btn.click()
                    else:
                        item.click()
                    
                    time.sleep(3)
                    
                    # 3. 互动并返回
                    success = self.interact_with_fan_profile()
                    if success:
                        self.fans_db.mark_fan_processed(self.current_blogger, fan_xpath, 'done')
                    else:
                        logger.warning(f"Interaction with {fan_nickname} failed, ensuring return to list...")
                        for _ in range(3):
                            if self.d(resourceId="com.ss.android.ugc.aweme:id/viewpager").exists: break
                            self.d.press("back")
                            time.sleep(1.5)

                # 4. 滚动逻辑
                # 检查显式的结束标识
                if self.d(textContains="暂时没有更多了").exists or self.d(textContains="隐私设置").exists:
                    logger.info("Fan list traversal completed: Reached end indicator.")
                    break

                # 如果这轮没发现新粉丝，增加计数
                if not found_new_in_this_view:
                    consecutive_no_new_swipes += 1
                    logger.info(f"No new fans in this view. (Consecutive: {consecutive_no_new_swipes})")
                
                # 退出条件：连续 30 个重复 或者 连续 3 次滑动都没新粉丝
                if consecutive_duplicates >= max_duplicates or consecutive_no_new_swipes >= 3:
                    logger.info(f"Traversal finished: duplicates={consecutive_duplicates}, no_new_swipes={consecutive_no_new_swipes}")
                    break
                
                # 计算滑动参数
                start_x = screen_width // 2
                dist = 2132 if scroll_count == 0 else 2106
                start_y = int(screen_height * 0.9)
                end_y = start_y - dist
                
                # 确保坐标不越界
                if end_y < 10: end_y = 10
                if start_y > screen_height - 10: start_y = screen_height - 10
                
                # 执行滑动
                logger.info(f"Scrolling (count: {scroll_count+1}, dist: {dist}px)...")
                self.d.swipe(start_x, start_y, start_x, end_y, duration=1.5)
                scroll_count += 1
                time.sleep(2)
                
            logger.info(f"Traverse completed. Total fans processed: {len(processed_fans)}")
            return True
        except Exception as e:
            logger.error(f"Error in process_followers_list: {e}")
            return False

    def return_to_home(self):
        """
        退出机制：不断返回直到看见抖音首页底栏容器。
        优化：增加超时等待和双重确认，防止 UI 刷新延迟导致的过度返回。
        """
        logger.info("Starting exit mechanism: Returning to home screen...")
        max_back_attempts = 10
        
        for i in range(max_back_attempts):
            # 1. 增加等待确认时间：使用 timeout 轮询检查首页特征
            # 给 UI 树 3 秒时间来刷新和显示底栏
            bottom_nav = self.d(resourceId="com.ss.android.ugc.aweme:id/bottom_space")
            
            if bottom_nav.exists(timeout=3.0):
                # 2. 找到了底栏，进一步检查是否是“干净”的首页（没有视频播放页的头像）
                avatar = self.d(resourceId="com.ss.android.ugc.aweme:id/user_avatar")
                if not avatar.exists:
                    # 3. 双重确认：再等 1 秒看看状态是否稳定，防止瞬时判定的误差
                    time.sleep(1.0)
                    if bottom_nav.exists and not avatar.exists:
                        logger.info("Confirmed: Successfully returned to clean TikTok home screen.")
                        return True
                else:
                    logger.debug("Bottom nav found but avatar still exists, probably in transition...")
            
            # 如果没通过检查，按一次返回键
            logger.debug(f"Home not detected. Back press {i+1}/{max_back_attempts}...")
            self.d.press("back")
            # 按完返回后给系统充足的时间去渲染下一页
            time.sleep(4.0)
            
        logger.warning("Reached max back attempts. Final check for safety...")
        if self.d(resourceId="com.ss.android.ugc.aweme:id/bottom_space").exists:
            return True
        return False

    def start_task(self):
        """
        无人机工作流主循环
        """
        if not self.d:
            logger.error("No device connection.")
            return

        logger.info(f"Drone worker {self.serial} started for dept: {self.dept}")
        
        while True:
            try:
                # 1. 领取任务 (dept='uav')
                url = self.db.get_pending_task(self.serial, mode=self.mode, dept=self.dept)
                
                if not url:
                    time.sleep(10)
                    continue

                logger.info(f"Task fetched: {url}")
                
                # 2. 执行步骤
                # Step 1: 导航
                if not self.navigate_to_video(url):
                    logger.error("Skip: Navigation failed.")
                    continue
                
                # Step 1.5: 扫描评论区寻找潜在客户
                self.process_potential_customers()
                
                # Step 2: 点击头像进入博主主页
                if not self.click_avatar():
                    # 简单重试一次
                    self.d.click(100, 100) # 点击空白处尝试关闭可能的弹窗
                    if not self.click_avatar():
                        continue
                
                # Step 3: 点开粉丝列表
                res = self.click_followers_list()
                if res == "privacy":
                    # 如果遇到隐私限制，直接汇报完成并进入下一个视频
                    logger.info(f"Task skipped due to privacy: {url}. Reporting status to DB...")
                    self.db.report_status(url, "done")
                    self.return_to_home() # 退出到首页
                    continue
                elif not res:
                    self.return_to_home() # 失败也尝试退出
                    continue
 
                # Step 4: 处理粉丝列表
                self.process_followers_list()

                # 处理完成后，汇报任务状态为 done
                logger.info(f"Task completed: {url}. Reporting status to DB...")
                self.db.report_status(url, "done")

                # 执行退出机制，返回到首页
                self.return_to_home()

                logger.info("Phase 1 completed: Processed followers list. Fetching next task...")

                # 不再执行返回操作，直接进入下一个循环（下一个任务的 navigate_to_video 会处理跳转）
                # time.sleep(2)
            except Exception as e:
                logger.error(f"Task loop error: {e}")
                self.return_to_home() # 发生异常也尝试退出
                time.sleep(5)
