from abc import ABC, abstractmethod
from utils.logger import logger
from core.driver_wrapper import DriverWrapper

class BaseAction(ABC):
    """
    宠物部门交互动作基类
    """
    def __init__(self, driver: DriverWrapper, config: dict):
        self.driver = driver
        self.config = config

    @abstractmethod
    def execute(self, data: dict = None) -> bool:
        """
        执行具体的交互逻辑
        """
        pass
