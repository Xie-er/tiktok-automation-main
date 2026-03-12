import random
from core.actions.base import BaseAction
from utils.logger import logger
from utils.human_sim import random_delay

class ReplyInteraction(BaseAction):
    """
    回复评论交互模块：长按/点击评论 -> 弹出输入框 -> 输入回复 -> 发送
    注意：此模块通常直接在评论列表操作，不需要进主页
    """
    def execute(self, comment_data: dict) -> bool:
        logger.info("Executing ReplyInteraction...")
        
        # 获取评论内容的坐标（点击评论内容通常会触发回复）
        # 这里假设点击 comment_item_text 对应的区域
        # bounds 格式: [left, top, right, bottom]
        
        # 注意：UIParser 提取时需要确保 bounds 准确
        # 这里演示逻辑，实际可能需要针对抖音回复按钮的坐标
        
        # 1. 尝试点击评论内容触发回复框
        # 假设 comment_data 中包含了内容区域的 bounds
        content_bounds = comment_data.get('content_bounds')
        if not content_bounds:
            logger.error("Content bounds not found in comment_data")
            return False
            
        x = (content_bounds[0] + content_bounds[2]) // 2
        y = (content_bounds[1] + content_bounds[3]) // 2
        
        logger.info(f"Clicking comment content to trigger reply...")
        self.driver.d.click(x, y)
        random_delay(1, 2)
        
        success = False
        
        # 2. 查找回复输入框
        # 抖音回复时通常会弹出一个半屏输入框
        input_id = self.config['ui_ids'].get('video_detail_comment_input')
        
        # 尝试通过 ID 查找输入框，或者寻找当前焦点所在的输入框
        input_field = self.driver.d(resourceId=input_id)
        if not input_field.exists(timeout=5):
            # 备选方案：查找任何可编辑的输入框
            input_field = self.driver.d(className="android.widget.EditText")

        if input_field.exists(timeout=2):
            message = random.choice(self.config['strategies']['reply_texts'])
            logger.info(f"Replying: {message}")
            
            if not self.config['limits']['dry_run']:
                # 使用 set_text 模拟输入。对于中文，uiautomator2 会自动处理。
                # 如果用户明确想用“粘贴”动作，set_text 其实是最稳定的“程序化粘贴”。
                input_field.set_text(message)
                random_delay(1, 2)
                
                # 点击发送
                # 方案 1: 尝试回车
                self.driver.d.press("enter")
                
                # 方案 2: 查找发送图标 (通常是一个纸飞机或“发送”文字)
                send_btn = self.driver.d(description="发送") or self.driver.d(text="发送")
                if send_btn.exists(timeout=2):
                    send_btn.click()
                
                logger.info("Reply sent successfully")
            else:
                logger.info(f"Dry run: skip reply '{message}'")
            
            success = True
            random_delay(1, 2)
        else:
            logger.warning("Reply input field not found")
            # 尝试按一次返回键关闭可能打开的半屏
            self.driver.press_back()
            
        return success
