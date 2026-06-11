"""BaseCollector — 数据采集器抽象基类。"""

from abc import ABC, abstractmethod
from datetime import datetime


class BaseCollector(ABC):
    """所有采集器的基类。"""

    def __init__(self, instance):
        """
        Args:
            instance: DatabaseInstance 模型对象
        """
        self.instance = instance
        self.conn = None

    @abstractmethod
    def connect(self):
        """建立到目标数据库的连接。"""
        ...

    @abstractmethod
    def collect(self) -> list[dict]:
        """执行采集，返回 ClickHouse metrics 行列表。"""
        ...

    def close(self):
        """关闭连接。"""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def run(self) -> list[dict]:
        """完整的采集流程: connect → collect → close。"""
        try:
            self.connect()
            rows = self.collect()
            return rows
        finally:
            self.close()
