import sys
import os

# 将项目根目录添加到 python 路径，确保可以导入 shared_data
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import sqlite3
import yaml
import adbutils
from typing import List, Dict
import subprocess
import signal
from typing import List, Dict, Optional
from pydantic import BaseModel
from fastapi import APIRouter

app = FastAPI(title="TikTok & XHS Automation API")

# --- 小红书后端路由 ---
xhs_router = APIRouter(prefix="/xhs", tags=["小红书"])

@xhs_router.get("/stats/history")
def get_xhs_history_stats(days: int = 7):
    """获取小红书历史统计数据（趋势图）"""
    try:
        from datetime import datetime, timedelta
        conn = sqlite3.connect(xhs_db.db_path)
        cursor = conn.cursor()
        
        trend = []
        now = datetime.now()
        for i in range(days-1, -1, -1):
            day = (now - timedelta(days=i)).strftime('%Y-%m-%d')
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE updated_at LIKE ? AND status='done'", (f"{day}%",))
            done_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE updated_at LIKE ?", (f"{day}%",))
            total_count = cursor.fetchone()[0]
            trend.append({"day": day, "done": done_count, "total": total_count})
        
        # 计算各项成功率
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE like_status='done'")
        like_done = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE comment_status='done'")
        comment_done = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE reply_status='done'")
        reply_done = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks")
        total = max(cursor.fetchone()[0], 1)
        
        conn.close()
        return {
            "trend": trend,
            "rates": {
                "like": round(like_done / total * 100, 1),
                "comment": round(comment_done / total * 100, 1),
                "reply": round(reply_done / total * 100, 1)
            }
        }
    except Exception as e:
        return {"trend": [], "rates": {"like": 0, "comment": 0, "reply": 0}}

from shared_data.xhs_db import xhs_db

@xhs_router.get("/stats")
def get_xhs_stats(dept: Optional[str] = None):
    """获取小红书任务统计信息"""
    try:
        # 严格使用 xhs_db，确保不与 TikTok 混淆
        stats = xhs_db.get_all_stats()
        
        # 如果指定了部门，返回该部门的统计
        if dept and dept != 'all':
            if dept in stats:
                res = stats[dept]
                res['total'] = sum(res.values())
                return res
            else:
                return {'pending': 0, 'processing': 0, 'done': 0, 'failed': 0, 'total': 0}
        
        # 如果没有指定部门或指定为 all，返回汇总统计
        total_stats = {'pending': 0, 'processing': 0, 'done': 0, 'failed': 0}
        for d_stats in stats.values():
            for status, count in d_stats.items():
                if status in total_stats:
                    total_stats[status] += count
        total_stats['total'] = sum(total_stats.values())
        return total_stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@xhs_router.get("/stats/all")
def get_xhs_all_stats():
    """获取小红书所有部门的详细统计信息"""
    try:
        # 严格使用 xhs_db
        return xhs_db.get_all_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@xhs_router.get("/tasks/recent")
def get_xhs_recent_tasks(dept: Optional[str] = None):
    """获取小红书最近任务"""
    try:
        conn = sqlite3.connect(xhs_db.db_path)
        cursor = conn.cursor()
        if dept:
            cursor.execute("SELECT id, url, status, like_status, comment_status, reply_status, worker_id, updated_at, dept FROM tasks WHERE dept = ? ORDER BY id DESC LIMIT 500", (dept,))
        else:
            cursor.execute("SELECT id, url, status, like_status, comment_status, reply_status, worker_id, updated_at, dept FROM tasks ORDER BY id DESC LIMIT 500")
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                "id": row[0], "url": row[1], "status": row[2],
                "like_status": row[3], "comment_status": row[4], "reply_status": row[5],
                "worker_id": row[6], "updated_at": row[7], "dept": row[8]
            })
        conn.close()
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 将小红书路由注册到主应用
app.include_router(xhs_router)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 进程管理
class ProcessManager:
    def __init__(self):
        self.scout_process: Optional[subprocess.Popen] = None
        self.scout_dept: str = "none"
        # 存储各部门的 grabber 进程
        self.grabber_processes: Dict[str, List[subprocess.Popen]] = {
            "general": [],
            "pet": [],
            "bci": [],
            "uav": []
        }
        self.log_dir = os.path.join(os.path.dirname(__file__), "proc_logs")
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def start_grabber(self, mode: str, dept: str = "general"):
        # 检查该部门是否已有运行中的进程
        if dept in self.grabber_processes and any(p.poll() is None for p in self.grabber_processes[dept]):
            return False
        
        self.grabber_processes[dept] = []
        
        # 确定运行目录和命令
        if dept == "pet":
            cwd = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pet_grabber")
            log_prefix = "pet_grabber"
        else:
            cwd = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tiktokgrabber")
            log_prefix = f"{dept}_grabber"
            
        log_file = open(os.path.join(self.log_dir, f"{log_prefix}_{mode}.log"), "wb")
        cmd = [sys.executable, "main.py", mode, "--multi", "--dept", dept]
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        p = subprocess.Popen(
            cmd, 
            cwd=cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            bufsize=1,
            env=env
        )
        self.grabber_processes[dept].append(p)
        return True

    def stop_grabber(self, dept: str = "general"):
        count = 0
        if dept in self.grabber_processes:
            for p in self.grabber_processes[dept]:
                if p.poll() is None:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                    count += 1
            self.grabber_processes[dept] = []
        return count > 0

    def start_scout(self, min_stay: int, max_stay: int, dept: str = "general", keywords: Optional[List[str]] = None):
        if self.scout_process and self.scout_process.poll() is None:
            return False
        
        # 更新配置
        with open(SCOUT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        config['crawler']['min_video_stay'] = min_stay
        config['crawler']['max_video_stay'] = max_stay
        
        # 如果传入了关键词列表，更新配置
        if keywords:
            # 如果只有一个关键词，也存入旧的 keyword 字段保持兼容
            if len(keywords) > 0:
                config['search']['keyword'] = keywords[0]
            config['search']['keywords'] = keywords
        
        with open(SCOUT_CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, allow_unicode=True)
            
        # 启动进程并重定向日志
        log_file = open(os.path.join(self.log_dir, "scout_stdout.log"), "wb")
        scout_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tiktok_scout")
        
        # 强制设置子进程的编码环境变量为 UTF-8
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        # 增加 --dept 参数
        cmd = [sys.executable, "main.py", "--dept", dept]
        print(f"Starting Scout with command: {' '.join(cmd)}")
        self.scout_process = subprocess.Popen(
            cmd, 
            cwd=scout_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            bufsize=1,
            env=env
        )
        self.scout_dept = dept
        return True

    def stop_scout(self):
        if self.scout_process and self.scout_process.poll() is None:
            # 在 Windows 上使用 taskkill 确保杀死整个进程树
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.scout_process.pid)], capture_output=True)
            self.scout_process = None
            self.scout_dept = "none"
            return True
        return False

    def get_status(self):
        return {
            "scout_running": self.scout_process is not None and self.scout_process.poll() is None,
            "scout_dept": self.scout_dept if self.scout_process and self.scout_process.poll() is None else "none",
            "grabber_running": any(p.poll() is None for p in self.grabber_processes["general"]) if "general" in self.grabber_processes else False,
            "pet_grabber_running": any(p.poll() is None for p in self.grabber_processes["pet"]) if "pet" in self.grabber_processes else False,
            "bci_grabber_running": any(p.poll() is None for p in self.grabber_processes["bci"]) if "bci" in self.grabber_processes else False,
            "uav_grabber_running": any(p.poll() is None for p in self.grabber_processes["uav"]) if "uav" in self.grabber_processes else False
        }

    def get_logs(self, target: str):
        # target 可以是 scout, general, pet, bci, uav
        if target == "scout":
            path = os.path.join(self.log_dir, "scout_stdout.log")
        else:
            # 对于 grabbers，寻找该部门最近更新的日志
            log_prefix = f"{target}_grabber"
            log_files = [f for f in os.listdir(self.log_dir) if f.startswith(log_prefix) and f.endswith(".log")]
            if not log_files:
                return f"暂无 {target} 部门运行日志"
            latest_log = max(log_files, key=lambda f: os.path.getmtime(os.path.join(self.log_dir, f)))
            path = os.path.join(self.log_dir, latest_log)

        if os.path.exists(path):
            try:
                # 使用二进制读取最后 8000 字节
                with open(path, 'rb') as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    offset = max(0, size - 8000)
                    f.seek(offset)
                    raw_bytes = f.read()
                    
                    # 尝试解码。如果是从中间截断的，ignore 掉不完整的字符
                    content = raw_bytes.decode('utf-8', errors='ignore')
                    
                    # 如果不是从头开始读的，第一行很可能是残缺的，去掉它以保证日志整齐
                    if offset > 0:
                        lines = content.split('\n')
                        if len(lines) > 1:
                            content = '\n'.join(lines[1:])
                    
                    # 转换为用户友好的中文日志
                    return self._translate_logs(content)
            except Exception as e:
                return f"读取日志出错: {str(e)}"
        return "未找到日志文件"

    def _translate_logs(self, raw_content: str) -> str:
        """将技术日志转换为用户友好的中文日志"""
        lines = raw_content.split('\n')
        friendly_lines = []
        
        # 翻译映射表
        translation_map = {
            "Processing video (like):": "正在处理视频 (点赞)：",
            "Processing video (comment):": "正在处理视频 (评论)：",
            "Processing video (reply):": "正在处理视频 (回复)：",
            "Pet Department processing video:": "🐾 宠物部门正在处理视频：",
            "Pet Task finished:": "✅ 宠物部门任务执行成功：",
            "Processing video (dm):": "正在处理视频 (私信)：",
            "Processing video:": "正在处理视频：",
            "Task finished": "✅ 任务执行成功",
            "Failed to execute": "❌ 执行失败",
            "Start processing comments...": "🔍 开始分析评论区...",
            "Keyword matched:": "🎯 触达客户：",
            "触达客户：": "🎯 触达客户：",
            "Found": "当前屏幕发现",
            "comments on screen": "条评论",
            "Reached bottom of comments": "📍 已到达评论区底部",
            "User already interacted": "⏭️ 该用户已互动过，跳过",
            "Worker": "设备",
            "started, waiting for tasks...": "已就绪，正在等待任务...",
            "No pending tasks, sleeping...": "😴 暂无待处理任务，休息中...",
            "App": "应用",
            "started": "已启动",
            "stopped": "已停止",
            "Pressed Back": "🔙 模拟返回键",
            "Searching for:": "🔎 正在搜索关键词：",
            "Video collected:": "📥 成功采集视频：",
            "Back from DM page": "🔙 从私信页返回",
            "Clicked": "已点击",
            "button": "按钮",
            "Using physical back button": "使用物理返回键",
            "Error processing video": "🚫 处理视频时出错",
            "Dry run: skip sending DM": "🧪 测试模式：跳过发送私信",
            "Logged interaction for": "📝 已记录互动：",
            "Navigating to:": "🚀 正在跳转至：",
            "Found search input": "找到搜索框",
            "Inputting keyword": "正在输入关键词",
            "Waiting for results": "等待搜索结果",
            "Checking video:": "正在检查视频：",
            "Stayed for": "停留时长：",
            "seconds": "秒",
            "Next video": "切换下一个视频"
        }

        import re
        # 匹配 loguru 默认格式: 2026-01-23 10:15:30 | INFO     | name:func:line - message
        log_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s\|\s(\w+)\s+\|.*?\s-\s(.*)')

        for line in lines:
            if not line.strip():
                continue
                
            match = log_pattern.search(line)
            if match:
                timestamp, level, message = match.groups()
                # 简化时间显示，只保留时分秒
                time_short = timestamp.split(' ')[1]
                
                # 转换等级
                level_cn = {
                    "INFO": "信息",
                    "SUCCESS": "成功",
                    "ERROR": "错误",
                    "WARNING": "警告",
                    "DEBUG": "调试"
                }.get(level, level)

                # 翻译消息内容
                friendly_msg = message
                for eng, chn in translation_map.items():
                    friendly_msg = friendly_msg.replace(eng, chn)
                
                friendly_lines.append(f"{time_short} [{level_cn}] {friendly_msg}")
            else:
                # 如果不匹配标准格式，尝试直接翻译整行
                friendly_msg = line
                for eng, chn in translation_map.items():
                    friendly_msg = friendly_msg.replace(eng, chn)
                friendly_lines.append(friendly_msg)

        return '\n'.join(friendly_lines)

pm = ProcessManager()

class ScoutStartRequest(BaseModel):
    min_stay: int = 15
    max_stay: int = 20
    dept: str = "general"
    keywords: Optional[List[str]] = None

class GrabberStartRequest(BaseModel):
    mode: str

class WirelessConnectRequest(BaseModel):
    ip: str
    port: int = 5555

class WirelessPairRequest(BaseModel):
    ip: str
    port: int
    code: str

class EnableTcpIpRequest(BaseModel):
    serial: str

@app.get("/processes/status")
def get_process_status():
    return pm.get_status()

@app.get("/processes/logs/{target}")
def get_process_logs(target: str):
    return {"logs": pm.get_logs(target)}

@app.post("/scout/start")
def start_scout(req: ScoutStartRequest):
    if pm.start_scout(req.min_stay, req.max_stay, req.dept, req.keywords):
        return {"status": "started"}
    return {"status": "already running"}

@app.post("/scout/stop")
def stop_scout():
    if pm.stop_scout():
        return {"status": "stopped"}
    return {"status": "not running"}

@app.post("/grabber/start")
def start_grabber(req: GrabberStartRequest, dept: str = "general"):
    if pm.start_grabber(req.mode, dept):
        return {"status": "started"}
    return {"status": "already running"}

@app.post("/grabber/stop")
def stop_grabber(dept: str = "general"):
    if pm.stop_grabber(dept):
        return {"status": "stopped"}
    return {"status": "not running"}

@app.post("/pet_grabber/start")
def start_pet_grabber(req: GrabberStartRequest):
    if pm.start_grabber(req.mode, "pet"):
        return {"status": "started"}
    return {"status": "already running"}

@app.post("/pet_grabber/stop")
def stop_pet_grabber():
    if pm.stop_grabber("pet"):
        return {"status": "stopped"}
    return {"status": "not running"}

PET_GRABBER_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pet_grabber", "config", "settings.yaml")

@app.get("/config/pet_grabber")
def get_pet_grabber_config():
    if not os.path.exists(PET_GRABBER_CONFIG_PATH):
        return {"error": "Config not found"}
    with open(PET_GRABBER_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

class ConfigUpdate(BaseModel):
    data: Dict

@app.post("/config/pet_grabber")
def update_pet_grabber_config(req: ConfigUpdate):
    if not os.path.exists(PET_GRABBER_CONFIG_PATH):
        return {"error": "Config not found"}
    
    with open(PET_GRABBER_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 合并数据
    if 'pet_translator_workflow' in req.data:
        if 'pet_translator_workflow' not in config:
            config['pet_translator_workflow'] = {}
        config['pet_translator_workflow'].update(req.data['pet_translator_workflow'])
    
    # 显式支持 ui_ids 的更新
    if 'ui_ids' in req.data:
        if 'ui_ids' not in config:
            config['ui_ids'] = {}
        config['ui_ids'].update(req.data['ui_ids'])
    
    with open(PET_GRABBER_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)
    return {"status": "updated"}

# 挂载静态文件目录
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# 现有的 API ...

class RoleUpdate(BaseModel):
    serial: str
    role: str

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared_data", "tasks.db")
CORPUS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared_data", "corpus.yaml")
SCOUT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tiktok_scout", "config", "scout_settings.yaml")
GRABBER_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tiktokgrabber", "config", "settings.yaml")

@app.get("/stats")
def get_stats(dept: Optional[str] = None):
    """获取任务统计信息，可选按部门过滤"""
    try:
        from shared_data.db_manager import DBManager
        db = DBManager(DB_PATH)
        conn = db._get_connection()
        cursor = conn.cursor()
        if dept:
            cursor.execute("SELECT status, COUNT(*) FROM tasks WHERE dept = ? GROUP BY status", (dept,))
        else:
            cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        stats = dict(cursor.fetchall())
        conn.close()
        
        # 确保所有状态都有值并计算总数
        total = 0
        for status in ['pending', 'processing', 'done', 'failed']:
            if status not in stats:
                stats[status] = 0
            total += stats[status]
        
        stats['total'] = total
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats/all")
def get_all_stats():
    """获取所有部门的任务统计信息"""
    try:
        from shared_data.db_manager import DBManager
        db = DBManager(DB_PATH)
        return db.get_all_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats/hit")
def get_hit_stats(dept: str = "all", period: str = "day", date: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """获取‘触达客户数量’统计"""
    try:
        from shared_data.db_manager import DBManager
        db = DBManager(DB_PATH)
        return db.get_hit_stats(dept=dept, period=period, date=date, start_date=start_date, end_date=end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats/tasks")
def get_task_execution_stats(dept: str = "all", period: str = "day", date: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """获取‘已执行视频任务数量’统计"""
    try:
        from shared_data.db_manager import DBManager
        db = DBManager(DB_PATH)
        return db.get_task_stats(dept=dept, period=period, date=date, start_date=start_date, end_date=end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/set_role")
async def set_device_role(update: RoleUpdate):
    """设置设备角色 (Scout 或 Grabber)"""
    try:
        if update.role == "Scout":
            # 读取现有配置
            config = {}
            if os.path.exists(SCOUT_CONFIG_PATH):
                with open(SCOUT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            
            # 更新 serial
            if 'device' not in config:
                config['device'] = {}
            config['device']['serial'] = update.serial
            
            # 写回文件
            with open(SCOUT_CONFIG_PATH, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True)
                
            return {"status": "success", "message": f"设备 {update.serial} 已设为采集端"}
        else:
            # 如果要把当前 Scout 设为 Grabber，需要清除配置中的 serial
            if os.path.exists(SCOUT_CONFIG_PATH):
                with open(SCOUT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                
                if config.get('device', {}).get('serial') == update.serial:
                    if 'device' in config:
                        config['device']['serial'] = ""
                    with open(SCOUT_CONFIG_PATH, 'w', encoding='utf-8') as f:
                        yaml.safe_dump(config, f, allow_unicode=True)
            
            return {"status": "success", "message": f"设备 {update.serial} 已设为执行端"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks/recent")
def get_recent_tasks(dept: Optional[str] = None):
    """获取最近的任务，可选按部门过滤"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if dept:
            cursor.execute("SELECT id, url, status, like_status, comment_status, reply_status, worker_id, updated_at, dept FROM tasks WHERE dept = ? ORDER BY id DESC LIMIT 500", (dept,))
        else:
            cursor.execute("SELECT id, url, status, like_status, comment_status, reply_status, worker_id, updated_at, dept FROM tasks ORDER BY id DESC LIMIT 500")
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                "id": row[0],
                "url": row[1],
                "status": row[2],
                "like_status": row[3],
                "comment_status": row[4],
                "reply_status": row[5],
                "worker_id": row[6],
                "updated_at": row[7],
                "dept": row[8]
            })
        conn.close()
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BatchDMRequest(BaseModel):
    task_ids: List[int]

@app.post("/tasks/batch_dm")
def batch_dm(req: BatchDMRequest):
    """一键私信选中的客户"""
    try:
        if pm.start_grabber("dm"):
            return {"status": "started", "message": f"已针对 {len(req.task_ids)} 个任务启动私信流程"}
        return {"status": "already running"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/{task_id}/reset")
def reset_task(task_id: int):
    """重置单个任务状态为 pending"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tasks 
            SET status = 'pending', 
                like_status = CASE WHEN like_status = 'failed' THEN 'pending' ELSE like_status END,
                comment_status = CASE WHEN comment_status = 'failed' THEN 'pending' ELSE comment_status END,
                reply_status = CASE WHEN reply_status = 'failed' THEN 'pending' ELSE reply_status END,
                worker_id = NULL,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
        ''', (task_id,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"任务 #{task_id} 已重置"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tasks/batch_reset")
def batch_reset_tasks(req: BatchDMRequest):
    """批量重置任务状态为 pending"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(req.task_ids))
        cursor.execute(f'''
            UPDATE tasks 
            SET status = 'pending', 
                like_status = 'pending', 
                comment_status = 'pending', 
                reply_status = 'pending',
                worker_id = NULL,
                updated_at = datetime('now', 'localtime')
            WHERE id IN ({placeholders})
        ''', req.task_ids)
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"已重置 {len(req.task_ids)} 个任务"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 语料库模型
class CorpusScene(BaseModel):
    name: str
    texts: List[str]

class CorpusData(BaseModel):
    dm: List[CorpusScene]
    comment: List[CorpusScene]
    reply: List[CorpusScene]

def get_default_corpus():
    return {
        "dm": [
            {"name": "产品咨询", "texts": ["亲，看到您对我们的产品感兴趣，请问有什么可以帮您的？", "您好！这是您咨询的产品详细资料，请查收。"]},
            {"name": "合作邀请", "texts": ["您好，看了您的主页觉得您的风格非常契合我们品牌，希望能有机会合作！", "Hi，我们是XX品牌方，想邀请您参与我们的新品测评。"]}
        ],
        "comment": [
            {"name": "常规互动", "texts": ["非常有见地的观点！", "感谢分享，学到了！", "这个视频拍得真棒，支持一下！"]}
        ],
        "reply": [
            {"name": "统一回复", "texts": ["感谢关注，私信已发，请查收~", "回复慢了请见谅，详细信息可以看我主页哦。"]}
        ]
    }

@app.get("/corpus")
def get_corpus():
    """获取所有语料场景"""
    # 确保目录存在
    os.makedirs(os.path.dirname(CORPUS_PATH), exist_ok=True)
    
    if not os.path.exists(CORPUS_PATH):
        return get_default_corpus()
    try:
        with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                return get_default_corpus()
            # 确保包含所有必要的键
            for key in ["dm", "comment", "reply"]:
                if key not in data:
                    data[key] = get_default_corpus().get(key, [])
            return data
    except Exception as e:
        print(f"Error reading corpus: {e}")
        return get_default_corpus()

@app.post("/corpus")
def save_corpus(data: CorpusData):
    """保存语料库"""
    try:
        os.makedirs(os.path.dirname(CORPUS_PATH), exist_ok=True)
        with open(CORPUS_PATH, 'w', encoding='utf-8') as f:
            # 使用 dict() 转换 Pydantic 模型，确保结构正确
            yaml.safe_dump(data.dict(), f, allow_unicode=True)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/devices")
def get_devices():
    """获取连接的设备列表"""
    try:
        # 获取 Scout 序列号用于标记
        scout_serial = ""
        if os.path.exists(SCOUT_CONFIG_PATH):
            with open(SCOUT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                scout_config = yaml.safe_load(f)
                scout_serial = scout_config.get('device', {}).get('serial', "")

        adb = adbutils.adb
        devices = []
        for d in adb.device_list():
            try:
                # 这里的 status 可能是 'device', 'offline', 'unauthorized', 'disconnect'
                state = "online"
                try:
                    state = "online" if d.get_state() == "device" else d.get_state()
                except:
                    state = "unknown"

                role = "Scout" if d.serial == scout_serial else "Grabber"
                
                # 获取 IP 地址
                ip = ""
                if ":" in d.serial:
                    ip = d.serial.split(":")[0]
                else:
                    try:
                        ip = d.wlan_ip()
                    except:
                        ip = "Unknown"

                devices.append({
                    "serial": d.serial,
                    "status": state,
                    "role": role,
                    "ip": ip,
                    "info": str(d.prop.model) if hasattr(d, 'prop') else "Unknown"
                })
            except Exception as device_err:
                print(f"Error processing device {d.serial}: {device_err}")
                continue
        return devices
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/devices/enable_tcpip")
def enable_tcpip(req: EnableTcpIpRequest):
    """通过 USB 开启设备的 5555 TCP 端口，以便之后进行无线连接"""
    try:
        adb_path = adbutils.adb_path()
        # 执行 adb -s <serial> tcpip 5555
        result = subprocess.run([adb_path, "-s", req.serial, "tcpip", "5555"], capture_output=True, text=True)
        if result.returncode == 0:
            return {"status": "success", "message": f"设备 {req.serial} 已开启 5555 端口。你现在可以拔掉 USB 线，并使用无线连接功能了。"}
        else:
            return {"status": "failed", "message": result.stderr or "开启失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"开启 TCP 模式出错: {str(e)}")

@app.post("/devices/restart_adb")
def restart_adb():
    """重启 ADB 服务"""
    try:
        adb_path = adbutils.adb_path()
        subprocess.run([adb_path, "kill-server"], check=True)
        subprocess.run([adb_path, "start-server"], check=True)
        return {"status": "success", "message": "ADB 服务已成功重启"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重启 ADB 失败: {str(e)}")

@app.post("/devices/connect_wireless")
def connect_wireless(req: WirelessConnectRequest):
    """通过无线方式连接 ADB 设备"""
    try:
        adb_path = adbutils.adb_path()
        target = f"{req.ip}:{req.port}"
        # 执行 adb connect 命令
        result = subprocess.run([adb_path, "connect", target], capture_output=True, text=True)
        
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        if "connected to" in stdout.lower():
            return {"status": "success", "message": f"成功连接到设备 {target}"}
        else:
            # 如果连接失败，尝试给出更具体的建议
            msg = stdout or stderr or "连接被拒绝"
            if "refused" in msg.lower():
                msg = "连接被拒绝。请确保手机上的“无线调试”已开启，且 IP 和端口正确。"
            elif "timeout" in msg.lower():
                msg = "连接超时。请检查手机和电脑是否在同一 Wi-Fi 下。"
            
            return {"status": "failed", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无线连接出错: {str(e)}")

@app.post("/devices/pair_wireless")
def pair_wireless(req: WirelessPairRequest):
    """通过配对码配对无线设备"""
    try:
        adb_path = adbutils.adb_path()
        target = f"{req.ip}:{req.port}"
        # 执行 adb pair 命令
        result = subprocess.run([adb_path, "pair", target, req.code], capture_output=True, text=True)
        
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        if "successfully paired" in stdout.lower() or "successfully paired" in stderr.lower():
            return {"status": "success", "message": f"成功配对设备 {target}，现在可以进行无线连接了。"}
        else:
            return {"status": "failed", "message": stdout or stderr or "配对失败，请检查配对码是否正确。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配对出错: {str(e)}")

@app.get("/config/{target}")
def get_config(target: str):
    """获取配置信息 (scout 或 grabber)"""
    path = SCOUT_CONFIG_PATH if target == "scout" else GRABBER_CONFIG_PATH
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Config file not found")
    
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

@app.post("/config/{target}")
def update_config(target: str, req: ConfigUpdate):
    """更新配置信息"""
    path = SCOUT_CONFIG_PATH if target == "scout" else GRABBER_CONFIG_PATH
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Config file not found")
    
    try:
        # 先读取现有配置
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 深度合并或简单更新
        for k, v in req.data.items():
            if k in config and isinstance(config[k], dict) and isinstance(v, dict):
                # 递归更新字典内容，保留未传的字段
                config[k].update(v)
            else:
                config[k] = v
                
        with open(path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, allow_unicode=True)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats/history")
def get_history_stats(days: Optional[int] = 7, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """获取历史统计数据图表"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        where_clause = ""
        if start_date and end_date:
            where_clause = f"WHERE updated_at >= '{start_date} 00:00:00' AND updated_at <= '{end_date} 23:59:59'"
        else:
            where_clause = f"WHERE updated_at >= date('now', '-{days} days')"

        # 1. 获取每日任务完成趋势
        cursor.execute(f'''
            SELECT date(updated_at) as day, 
                   COUNT(*) as total,
                   SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done
            FROM tasks 
            {where_clause}
            GROUP BY day
            ORDER BY day ASC
        ''')
        trend = [{"day": r[0], "total": r[1], "done": r[2]} for r in cursor.fetchall()]
        
        # 2. 获取操作完成率
        cursor.execute(f'''
            SELECT 
                SUM(CASE WHEN like_status='done' THEN 1 ELSE 0 END) as like_done,
                SUM(CASE WHEN comment_status='done' THEN 1 ELSE 0 END) as comment_done,
                SUM(CASE WHEN reply_status='done' THEN 1 ELSE 0 END) as reply_done,
                COUNT(*) as total
            FROM tasks
            {where_clause}
        ''')
        row = cursor.fetchone()
        completion_rates = {
            "like": round(row[0] / row[3] * 100, 1) if row and row[3] > 0 else 0,
            "comment": round(row[1] / row[3] * 100, 1) if row and row[3] > 0 else 0,
            "reply": round(row[2] / row[3] * 100, 1) if row and row[3] > 0 else 0,
        }
        
        conn.close()
        return {
            "trend": trend,
            "rates": completion_rates,
            "period": "custom" if start_date else f"past_{days}_days"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/devices/auto_connect")
def auto_connect_devices():
    """一键识别并连接所有 ADB 设备"""
    try:
        adb = adbutils.adb
        devices = adb.device_list()
        
        if not devices:
            return {"status": "error", "message": "未检测到任何 ADB 设备，请检查 USB 连接及调试模式是否开启"}
        
        # 获取第一个设备作为 Scout
        scout_serial = devices[0].serial
        
        # 更新 Scout 配置
        if os.path.exists(SCOUT_CONFIG_PATH):
            with open(SCOUT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if 'device' not in config:
                config['device'] = {}
            
            config['device']['serial'] = scout_serial
            
            with open(SCOUT_CONFIG_PATH, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True)
        
        device_list = []
        for d in devices:
            role = "Scout" if d.serial == scout_serial else "Grabber"
            device_list.append({
                "serial": d.serial,
                "role": role,
                "model": str(d.prop.model) if hasattr(d, 'prop') else "Unknown"
            })
            
        return {
            "status": "success", 
            "message": f"成功识别 {len(devices)} 台设备。已分配 {scout_serial} 为采集机(Scout)。",
            "devices": device_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
