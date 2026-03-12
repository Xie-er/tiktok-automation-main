import random
from core.actions.base import BaseAction
from utils.logger import logger
from utils.human_sim import random_delay

class DMInteraction(BaseAction):
    """
    私信交互模块：点击头像 -> 进主页 -> 点击发私信 -> 输入话术 -> 发送 -> 返回
    """
    def execute(self, comment_data: dict) -> bool:
        logger.info("Executing DMInteraction...")
        bounds = comment_data['avatar_bounds']
        
        # 1. 点击头像进入主页
        x = (bounds[0] + bounds[2]) // 2
        y = (bounds[1] + bounds[3]) // 2
        logger.info(f"Clicking avatar to enter profile...")
        self.driver.d.click(x, y)
        random_delay(3, 5)
        
        success = False
        
        # 2. 查找“发私信”按钮
        # 抖音主页可能有直接的“发私信”按钮，也可能在“更多”菜单里
        # 针对新版 UI：可能是纸飞机图标，建议优先用 ID 查找
        dm_btn_id = self.config['ui_ids']['profile_dm_btn']
        
        entered_dm_page = False
        
        # 尝试点击配置的 ID
        if self.driver.safe_click(dm_btn_id, timeout=5):
            entered_dm_page = True
        # 备选方案：尝试查找 Description 包含 "私信" 的元素
        elif self.driver.safe_click("desc='私信'", timeout=3):
            entered_dm_page = True
        # 备选方案：尝试查找 Text 包含 "私信" 的元素
        elif self.driver.safe_click("text='私信'", timeout=3):
            entered_dm_page = True
        # 备选方案：更多菜单
        else:
            logger.info("Direct DM button not found, trying 'More' menu...")
            more_btn_id = self.config['ui_ids']['profile_more_btn']
            if self.driver.safe_click(more_btn_id):
                random_delay(1, 2)
                if self.driver.safe_click("text='发私信'"):
                    entered_dm_page = True
        
        if not entered_dm_page:
            logger.warning("Could not enter DM page")
            self.driver.press_back() # 退回评论区
            return False

        # 等待私信页加载
        random_delay(2, 3)
        
        # 3. 输入并发送私信
        input_id = self.config['ui_ids']['dm_input_field']
        send_btn_id = self.config['ui_ids']['dm_send_btn']
        
        # 针对未关注人，只能发一条消息的情况
        # 检查是否存在输入框
        if self.driver.d(resourceId=input_id).exists:
            # 随机选一条话术
            message = random.choice(self.config['strategies']['dm_texts'])
            logger.info(f"Sending DM: {message}")
            
            if not self.config['limits']['dry_run']:
                # 使用增强版输入方法
                if self.driver.input_text(input_id, message):
                    random_delay(1, 2)
                    
                    # 点击发送
                    if not self.driver.safe_click(send_btn_id):
                        # 尝试回车发送
                        self.driver.d.press("enter")
                    
                    logger.info("DM sent successfully")
                else:
                    logger.error("Failed to input DM text")
            else:
                logger.info(f"Dry run: skip sending DM '{message}'")
            
            success = True
            random_delay(1, 2)
            
            # 4. 返回主页
            # 注意：如果进入了私信页，通常需要按一次返回到用户主页
            logger.info("Back from DM page")
            dm_back_id = self.config['ui_ids'].get('dm_page_back_btn')
            if dm_back_id and self.driver.safe_click(dm_back_id, timeout=3):
                logger.info("Clicked DM page back button")
            else:
                logger.info("Using physical back button for DM page")
                self.driver.press_back()
            random_delay(1, 2)
        else:
            logger.warning("DM input field not found (maybe blocked or different UI)")
            # 可能是“发送请求”按钮，或者其他限制提示
            # 即便没发成功，也需要退回用户主页
            logger.info("Back from DM page (failed)")
            self.driver.press_back()
            random_delay(1, 2)
            
        # 5. 从用户主页返回评论区
        logger.info("Back to comment section")
        
        # 尝试点击“回到评论区”悬浮按钮（如果存在）
        back_to_comment_id = self.config['ui_ids'].get('profile_back_to_comment_btn')
        if back_to_comment_id and self.driver.safe_click(back_to_comment_id, timeout=3):
            logger.info("Clicked 'Back to Comment' button")
        else:
            # 备选：尝试点击 text="回到评论区"
            if self.driver.safe_click("text='回到评论区'", timeout=2):
                 logger.info("Clicked 'Back to Comment' text")
            else:
                # 兜底：物理返回键
                logger.info("Using physical back button")
                self.driver.press_back()
                
        return success
