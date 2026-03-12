import os
import sqlite3
import time
from utils.logger import logger

class Storage:
    def __init__(self, db_path=None):
        if db_path is None:
            # 默认路径：当前文件所在目录下的 history.db
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS interaction_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_key TEXT UNIQUE,
                        video_url TEXT,
                        keyword TEXT,
                        action_type TEXT,
                        timestamp REAL
                    )
                ''')
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to init database: {e}")

    def has_interacted(self, user_key):
        """
        检查是否已互动过
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM interaction_log WHERE user_key = ?", (user_key,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"DB error in has_interacted: {e}")
            return False

    def log_interaction(self, user_key, video_url, keyword, action_type="like"):
        """
        记录互动
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO interaction_log (user_key, video_url, keyword, action_type, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_key, video_url, keyword, action_type, time.time()))
                conn.commit()
                logger.info(f"Logged interaction for {user_key}")
        except Exception as e:
            logger.error(f"DB error in log_interaction: {e}")
