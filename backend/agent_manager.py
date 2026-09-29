# -*- coding: utf-8 -*-
"""
agent_manager.py - Agent统一管理器
=============================================
功能：初始化并管理所有组件
  - 加载配置
  - 初始化记忆管理器
  - 初始化所有工具
  - 创建ReAct/LangGraph/Plan-and-Execute三种Agent
  - 提供统一的run_agent接口
"""

from typing import List, Dict, Any, Optional
from loguru import logger

from config import AppConfig, get_config
from memory.memory_manager import MemoryManager
from tools import get_all_tools
from tools.doc_qa import get_doc_qa_tool
from agent.react_agent import ReActAgent, AgentCallback
from agent.langgraph_agent import LangGraphAgent
from agent.planner import PlanAndExecuteAgent


class AgentManager:
    """
    Agent统一管理器

    懒加载所有组件，避免启动时加载所有模型。
    提供统一的run_agent接口，支持三种Agent模式。
    """

    def __init__(self, config: Optional[AppConfig] = None):
        """
        Args:
            config: 应用配置（为None时从config.yaml加载）
        """
        self.config = config or get_config()
        self._memory = None
        self._tools = None
        self._react_agent = None
        self._langgraph_agent = None
        self._planner = None
        self._doc_qa_tool = None

    @property
    def memory(self) -> MemoryManager:
        """获取记忆管理器（懒加载）"""
        if self._memory is None:
            logger.info("初始化记忆管理器...")
            self._memory = MemoryManager(self.config)
        return self._memory

    @property
    def tools(self):
        """获取工具列表（懒加载）"""
        if self._tools is None:
            logger.info("初始化工具集...")
            # 文档QA工具（可选，初始化失败不影响其他工具）
            if self._doc_qa_tool is None:
                try:
                    self._doc_qa_tool = get_doc_qa_tool(self.config)
                    if self._doc_qa_tool:
                        logger.info("文档QA工具已加载")
                except Exception as e:
                    logger.warning(f"文档QA工具初始化失败（不影响其他功能）: {e}")
                    self._doc_qa_tool = None

            self._tools = get_all_tools(
                memory_manager=self.memory,
                doc_qa_tool=self._doc_qa_tool,
            )
            logger.info(f"已加载 {len(self._tools)} 个工具: "
                       f"{[t.name for t in self._tools]}")
        return self._tools

    def get_react_agent(
        self,
        extra_callbacks: Optional[List[AgentCallback]] = None,
    ) -> ReActAgent:
        """
        获取ReAct Agent实例

        每次调用创建新实例（因为回调可能不同），但共享工具和记忆
        """
        callbacks = []
        if extra_callbacks:
            callbacks.extend(extra_callbacks)

        return ReActAgent(
            tools=self.tools,
            config=self.config,
            memory_manager=self.memory,
            callbacks=callbacks,
        )

    def get_langgraph_agent(
        self,
        extra_callbacks: Optional[List[AgentCallback]] = None,
    ) -> LangGraphAgent:
        """获取LangGraph Agent实例"""
        callbacks = extra_callbacks or []
        return LangGraphAgent(
            tools=self.tools,
            config=self.config,
            memory_manager=self.memory,
            callbacks=callbacks,
        )

    def get_planner(
        self,
        extra_callbacks: Optional[List[AgentCallback]] = None,
    ) -> PlanAndExecuteAgent:
        """获取Plan-and-Execute Agent实例"""
        react_agent = self.get_react_agent(extra_callbacks)
        return PlanAndExecuteAgent(
            react_agent=react_agent,
            config=self.config,
            callbacks=extra_callbacks,
        )

    def run_agent(
        self,
        query: str,
        session_id: str = "default",
        agent_type: str = "react",
        extra_callbacks: Optional[List[AgentCallback]] = None,
    ) -> Dict[str, Any]:
        """
        统一的Agent运行接口

        Args:
            query: 用户输入
            session_id: 会话ID
            agent_type: Agent类型 ("react" / "langgraph" / "planner")
            extra_callbacks: 额外回调

        Returns:
            Dict: 运行结果
        """
        if agent_type == "langgraph":
            agent = self.get_langgraph_agent(extra_callbacks)
            return agent.run(query, session_id=session_id)

        elif agent_type == "planner":
            planner = self.get_planner(extra_callbacks)
            return planner.run(query, session_id=session_id)

        else:  # 默认 react
            agent = self.get_react_agent(extra_callbacks)
            return agent.run(query, session_id=session_id)


# 全局单例
_global_manager: Optional[AgentManager] = None


def get_agent_manager(config: Optional[AppConfig] = None) -> AgentManager:
    """获取全局Agent管理器单例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = AgentManager(config)
    return _global_manager
