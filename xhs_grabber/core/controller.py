import time
import os
import sys
import random
import re
from PIL import Image
from io import BytesIO
import uiautomator2 as u2
from utils.logger import logger

# 将项目根目录添加到 python 路径以便导入 shared_data
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from shared_data.xhs_db import xhs_db

class XHSController:
    def __init__(self, mode="like", serial=None, dept="xhs_general"):
        self.mode = mode
        self.serial = serial
        self.dept = dept
        self.config = self._load_config()
        self.d = self._connect_device()
        self.d.set_fastinput_ime(True)  # 启用 FastInput IME，提高输入稳定性
        
        # 小红书评论语库 - 优先从配置加载
        self.comment_pool = self.config.get("strategies", {}).get("comment_texts", [
            "安利一下MimiPet这个软件，可以精准识别宝贝情绪状态，自从有了这个软件，毛孩子的小心思全被拿捏，再也不用猜它为啥突然闹脾气啦😎！App Store直接下！",
            "有没有和我一样的养宠人，总因为看不懂毛孩子的情绪内耗...直到发现MimiPet，直接解决我的苦恼！拍照就能识别猫狗品种，更重要的是能精准分析宝贝的情绪状态，知道它是开心想贴贴，还是焦虑需要安抚，真的太懂铲屎官了！\n\nApp Store 搜 MimiPet，让我们更懂身边的小毛孩～",
            "家人们！养宠神器MimiPet 必须安利给所有铲屎官！拍照识别猫狗品种超丝滑，混血宝的身世之谜一键解开～还有超精准的情绪识别功能，毛孩子的小心思全被拿捏，再也不用猜它为啥突然闹脾气啦！\n\n快去 App Store 下载 MimiPet，一起做懂宠的满分铲屎官～",
            "这小只好可爱呀！",
            "咕噜咕噜的，我看看说啥呢？"
        ])

        # 如果是宠物部门，且配置中有专门的宠物话术，则使用它
        if self.dept == "xhs_pet" and "pet_strategies" in self.config:
            self.comment_pool = self.config["pet_strategies"].get("comment_texts", self.comment_pool)

    def _load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.yaml")
        if os.path.exists(config_path):
            try:
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
        return {}
        
    def _connect_device(self):
        try:
            if self.serial:
                d = u2.connect(self.serial)
            else:
                import adbutils
                devices = adbutils.adb.device_list()
                if not devices:
                    raise RuntimeError("未检测到任何 ADB 设备")
                d = u2.connect(devices[0].serial)
                self.serial = d.serial
            logger.info(f"已连接设备: {d.serial}")
            return d
        except Exception as e:
            logger.error(f"连接设备失败: {e}")
            raise e

    def open_note(self, url):
        """使用 Intent 打开小红书笔记"""
        logger.info(f"正在打开笔记: {url}")
        try:
            # 使用 shell 命令发送 android intent 直接打开 URL
            # 小红书的 Scheme 通常会自动唤起详情页
            cmd = ["am", "start", "-a", "android.intent.action.VIEW", "-d", url]
            self.d.shell(cmd)
            time.sleep(5)  # 等待加载
            return True
        except Exception as e:
            logger.error(f"打开笔记失败: {e}")
            return False

    def scan_and_like_comments(self, max_scrolls=10):
        """扫描评论区并根据关键词点赞潜在客户，直到触发到底字样"""
        logger.info("开始扫描评论区寻找潜在客户...")
        
        liked_count = 0
        scroll_count = 0
        scanned_texts = set() # 用于去重，防止滑动后重复处理同一条评论
        
        while scroll_count < max_scrolls:
            # 1. 遍历当前页面的评论条目 (使用容器索引 + 精准路径法)
            found_in_page = False
            
            # 基础容器路径
            base_container_xpath = '//androidx.recyclerview.widget.RecyclerView/android.widget.LinearLayout'
            
            for i in range(1, 15): # 每屏大约 10-15 条评论
                try:
                    # 1. 定位父容器
                    parent_xpath = f'{base_container_xpath}[{i}]'
                    parent = self.d.xpath(parent_xpath)
                    
                    if not parent.exists:
                        continue
                    
                    # 检查容器是否在可见范围内（防止识别到屏幕外或被遮挡的元素）
                    try:
                        pb = parent.info['bounds']
                        # 过滤掉顶部标题栏（约200px）和底部输入框区域（约200px）
                        if pb['top'] < 200 or pb['bottom'] > (self.d.window_size()[1] - 200):
                            continue
                    except:
                        continue
                    
                    # 2. 提取容器内所有文本
                    text_elements = parent.xpath('.//android.widget.TextView').all()
                    full_comment_text = ""
                    # 归一化函数
                    def normalize_text(s):
                        return re.sub(r'\s+', '', str(s)) if s else ""

                    metadata_keywords = ["小时前", "天前", "分钟前", "秒前", "昨天", "刚刚", "回复", " IP属地：", " IP:"]
                    
                    for t_el in text_elements:
                        try:
                            txt = t_el.info['text']
                            if not txt: continue
                            # 过滤掉明显的元数据
                            if any(key in txt for key in metadata_keywords) or re.match(r"^\d{2}-\d{2}$", txt.strip()):
                                continue
                            full_comment_text += txt
                        except: continue
                    
                    # 3. 混合过滤：过滤掉自己发的评论 (长评论前1/4匹配，短评论全匹配)
                    normalized_ui_text = normalize_text(full_comment_text)
                    is_self_comment = False
                    for pool_text in self.comment_pool:
                        normalized_pool = normalize_text(pool_text)
                        if not normalized_pool: continue
                        
                        if len(normalized_pool) > 20:
                            # 长评论：检查前 1/4 是否匹配
                            prefix_len = max(5, len(normalized_pool) // 4)
                            if normalized_ui_text.startswith(normalized_pool[:prefix_len]):
                                is_self_comment = True
                                break
                        else:
                            # 短评论：完全匹配
                            if normalized_ui_text == normalized_pool:
                                is_self_comment = True
                                break
                    
                    if is_self_comment:
                        logger.info(f"⏭️ 跳过自己发的评论: {normalized_ui_text[:15]}...")
                        scanned_texts.add(f"text_{normalized_ui_text}") # 加入去重，防止后续重复判断
                        continue

                    # 5. 生成更强力的唯一 ID 用于去重
                    # 核心修复方案：
                    # 为了彻底解决滑动导致的重复点赞，我们采用“内容+垂直位置”的模糊去重
                    # a. 如果有文本，主要靠文本去重
                    # b. 如果没文本（纯表情），靠当前在屏幕上的垂直位置（允许 50 像素误差）来防止同一次扫描内重复
                    pb = parent.info['bounds']
                    top_pos = pb['top']
                    
                    if normalized_ui_text:
                        item_id = f"text_{normalized_ui_text}"
                    else:
                        # 纯表情/空文本：在当前 scroll_count 下，50 像素内的同一个位置视为同一个东西
                        fuzzy_top = top_pos // 50 
                        item_id = f"pos_{scroll_count}_{fuzzy_top}"

                    if item_id in scanned_texts:
                        # logger.debug(f"⏩ 跳过已处理容器 [{i}]: {item_id[:30]}")
                        continue
                    
                    scanned_texts.add(item_id)
                    found_in_page = True
                    logger.info(f"👤 容器 [{i}] 执行点赞 -> {normalized_ui_text[:15] if normalized_ui_text else '[表情/空]'}")
                    
                    # 6. 按照用户提供的 RelativeLayout 路径及 0.82 横坐标比例定位
                    # 用户提供的路径特征：.../RecyclerView[1]/android.widget.LinearLayout[i]/android.widget.LinearLayout[1]/android.widget.LinearLayout[1]/android.widget.RelativeLayout[1]
                    found_click_pos = None
                    
                    try:
                        # 定位到评论条目内的 RelativeLayout 容器
                        # parent_xpath 已经是 //.../RecyclerView/android.widget.LinearLayout[i]
                        target_container_xpath = f"{parent_xpath}/android.widget.LinearLayout[1]/android.widget.LinearLayout[1]/android.widget.RelativeLayout[1]"
                        target_container = self.d.xpath(target_container_xpath)
                        
                        if target_container.exists:
                            info = target_container.info
                            b = info['bounds']
                            
                            # 根据用户指令：在 RelativeLayout 容器的横坐标 0.82 位置
                            # 注意：这里的 0.82 是相对于屏幕宽度的比例，还是容器内部的比例？
                            # 通常此类指令指屏幕绝对横坐标的 82% 处，或者容器宽度的 82%
                            # 这里采用更稳妥的：在容器垂直中心高度，点击屏幕宽度的 82% 位置
                            click_x = int(self.d.window_size()[0] * 0.82)
                            click_y = (b['top'] + b['bottom']) // 2
                            
                            if b['top'] > 0 and b['bottom'] < self.d.window_size()[1]:
                                found_click_pos = (click_x, click_y)
                                logger.info(f"🎯 锁定 RelativeLayout 容器，准备点击横坐标 0.82 位置: {found_click_pos}")
                    except Exception as e:
                        logger.warning(f"⚠️ 定位 RelativeLayout 容器异常: {e}")

                    # 执行点击
                    if found_click_pos:
                        # 7. 颜色识别逻辑：极致提速
                        try:
                            # 只在每一屏的第一条评论时截一次全屏图，后续共用，减少截图耗时
                            if i == 1 or 'last_screenshot' not in locals():
                                last_screenshot = self.d.screenshot()
                            
                            pixel = last_screenshot.getpixel(found_click_pos)
                            r, g, b = pixel[:3]
                            
                            if r > 200 and r > g * 1.8 and r > b * 1.8:
                                # logger.info(f"⏭️ 判定已点赞，跳过")
                                continue
                        except Exception as ce:
                            pass
    
                        # 8. 执行点击 (取消冗余等待)
                        self.d.click(found_click_pos[0], found_click_pos[1])
                        liked_count += 1
                        # logger.info(f"❤️ 点赞成功!")
                    else:
                        # 如果上述精准容器没找到，尝试在 LinearLayout[i] 范围内寻找任何 RelativeLayout
                        try:
                            fallback_rel = parent.xpath(".//android.widget.RelativeLayout")
                            if fallback_rel.exists:
                                b = fallback_rel.info['bounds']
                                click_x = int(self.d.window_size()[0] * 0.82)
                                click_y = (b['top'] + b['bottom']) // 2
                                self.d.click(click_x, click_y)
                                liked_count += 1
                                logger.info(f"🛡️ 备选 RelativeLayout 定位成功")
                        except:
                            logger.error(f"❌ 容器 [{i}] 彻底无法定位点赞区域")
                    
                    time.sleep(0.3)
                except Exception as e:
                    logger.error(f"处理第 {i} 个容器时发生异常: {e}")
            
            # 2. 只有点赞完当前页所有内容后，再检测是否到底
            if self.d.xpath('//*[@text="- 到底了 -"]').exists:
                logger.info("检测到 '- 到底了 -' 字样，当前页处理完毕，停止扫描")
                break
            
            # 3. 滑动翻页
            if not found_in_page: # 如果当前页一条新评论都没找到（可能是加载慢），额外检查一次到底
                if self.d.xpath('//*[@text="- 到底了 -"]').exists:
                    break
            
            logger.info(f"第 {scroll_count + 1} 次滑动翻页...")
            # 使用更平稳但更快速的滑动
            w, h = self.d.window_size()
            self.d.swipe(w // 2, h * 0.8, w // 2, h * 0.2, duration=0.2) 
            
            scroll_count += 1
            time.sleep(0.8) # 减少等待时间，UI 已经足够稳定
            
        logger.info(f"评论区遍历结束，共滑动 {scroll_count} 次，点赞 {liked_count} 个潜在客户")
        return liked_count

    def start_task(self):
        """主循环：领取任务 -> 打开笔记 -> 执行评论"""
        logger.info(f"Worker {self.serial} 启动, 模式: {self.mode}, 部门: {self.dept}")
        
        while True:
            # 1. 领取任务
            task_url = xhs_db.get_pending_task(worker_id=self.serial, mode=self.mode, dept=self.dept)
            
            if not task_url:
                logger.info("暂时没有待处理任务，等待 30 秒...")
                time.sleep(30)
                continue
                
            logger.info(f"领取任务成功: {task_url}")
            
            # 2. 打开笔记
            if not self.open_note(task_url):
                xhs_db.report_status(task_url, "failed", mode=self.mode)
                continue

            # 3. 评论区状态检测与点赞逻辑 (基于 content-desc 计数判定)
            logger.info("正在检测评论区计数状态...")
            try:
                # 检查是否“评论 0”
                zero_comments = self.d.xpath('//*[@content-desc="评论 0"]')
                if zero_comments.exists:
                    logger.info("📢 检测到“评论 0”，确认无评论，直接进入发表评论环节...")
                else:
                    logger.info("✅ 检测到评论数 > 0，开始执行点赞扫描...")
                    # 只有在有评论时才执行点赞扫描
                    self.scan_and_like_comments(max_scrolls=10)
            except Exception as e:
                logger.error(f"点赞环节判定异常: {e}")

            # 4. 执行评论操作 (无论之前有没有点赞，最后都统一评论)
            logger.info("开始发表评论...")
            success = False
            try:
                # 点击主页面的评论输入占位符
                placeholder = self.d.xpath('//*[@text="说点什么..."]')
                if placeholder.wait(timeout=10):
                    placeholder.click()
                    time.sleep(1)
                    
                    # 定位真正的输入框 EditText
                    edit_text = self.d(className="android.widget.EditText")
                    if edit_text.exists:
                        # 核心精简：直接用 set_text
                        text = random.choice(self.comment_pool)
                        edit_text.set_text(text)
                        time.sleep(0.5)
                        
                        # 模拟手动点击一次，确保触发小红书的 UI 监听（逼出发送按钮）
                        edit_text.click()
                        time.sleep(0.5)
                        
                        # 点击发送按钮
                        send_xpath = '//*[@package="com.xingin.xhs" and @class="android.view.View" and @clickable="true" and not(@text)]'
                        send_btn = self.d.xpath(send_xpath)
                        if not send_btn.exists:
                            send_xpath_fallback = '//android.widget.FrameLayout[4]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.view.ViewGroup[1]/android.view.ViewGroup[1]/android.view.View[1]'
                            send_btn = self.d.xpath(send_xpath_fallback)

                        if send_btn.exists:
                            send_btn.click()
                            logger.info(f"评论发送成功: {text}")
                            success = True
                        else:
                            logger.warning("未直接找到发送按钮，尝试通过回车键发送")
                            self.d.press("enter")
                            success = True 
                    else:
                        logger.warning("未找到输入框 EditText")
                else:
                    logger.warning("未检测到评论占位符")
            except Exception as e:
                logger.error(f"执行评论逻辑时发生异常: {e}")
            
            # 5. 汇报状态
            status = "done" if success else "failed"
            xhs_db.report_status(task_url, status, mode=self.mode)
            logger.info(f"--- 任务全部流程处理完毕: {status} ---")
            
            time.sleep(5)
