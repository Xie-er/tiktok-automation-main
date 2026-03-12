import os
import sqlite3
import time
from datetime import datetime

try:
    from utils.logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("db_manager")

class DBManager:
    _initialized = False

    def __init__(self, db_path=None):
        if db_path is None:
            # 默认路径：当前文件所在目录下的 tasks.db
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.db")
        self.db_path = db_path
        self.timeout = 20  # 增加超时时间
        if not DBManager._initialized:
            self._init_db()
            DBManager._initialized = True

    def _get_connection(self):
        """获取带 WAL 模式和超时的连接"""
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()
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
                share_token TEXT,
                description TEXT,
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
        
        # 检查是否需要迁移（为旧表添加新列）
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'like_status' not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN like_status TEXT DEFAULT 'pending'")
        if 'comment_status' not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN comment_status TEXT DEFAULT 'pending'")
        if 'reply_status' not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN reply_status TEXT DEFAULT 'pending'")
        if 'dept' not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN dept TEXT DEFAULT 'general'")
        if 'share_token' not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN share_token TEXT")
        if 'description' not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN description TEXT")
            
        conn.commit()
        conn.close()

    def add_hit_count(self, dept="general", count=1):
        """增加触达客户数量（关键词命中统计）"""
        today = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"[DB] Adding hit count: dept={dept}, count={count}, date={today}")
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO hit_stats (date, dept, hit_count)
                VALUES (?, ?, ?)
                ON CONFLICT(date, dept) DO UPDATE SET hit_count = hit_count + ?
            ''', (today, dept, count, count))
            conn.commit()
        except Exception as e:
            print(f"Error adding hit count: {e}")
        finally:
            conn.close()

    def get_hit_stats(self, dept="all", period="day", date=None, start_date=None, end_date=None):
        """获取触达客户统计数据 (period: day, week, month, year, date, range)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now()
        
        where_clause = ""
        params = []
        if dept != "all":
            where_clause = "WHERE dept = ?"
            params.append(dept)

        try:
            if period == "date" and date:
                # 特定日期统计
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date = ?", params + [date])
                return cursor.fetchone()[0] or 0
            
            elif period == "range" and start_date and end_date:
                # 日期范围统计
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date BETWEEN ? AND ?", params + [start_date, end_date])
                return cursor.fetchone()[0] or 0

            elif period == "day":
                # 今日统计
                today = now.strftime('%Y-%m-%d')
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date = ?", params + [today])
                return cursor.fetchone()[0] or 0
            
            elif period == "week":
                # 本周统计 (从周一开始)
                from datetime import timedelta
                start_of_week = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date >= ?", params + [start_of_week])
                return cursor.fetchone()[0] or 0
                
            elif period == "month":
                # 本月统计
                start_of_month = now.strftime('%Y-%m-01')
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date >= ?", params + [start_of_month])
                return cursor.fetchone()[0] or 0
                
            elif period == "year":
                # 本年统计
                start_of_year = now.strftime('%Y-01-01')
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date >= ?", params + [start_of_year])
                return cursor.fetchone()[0] or 0
                
            elif period == "all":
                # 同时返回所有周期的统计
                res = {}
                # 今日
                today = now.strftime('%Y-%m-%d')
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date = ?", params + [today])
                res['day'] = cursor.fetchone()[0] or 0
                
                # 本周
                from datetime import timedelta
                start_of_week = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date >= ?", params + [start_of_week])
                res['week'] = cursor.fetchone()[0] or 0
                
                # 本月
                start_of_month = now.strftime('%Y-%m-01')
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date >= ?", params + [start_of_month])
                res['month'] = cursor.fetchone()[0] or 0
                
                # 本年
                start_of_year = now.strftime('%Y-01-01')
                cursor.execute(f"SELECT SUM(hit_count) FROM hit_stats {where_clause} {'AND' if params else 'WHERE'} date >= ?", params + [start_of_year])
                res['year'] = cursor.fetchone()[0] or 0
                
                return res
                
            return 0
        finally:
            conn.close()

    def get_task_stats(self, dept="all", period="day", date=None, start_date=None, end_date=None):
        """获取已完成视频任务统计数据 (period: day, week, month, year, date, range)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now()
        
        where_clause = "WHERE status = 'done'"
        params = []
        if dept != "all":
            where_clause += " AND dept = ?"
            params.append(dept)

        try:
            if period == "date" and date:
                # 特定日期统计
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at LIKE ?", params + [f"{date}%"])
                return cursor.fetchone()[0] or 0
            
            elif period == "range" and start_date and end_date:
                # 日期范围统计 (注意 tasks 表的 updated_at 是 DATETIME 格式)
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ? AND updated_at <= ?", params + [f"{start_date} 00:00:00", f"{end_date} 23:59:59"])
                return cursor.fetchone()[0] or 0

            elif period == "day":
                today = now.strftime('%Y-%m-%d')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at LIKE ?", params + [f"{today}%"])
                return cursor.fetchone()[0] or 0
            
            elif period == "week":
                from datetime import timedelta
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
                today = now.strftime('%Y-%m-%d')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at LIKE ?", params + [f"{today}%"])
                res['day'] = cursor.fetchone()[0] or 0
                
                from datetime import timedelta
                start_of_week = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_week])
                res['week'] = cursor.fetchone()[0] or 0
                
                start_of_month = now.strftime('%Y-%m-01')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_month])
                res['month'] = cursor.fetchone()[0] or 0
                
                start_of_year = now.strftime('%Y-01-01')
                cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause} AND updated_at >= ?", params + [start_of_year])
                res['year'] = cursor.fetchone()[0] or 0
                
                return res
                
            return 0
        finally:
            conn.close()

    def add_task(self, url, category="default", dept="general", share_token=None, description=None):
        """发布端调用：添加新任务，如果 URL、share_token 或 description 已存在则忽略"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 1. 如果提供了 share_token，先检查库中是否已存在
            if share_token:
                cursor.execute('SELECT id FROM tasks WHERE share_token = ?', (share_token,))
                if cursor.fetchone():
                    logger.info(f"[DB] 检测到重复 share_token: {share_token}, 跳过入库")
                    return False
            
            # 2. 如果提供了 description，检查库中是否已存在 (解决不同账号 share_token 不一致的问题)
            if description:
                cursor.execute('SELECT id FROM tasks WHERE description = ?', (description,))
                if cursor.fetchone():
                    logger.info(f"[DB] 检测到重复文案内容, 跳过入库")
                    return False
            
            # 3. 尝试插入新任务 (URL 唯一约束也会起作用)
            cursor.execute('''
                INSERT INTO tasks (url, category, dept, share_token, description, status, like_status, comment_status, reply_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (url, category, dept, share_token, description, 'pending', 'pending', 'pending', 'pending', now, now))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # URL 已存在
            return False
        except Exception as e:
            logger.error(f"[DB] 添加任务出错: {e}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()

    def get_pending_task(self, worker_id, mode=None, dept=None):
        """执行端获取待处理任务，优先处理该 worker 之前未完成的任务"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # 开启立即事务，防止并发冲突
            cursor.execute("BEGIN IMMEDIATE")
            
            # 基础条件
            conditions = []
            params = []

            if dept:
                conditions.append("dept = ?")
                params.append(dept)

            # 宠物部门特殊处理：不关心子任务状态，只关心总状态
            if dept == 'pet':
                row = self._get_generic_pending(cursor, conditions, params, worker_id)
            elif dept == 'uav':
                # 无人机部门：严格按照 ID 顺序处理 status='pending' 的任务
                uav_conditions = conditions + ["status = 'pending'"]
                cursor.execute(f'''
                    SELECT id, url FROM tasks 
                    WHERE {" AND ".join(uav_conditions)}
                    ORDER BY id ASC LIMIT 1
                ''', params)
                row = cursor.fetchone()
            elif mode:
                # 提取实际的模式名
                actual_mode = mode
                if "_" in mode:
                    parts = mode.split("_")
                    if parts[-1] in ['like', 'comment', 'reply', 'translator']:
                        actual_mode = parts[-1]
                
                if actual_mode in ['like', 'comment', 'reply', 'translator']:
                    target_col_mode = "reply" if actual_mode == "translator" else actual_mode
                    status_col = f"{target_col_mode}_status"
                    
                    # 1. 优先找当前 worker 正在处理 (processing) 且该子任务还是 pending 的
                    current_worker_conditions = conditions + ["worker_id = ?", "status = 'processing'", f"{status_col} = 'pending'"]
                    current_worker_params = params + [worker_id]
                    
                    cursor.execute(f'''
                        SELECT id, url FROM tasks 
                        WHERE {" AND ".join(current_worker_conditions)}
                        ORDER BY id ASC LIMIT 1
                    ''', current_worker_params)
                    row = cursor.fetchone()
                    
                    # 2. 如果没找到，找该子任务状态是 pending 的任务
                    if not row:
                        pending_conditions = conditions + [f"{status_col} = 'pending'"]
                        cursor.execute(f'''
                            SELECT id, url FROM tasks 
                            WHERE {" AND ".join(pending_conditions)}
                            ORDER BY id ASC LIMIT 1
                        ''', params)
                        row = cursor.fetchone()
                else:
                    row = self._get_generic_pending(cursor, conditions, params, worker_id)
            else:
                row = self._get_generic_pending(cursor, conditions, params, worker_id)
            
            if row:
                task_id, url = row
                cursor.execute('''
                    UPDATE tasks SET status = 'processing', worker_id = ?, updated_at = ?
                    WHERE id = ?
                ''', (worker_id, now, task_id))
                conn.commit()
                return url
            
            conn.commit()
            return None
        except Exception as e:
            print(f"Error getting pending task: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def _get_generic_pending(self, cursor, conditions, params, worker_id):
        """通用的待处理任务获取逻辑"""
        # 1. 优先找当前 worker 正在处理 (processing)
        current_worker_conditions = conditions + ["worker_id = ?", "status = 'processing'"]
        current_worker_params = params + [worker_id]
        cursor.execute(f'''
            SELECT id, url FROM tasks 
            WHERE {" AND ".join(current_worker_conditions)}
            ORDER BY id ASC LIMIT 1
        ''', current_worker_params)
        row = cursor.fetchone()
        
        if not row:
            pending_conditions = conditions + ["status = 'pending'"]
            cursor.execute(f'''
                SELECT id, url FROM tasks 
                WHERE {" AND ".join(pending_conditions)}
                ORDER BY id ASC LIMIT 1
            ''', params)
            row = cursor.fetchone()
        return row

    def report_status(self, url, status, mode=None):
        """执行端汇报任务状态"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # 首先获取任务的部门信息
            cursor.execute("SELECT dept FROM tasks WHERE url = ?", (url,))
            res = cursor.fetchone()
            dept = res[0] if res else 'general'

            # 统一处理模式名
            actual_mode = mode
            if mode and "_" in mode:
                parts = mode.split("_")
                if parts[-1] in ['like', 'comment', 'reply', 'translator']:
                    actual_mode = parts[-1]
            
            # 如果是宠物部门，状态汇报直接决定总状态
            if dept == 'pet':
                cursor.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE url = ?", (status, now, url))
                # 同步更新子状态，防止前端显示不一致
                cursor.execute("UPDATE tasks SET like_status = ?, comment_status = ?, reply_status = ? WHERE url = ?", 
                             (status, status, status, url))
            elif actual_mode in ['like', 'comment', 'reply', 'translator']:
                target_col_mode = "reply" if actual_mode == "translator" else actual_mode
                status_col = f"{target_col_mode}_status"
                cursor.execute(f"UPDATE tasks SET {status_col} = ?, updated_at = ? WHERE url = ?", (status, now, url))
                
                # 重新计算总状态 (非宠物部门保留聚合逻辑)
                cursor.execute("SELECT like_status, comment_status, reply_status FROM tasks WHERE url = ?", (url,))
                row = cursor.fetchone()
                if row:
                    l, c, r = row
                    if l == 'done' and c == 'done' and r == 'done':
                        new_total_status = 'done'
                    elif l == 'failed' or c == 'failed' or r == 'failed':
                        new_total_status = 'failed'
                    elif l != 'pending' or c != 'pending' or r != 'pending':
                        new_total_status = 'processing'
                    else:
                        new_total_status = 'pending'
                    cursor.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE url = ?", (new_total_status, now, url))
            else:
                cursor.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE url = ?", (status, now, url))
            conn.commit()
        finally:
            conn.close()

    def get_task_status(self, url):
        """发布端调用：获取任务状态以进行同步"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT status FROM tasks WHERE url = ?', (url,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def get_all_stats(self):
        """获取所有部门的统计信息"""
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
            
        # 确保所有已知部门都存在
        for d in ['pet', 'general', 'bci', 'uav']:
            if d not in result:
                result[d] = {'pending': 0, 'processing': 0, 'done': 0, 'failed': 0}
        return result

if __name__ == "__main__":
    # 测试代码
    db = DBManager()
    print("Database initialized.")
