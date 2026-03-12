from abc import ABC, abstractmethod
from utils.logger import logger
from core.driver_wrapper import DriverWrapper

class BaseAction(ABC):
    """
    交互动作基类
    """
    def __init__(self, driver: DriverWrapper, config: dict):
        self.driver = driver
        self.config = config

    @abstractmethod
    def execute(self, data: dict) -> bool:
        """
        执行具体的交互逻辑
        :param data: 交互所需的数据 (如用户信息、评论内容等)
        :return: 是否执行成功
        """
        pass
