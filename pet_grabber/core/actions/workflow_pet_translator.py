import time
import os
from core.actions.base import BaseAction
from utils.logger import logger

class PetTranslatorWorkflow(BaseAction):
    def __init__(self, driver, config):
        super().__init__(driver, config)
        self.config = config
        self.controller = None # 由 controller 注入
        # 兼容性字段：供 controller.py 调用
        self.wf_config = config.get('pet_translator_workflow', {})
        self.ui_ids = config.get('ui_ids', {})

    def execute(self, video_url: str = None) -> bool:
        """
        引导模式：严格按照用户指令执行
        """
        d = self.driver.d
        
        # 用户指令第一步：打开评论区
        ID_OPEN = self.ui_ids.get('comment_button', "com.ss.android.ugc.aweme:id/en1")
        ID_INPUT = self.ui_ids.get('comment_input_box', "com.ss.android.ugc.aweme:id/el7")
        ID_SEND = self.ui_ids.get('comment_send_btn', "com.ss.android.ugc.aweme:id/eqf")
        
        logger.info(f"执行第一步：打开评论区 ({ID_OPEN})")
        
        target = d(resourceId=ID_OPEN)
        if target.exists(timeout=5):
            target.click()
            time.sleep(1.5) # 缩短等待评论区打开时间
        else:
            logger.error(f"失败：未找到 resourceid 为 {ID_OPEN} 的按钮")
            return False

        # 用户指令第二步：点击输入框并输入话术
        logger.info(f"执行第二步：点击输入框 ({ID_INPUT})")
        if d(resourceId=ID_INPUT).exists(timeout=3):
            d(resourceId=ID_INPUT).click()
            time.sleep(0.5) # 缩短点击后的等待
            
            # 优先从配置获取话术，如果没有则使用默认值
            custom_comments = self.wf_config.get('custom_comments', [])
            if custom_comments and len(custom_comments) > 0:
                import random
                text = random.choice(custom_comments)
            else:
                text = "你家的毛孩子好可爱"
                
            logger.info(f"正在输入：{text}")
            d(resourceId=ID_INPUT).set_text(text)
            time.sleep(1) # 缩短输入后的等待
        else:
            logger.error(f"失败：未找到输入框 {ID_INPUT}")
            return False

        # 用户指令第三步：点击发送
        logger.info(f"执行第三步：点击发送按钮 ({ID_SEND})")
        send_btn = d(resourceId=ID_SEND)
        if not send_btn.exists:
            # 尝试通过文本查找
            send_btn = d(text="发送")
            
        if send_btn.exists(timeout=5):
            logger.info("找到发送按钮，正在点击...")
            send_btn.click()
            logger.success("发送成功")
            time.sleep(1.5) # 缩短等待发送完成时间
        else:
            logger.error(f"失败：未找到发送按钮 {ID_SEND} 或文本'发送'")
            # 尝试强制点击坐标（如果知道位置的话，但这里先记录错误）
            return False

        # 用户指令第四步：遍历头像（从第二个开始）
        logger.info("执行第四步：开始遍历用户头像...")
        ID_AVATAR = self.ui_ids.get('avatar_id', "com.ss.android.ugc.aweme:id/avatar")
        ID_COMMENT_TEXT = self.ui_ids.get('comment_content_id', "com.ss.android.ugc.aweme:id/content")
        
        # 获取关键词列表
        target_keywords = self.ui_ids.get('target_keywords', [])
        logger.info(f"目标精准关键词: {target_keywords}")
        
        # 记录已处理过的头像坐标，防止滑动后重复点击
        processed_coords = []
        last_exit_time = 0  # 记录上一次从主页退出的时间
        
        scroll_count = 0
        consecutive_no_new_any_avatar = 0 # 连续没有发现【任何】新头像的次数 (用于判断是否到底)
        
        while scroll_count < 999: # 增加滑动上限，由“暂时没有更多了”或连续未发现新头像判定结束
            # 直接通过 ID 获取当前屏幕的所有头像
            avatars = d(resourceId=ID_AVATAR)
            count = avatars.count

            logger.info(f"当前屏幕发现 {count} 个潜在目标")
            
            found_any_new_avatar_on_this_page = False # 只要这一页有任何一个新头像（不管匹不匹配关键词），就说明没到底
            
            for i in range(count):
                # 规则：如果是第一页的第一个，跳过（那是发完评论后的自己）
                if scroll_count == 0 and i == 0:
                    continue
                
                # 重新获取，防止 UI 变动
                current_avatars = d(resourceId=ID_AVATAR)
                current_comments = d(resourceId=ID_COMMENT_TEXT)
                
                if i >= current_avatars.count: break
                
                avatar = current_avatars[i]
                if not avatar.exists: continue
                
                # 获取位置
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
                
                # 只要进入到这里，说明发现了一个物理意义上的“新头像”
                found_any_new_avatar_on_this_page = True
                consecutive_no_new_any_avatar = 0 # 重置到底检测计数器
                
                # 【简化重构】直接按照用户指定的 ID 获取评论文字，不使用其他方法
                match_keyword = False
                comment_text = ""
                
                try:
                    if i < current_comments.count:
                        comment_text = current_comments[i].get_text()
                    
                    if comment_text:
                        logger.info(f"直接获取评论内容: {comment_text}")
                        if not target_keywords: # 如果没设置关键词，默认全部匹配
                            logger.info("未设置关键词，视为触达客户")
                            if self.controller and self.controller.db:
                                self.controller.db.add_hit_count(dept=getattr(self.controller, 'dept', 'pet'))
                            match_keyword = True
                        else:
                            for kw in target_keywords:
                                if kw in comment_text:
                                    logger.success(f"触达客户：命中关键词 '{kw}'")
                                    # 记录到数据库统计表
                                    if self.controller and self.controller.db:
                                        self.controller.db.add_hit_count(dept=getattr(self.controller, 'dept', 'pet'))
                                    match_keyword = True
                                    break
                    else:
                        logger.warning(f"未能直接获取到第 {i} 个评论文字")
                except Exception as e:
                    logger.warning(f"获取评论异常: {str(e)}")

                if not match_keyword and target_keywords:
                    # 记录已处理，防止下一轮重复扫描（即使不匹配，它也是一个已处理的物理位置）
                    processed_coords.append((cx, cy))
                    continue
                
                # 发现新头像且匹配成功（或无关键词限制）
                # 按照指令：从上一个主页出来的时刻到点开下一个头像的时刻间隔一共 1.5 秒
                if last_exit_time > 0:
                    elapsed = time.time() - last_exit_time
                    wait_needed = 1.5 - elapsed
                    if wait_needed > 0:
                        time.sleep(wait_needed)
                
                # 立即点击
                logger.info(f"点击目标 (第 {len(processed_coords) + 1} 个): ({cx}, {cy})")
                d.click(cx, cy)
                
                # 严明逻辑：进用户主页之后要等 1.5 秒才执行后续操作（确保主页加载及规避风控）
                logger.info("已进入用户主页，等待 1.5 秒...")
                time.sleep(1.5) 
                
                # 用户主页第一个视频点赞逻辑
                ID_FIRST_VIDEO = self.ui_ids.get('video_container', "com.ss.android.ugc.aweme:id/container")
                
                logger.info(f"寻找主页第一个视频 ({ID_FIRST_VIDEO})")
                first_video = d(resourceId=ID_FIRST_VIDEO)
                if first_video.exists(timeout=3):
                    # 点击进入第一个视频
                    logger.info("点击进入第一个视频")
                    first_video.click()
                    # 确保视频内容和 UI 加载完成，防止双击变成暂停
                    time.sleep(2.0) 
                    
                    # 按照用户要求：双击速度要快一点，间隔缩短，确保触发点赞而非暂停
                    logger.info("执行超快速双击点赞（0.05s 间隔）")
                    sw, sh = d.window_size()
                    # 在屏幕中心偏上位置双击，避开可能的底部 UI 干扰
                    click_x, click_y = sw // 2, sh // 2
                    d.click(click_x, click_y)
                    time.sleep(0.05) # 极短间隔确保被识别为双击
                    d.click(click_x, click_y)
                    logger.success("双击点赞指令已发送")
                    time.sleep(1.2)
                    
                    # 退出视频播放页，回到主页
                    d.press("back")
                    time.sleep(0.8)
                else:
                    logger.warning("未能在主页找到第一个视频容器")

                # 立即返回
                d.press("back")
                last_exit_time = time.time() # 记录退出的时刻
                
                processed_coords.append((cx, cy))
            
            if not found_any_new_avatar_on_this_page:
                consecutive_no_new_any_avatar += 1
                logger.info(f"当前页面未发现【任何】新头像（已全部处理过），已连续 {consecutive_no_new_any_avatar} 次")
            
            # 如果连续 3 次滑动都没发现任何新头像，说明物理上已经到底了
            if consecutive_no_new_any_avatar >= 3:
                logger.success("已经连续多次未发现任何新头像，判定为评论区已触底，任务结束")
                break
            
            # 【用户指令】检查是否出现“暂时没有更多了”
            if d.xpath('//*[@text="暂时没有更多了"]').exists:
                logger.success("检测到‘暂时没有更多了’，评论已全部遍历完成，任务结束")
                break

            # 匀速、小幅度向下滑动找更多
            logger.info("小幅度匀速滑动找更多用户...")
            d.swipe(500, 1500, 500, 1000, steps=30) 
            time.sleep(1) # 滑动后稍微等 UI 稳定，防止检测不到头像
            scroll_count += 1
                
        logger.success("遍历用户头像任务完成")
        return True
