# -*- coding: utf-8 -*-
"""
short_term.py - 短期记忆（滑动窗口）
=============================================
功能：保留最近K轮对话，超出窗口自动淘汰旧消息
基于LangChain消息格式，与Agent无缝集成
"""

from typing import List, Dict, Any, Optional
from collections import deque
from loguru import logger

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


class ShortTermMemory:
    """
    短期记忆：滑动窗口实现

    维护一个固定大小的消息队列，新消息加入时自动淘汰最旧的消息。
    一轮对话 = 一条HumanMessage + 一条AIMessage。
    """

    def __init__(self, window_size: int = 5):
        """
        Args:
            window_size: 滑动窗口大小（保留最近多少轮对话）
        """
        self.window_size = window_size
        # 使用deque实现滑动窗口，maxlen自动淘汰旧消息
        # 每条消息是一个BaseMessage对象
        self._messages: deque = deque(maxlen=window_size * 2)  # 每轮2条消息

    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self._messages.append(HumanMessage(content=content))
        logger.debug(f"短期记忆: 添加用户消息，当前{len(self._messages)}条")

    def add_ai_message(self, content: str) -> None:
        """添加AI消息"""
        self._messages.append(AIMessage(content=content))
        logger.debug(f"短期记忆: 添加AI消息，当前{len(self._messages)}条")

    def add_message(self, message: BaseMessage) -> None:
        """添加原始消息对象"""
        self._messages.append(message)

    def get_messages(self) -> List[BaseMessage]:
        """获取当前窗口内的所有消息"""
        return list(self._messages)

    def get_history_text(self) -> str:
        """
        获取对话历史的文本格式（用于Prompt拼接）

        Returns:
            str: 格式化的对话历史
        """
        if not self._messages:
            return "（暂无对话历史）"

        lines = []
        for msg in self._messages:
            if isinstance(msg, HumanMessage):
                lines.append(f"用户: {msg.content}")
            elif isinstance(msg, AIMessage):
                lines.append(f"助手: {msg.content}")
            elif isinstance(msg, SystemMessage):
                lines.append(f"系统: {msg.content}")
            else:
                lines.append(f"{msg.type}: {msg.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        """清空短期记忆"""
        self._messages.clear()
        logger.info("短期记忆已清空")

    def __len__(self) -> int:
        return len(self._messages)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于持久化）"""
        messages = []
        for msg in self._messages:
            messages.append({
                "type": msg.type,
                "content": msg.content,
            })
        return {"window_size": self.window_size, "messages": messages}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShortTermMemory":
        """从字典反序列化"""
        memory = cls(window_size=data.get("window_size", 5))
        type_map = {
            "human": HumanMessage,
            "ai": AIMessage,
            "system": SystemMessage,
        }
        for msg_data in data.get("messages", []):
            msg_cls = type_map.get(msg_data["type"])
            if msg_cls:
                memory.add_message(msg_cls(content=msg_data["content"]))
        return memory
