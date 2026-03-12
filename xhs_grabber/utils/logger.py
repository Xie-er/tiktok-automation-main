from loguru import logger
import sys
import os

# 确保日志目录存在
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置 logger
logger.remove()  # 移除默认 handler

# 控制台输出
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 文件输出
logger.add(
    os.path.join(log_dir, "runtime_{time}.log"),
    rotation="50 MB",
    retention="10 days",
    level="DEBUG",
    encoding="utf-8"
)
