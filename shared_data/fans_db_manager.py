import os
import sqlite3
from datetime import datetime
from utils.logger import logger

class FansDBManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # 默认路径：E:\tiktok\shared_data\fans.db
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, "shared_data", "fans.db")
        
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """初始化粉丝数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()
        # 创建 fans 表，记录粉丝信息及其主页 Xpath
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                blogger_id TEXT,          -- 所属博主标识 (可以是博主昵称或 ID)
                fan_nickname TEXT,        -- 粉丝昵称
                fan_description TEXT,     -- 粉丝主页简介
                xpath TEXT,               -- 该粉丝在列表中的 Xpath (含昵称和简介)
                status TEXT DEFAULT 'pending', -- 处理状态
                created_at DATETIME,
                updated_at DATETIME,
                UNIQUE(blogger_id, xpath)  -- 同一个博主下的 Xpath 应该是唯一的
            )
        ''')
        conn.commit()
        conn.close()

    def save_fan(self, blogger_id, nickname, description, xpath):
        """保存或更新粉丝信息"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO fans (blogger_id, fan_nickname, fan_description, xpath, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(blogger_id, xpath) DO UPDATE SET
                    fan_nickname = excluded.fan_nickname,
                    fan_description = excluded.fan_description,
                    updated_at = excluded.updated_at
            ''', (blogger_id, nickname, description, xpath, now, now))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"[FansDB] Error saving fan: {e}")
            return False
        finally:
            conn.close()

    def mark_fan_processed(self, blogger_id, xpath, status='done'):
        """标记粉丝为已处理"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE fans SET status = ?, updated_at = ?
                WHERE blogger_id = ? AND xpath = ?
            ''', (status, now, blogger_id, xpath))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"[FansDB] Error updating fan status: {e}")
            return False
        finally:
            conn.close()

    def is_fan_processed(self, blogger_id, xpath):
        """检查粉丝是否已处理过"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT status FROM fans WHERE blogger_id = ? AND xpath = ?', (blogger_id, xpath))
            row = cursor.fetchone()
            return row is not None and row[0] == 'done'
        finally:
            conn.close()
