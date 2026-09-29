# -*- coding: utf-8 -*-
"""
memory 包 - 混合记忆系统
=============================================
短期记忆：滑动窗口，保留最近5轮对话
长期记忆：FAISS向量库，存储关键事实，语义检索
记忆管理器：统一接口，自动提取与去重
"""

from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.memory_manager import MemoryManager

__all__ = ["ShortTermMemory", "LongTermMemory", "MemoryManager"]
