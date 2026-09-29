# -*- coding: utf-8 -*-
"""
memory_manager.py - 记忆管理器
=============================================
功能：统一管理短期记忆和长期记忆
  - get_memory_context(query): 拼接短期+长期记忆上下文
  - add_conversation(): 添加一轮对话
  - auto_extract_facts(): 对话结束后LLM自动提取需要长期记住的事实
  - 多会话隔离（按session_id）
"""

import json
from typing import List, Dict, Any, Optional
from loguru import logger

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory


class MemoryManager:
    """
    记忆管理器

    统一管理短期（滑动窗口）和长期（向量）记忆，
    为Agent提供记忆上下文构建、自动事实提取等能力。
    支持多会话隔离。
    """

    def __init__(self, config=None):
        """
        Args:
            config: 应用配置（为None时从全局加载）
        """
        from config import get_config
        if config is None:
            config = get_config()

        self.config = config
        self.memory_config = config.memory

        # 短期记忆（按session_id隔离）
        self._short_term_memories: Dict[str, ShortTermMemory] = {}

        # 长期记忆（全局共享，跨会话）
        self._long_term = LongTermMemory(
            embedding_model=self.memory_config.long_term_embedding_model,
            persist_dir=self.memory_config.long_term_persist_dir,
            top_k=self.memory_config.long_term_top_k,
            similarity_threshold=self.memory_config.similarity_threshold,
        )

        # LLM实例（用于自动提取事实，延迟初始化）
        self._llm = None

    def _get_llm(self):
        """获取LLM实例"""
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(
                model=self.config.llm.model,
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url,
                temperature=0.0,
                max_tokens=512,
            )
        return self._llm

    def _get_short_term(self, session_id: str) -> ShortTermMemory:
        """获取指定会话的短期记忆"""
        if session_id not in self._short_term_memories:
            self._short_term_memories[session_id] = ShortTermMemory(
                window_size=self.memory_config.short_term_window
            )
        return self._short_term_memories[session_id]

    def add_conversation(
        self,
        session_id: str,
        user_message: str,
        ai_message: str,
        auto_extract: bool = True,
    ) -> None:
        """
        添加一轮对话到记忆

        Args:
            session_id: 会话ID
            user_message: 用户消息
            ai_message: AI回复
            auto_extract: 是否自动提取长期事实
        """
        # 添加到短期记忆
        stm = self._get_short_term(session_id)
        stm.add_user_message(user_message)
        stm.add_ai_message(ai_message)

        # 自动提取长期事实
        if auto_extract:
            try:
                self.auto_extract_facts(user_message, ai_message)
            except Exception as e:
                logger.warning(f"自动提取事实失败: {e}")

    def get_memory_context(
        self,
        session_id: str,
        query: str = "",
    ) -> Dict[str, Any]:
        """
        构建记忆上下文（供Agent使用）

        Args:
            session_id: 会话ID
            query: 当前查询（用于检索相关长期记忆）

        Returns:
            Dict: {
                "history": 短期对话历史文本,
                "messages": 短期消息列表,
                "long_term_facts": 相关长期事实列表,
                "context_text": 拼接好的上下文字符串
            }
        """
        stm = self._get_short_term(session_id)

        # 短期记忆
        messages = stm.get_messages()
        history_text = stm.get_history_text()

        # 长期记忆检索
        long_term_facts = []
        if query and self._long_term.count > 0:
            long_term_facts = self._long_term.search(query)

        # 拼接上下文
        context_parts = []
        if long_term_facts:
            facts_text = "\n".join(
                f"- {f['content']}" for f in long_term_facts
            )
            context_parts.append(f"【相关记忆】\n{facts_text}")

        context_parts.append(f"【对话历史】\n{history_text}")
        context_text = "\n\n".join(context_parts)

        return {
            "history": history_text,
            "messages": messages,
            "long_term_facts": long_term_facts,
            "context_text": context_text,
        }

    def add_long_term_fact(
        self,
        content: str,
        fact_type: str = "general",
        source: str = "manual",
        metadata: Optional[Dict] = None,
    ) -> bool:
        """
        手动添加长期事实

        Args:
            content: 事实内容
            fact_type: 类型
            source: 来源
            metadata: 额外元数据

        Returns:
            bool: 是否添加成功
        """
        return self._long_term.add_fact(content, fact_type, source, metadata)

    def search_long_term(self, query: str, top_k: int = 3) -> List[Dict]:
        """检索长期记忆"""
        return self._long_term.search(query, top_k)

    def auto_extract_facts(self, user_message: str, ai_message: str) -> List[str]:
        """
        使用LLM自动从对话中提取值得长期记住的事实

        Args:
            user_message: 用户消息
            ai_message: AI回复

        Returns:
            List[str]: 提取到的事实列表
        """
        prompt = f"""请分析以下对话，判断是否有值得长期记住的事实信息（如用户偏好、个人信息、重要约定等）。

用户: {user_message}
助手: {ai_message}

如果有值得记住的事实，请以JSON数组格式返回，每个元素是一条事实字符串。
如果没有值得记住的信息，返回空数组 []。
只返回JSON，不要其他文字。

示例输出：
["用户偏好使用Python语言", "用户正在学习LangChain框架"]
"""
        try:
            response = self._get_llm().invoke(prompt)
            text = response.content.strip()

            # 解析JSON
            if text.startswith("```"):
                # 去除markdown代码块
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            facts = json.loads(text)
            if not isinstance(facts, list):
                return []

            # 存储提取的事实
            stored = []
            for fact in facts:
                if isinstance(fact, str) and len(fact) > 3:
                    if self._long_term.add_fact(
                        content=fact,
                        fact_type="auto_extracted",
                        source="conversation",
                    ):
                        stored.append(fact)

            if stored:
                logger.info(f"自动提取 {len(stored)} 条长期事实")
            return stored

        except Exception as e:
            logger.debug(f"事实提取解析失败: {e}")
            return []

    def clear_session(self, session_id: str) -> None:
        """清空指定会话的短期记忆"""
        if session_id in self._short_term_memories:
            self._short_term_memories[session_id].clear()
            del self._short_term_memories[session_id]
            logger.info(f"会话 {session_id} 短期记忆已清空")

    def clear_long_term(self) -> None:
        """清空长期记忆"""
        self._long_term.clear()

    def get_stats(self, session_id: str = "default") -> Dict[str, Any]:
        """获取记忆统计信息"""
        stm = self._get_short_term(session_id)
        return {
            "short_term_messages": len(stm),
            "long_term_facts": self._long_term.count,
            "sessions": len(self._short_term_memories),
        }
