import random
from core.actions.base import BaseAction
from utils.logger import logger
from utils.human_sim import random_delay

class CommentInteraction(BaseAction):
    """
    直接评论交互模块：在视频页点击输入框 -> 输入话术 -> 发送
    """
    def execute(self, video_data: dict) -> bool:
        logger.info("Executing CommentInteraction...")
        
        # 1. 查找视频页的评论输入入口
        input_id = self.config['ui_ids'].get('video_detail_comment_input')
        
        # 尝试使用 ID 点击，如果失败尝试使用 className
        input_field = self.driver.d(resourceId=input_id)
        if not input_field.exists(timeout=5):
            logger.warning(f"Primary comment input ID {input_id} not found, trying fallback...")
            input_field = self.driver.d(className="android.widget.EditText")

        if input_field.exists(timeout=5):
            input_field.click()
            random_delay(1, 2)
            message = random.choice(self.config['strategies']['reply_texts'])
            logger.info(f"Posting comment: {message}")
            
            if not self.config['limits']['dry_run']:
                input_field.set_text(message)
                random_delay(1, 2)
                
                # 尝试点击“发送”按钮，抖音常见的发送按钮 ID 或文本
                send_btn = self.driver.d(description="发送") or \
                           self.driver.d(text="发送") or \
                           self.driver.d(resourceId="com.ss.android.ugc.aweme:id/jb5") # 借用 DM 的发送 ID 尝试
                
                if send_btn.exists(timeout=3):
                    logger.info("Clicking explicit 'Send' button")
                    send_btn.click()
                else:
                    logger.info("Send button not found by ID/Text, trying IME action 'send'...")
                    # 尝试发送软键盘的“发送”动作
                    self.driver.d.send_action("send")
                    
                random_delay(1, 2)
                logger.info("Comment post attempt finished")
            else:
                logger.info(f"Dry run: skip posting comment '{message}'")
            return True
        else:
            logger.warning("Video comment input not found (tried ID and EditText)")
            return False
