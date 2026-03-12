from core.actions.base import BaseAction
from utils.logger import logger
from utils.human_sim import random_delay

class LikeInteraction(BaseAction):
    """
    点赞交互模块：点击头像 -> 进主页 -> 点首个作品 -> 点赞
    """
    def execute(self, comment_data: dict = None) -> bool:
        logger.info("Executing LikeInteraction...")
        
        # 如果提供了 comment_data，则去给该用户的第一个视频点赞 (原逻辑)
        if comment_data and 'avatar_bounds' in comment_data:
            bounds = comment_data['avatar_bounds']
            
            # 1. 点击头像
            x = (bounds[0] + bounds[2]) // 2
            y = (bounds[1] + bounds[3]) // 2
            
            logger.info(f"Clicking avatar at {x}, {y}")
            self.driver.d.click(x, y)
            
            random_delay(3, 5) # 等待主页加载
            
            success = False
            
            # 2. 查找并点击第一个作品
            first_cover_id = self.config['ui_ids']['profile_first_video_cover']
            if self.driver.safe_click(first_cover_id):
                logger.info("Entered video detail")
                random_delay(2, 4)
                
                # 3. 执行点赞
                like_btn_id = self.config['ui_ids']['video_detail_like_btn']
                if not self.config['limits']['dry_run']:
                    # 优先尝试选择器，失败则尝试坐标
                    if not self.driver.safe_click(like_btn_id, timeout=5):
                        logger.warning("Like button not found, using coordinate fallback")
                        self.driver.click_percent(0.913, 0.578)
                    logger.info("Liked video")
                else:
                    logger.info("Dry run: matched but skipped like")
                
                success = True
                random_delay(1, 2)
                
                # 4. 返回主页
                self.driver.press_back()
                random_delay(1, 2)
            else:
                logger.warning("Could not find first video (maybe private account)")
                
            # 5. 返回评论区
            self.driver.press_back()
            return success
        else:
            # 如果没有提供 comment_data，则直接给当前视频点赞 (新逻辑)
            logger.info("No comment_data provided, liking the main video...")
            like_btn_id = self.config['ui_ids']['video_detail_like_btn']
            
            if not self.config['limits']['dry_run']:
                # 在视频详情页，直接找点赞按钮
                # 有时候点赞按钮 ID 可能会变，增加一些容错
                if not self.driver.safe_click(like_btn_id, timeout=5):
                    # 备选：尝试点击屏幕右侧偏中上的点赞常用位置
                    logger.warning("Like button ID not found, using coordinate fallback")
                    self.driver.click_percent(0.9, 0.5) 
                logger.info("Liked main video")
            else:
                logger.info("Dry run: skipped liking main video")
            return True
