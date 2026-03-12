import os
import sqlite3
import time
from datetime import datetime
from .db_manager import DBManager

class XHSDatabase(DBManager):
    def __init__(self, db_path=None):
        if db_path is None:
            # 默认路径：shared_data 目录下的 xhs_tasks.db
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xhs_tasks.db")
        super().__init__(db_path)

    def _init_db(self):
        """初始化小红书数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # 小红书任务表结构（目前与 TikTok 保持一致，方便前端共用逻辑，以后可扩展）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                category TEXT,
                status TEXT DEFAULT 'pending',
                dept TEXT DEFAULT 'general',
                like_status TEXT DEFAULT 'pending',
                comment_status TEXT DEFAULT 'pending',
                reply_status TEXT DEFAULT 'pending',
                worker_id TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
        ''')
        
        # 创建统计表（触达客户数量）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hit_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
                dept TEXT,
                hit_count INTEGER DEFAULT 0,
                UNIQUE(date, dept)
            )
        ''')
        conn.commit()
        conn.close()

    def get_hit_stats(self, dept="all", period="day", date=None, start_date=None, end_date=None):
        """
        重写触达客户统计逻辑：一个点赞代表触达一个客户。
        即统计 like_status = 'done' 的任务数量。
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 触达客户 = 点赞任务完成
        where_clause = "WHERE like_status = 'done'"
        params = []
        if dept != "all":
            where_clause += " AND dept = ?"
            params.append(dept)

        try:
            # 使用与 DBManager 一致的日期处理逻辑
            now = datetime.now()
            
            if period == "date" and date:
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at LIKE ?", params + [f"{date}%"])
                return cursor.fetchone()[0] or 0
            
            elif period == "range" and start_date and end_date:
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ? AND updated_at <= ?", params + [f"{start_date} 00:00:00", f"{end_date} 23:59:59"])
                return cursor.fetchone()[0] or 0

            elif period == "day":
                today = now.strftime('%Y-%m-%d')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at LIKE ?", params + [f"{today}%"])
                return cursor.fetchone()[0] or 0
            
            elif period == "week":
                from datetime import timedelta
                # 本周从周一开始
                start_of_week = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_week])
                return cursor.fetchone()[0] or 0
                
            elif period == "month":
                start_of_month = now.strftime('%Y-%m-01')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_month])
                return cursor.fetchone()[0] or 0
                
            elif period == "year":
                start_of_year = now.strftime('%Y-01-01')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_year])
                return cursor.fetchone()[0] or 0
                
            elif period == "all":
                res = {}
                # 今日
                today = now.strftime('%Y-%m-%d')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at LIKE ?", params + [f"{today}%"])
                res['day'] = cursor.fetchone()[0] or 0
                
                # 本周
                from datetime import timedelta
                start_of_week = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_week])
                res['week'] = cursor.fetchone()[0] or 0
                
                # 本月
                start_of_month = now.strftime('%Y-%m-01')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_month])
                res['month'] = cursor.fetchone()[0] or 0
                
                # 本年
                start_of_year = now.strftime('%Y-01-01')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_year])
                res['year'] = cursor.fetchone()[0] or 0
                
                return res
            return 0
        finally:
            conn.close()

    def get_all_stats(self):
        """获取小红书所有部门的统计信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT dept, status, COUNT(*) FROM tasks GROUP BY dept, status")
        rows = cursor.fetchall()
        conn.close()
        
        result = {}
        for dept, status, count in rows:
            if dept not in result:
                result[dept] = {'pending': 0, 'processing': 0, 'done': 0, 'failed': 0}
            result[dept][status] = count
            
        # 确保小红书已知部门都存在
        for d in ['xhs_pet', 'xhs_general', 'general']:
            if d not in result:
                result[d] = {'pending': 0, 'processing': 0, 'done': 0, 'failed': 0}
        return result

# 单例模式导出
xhs_db = XHSDatabase()
