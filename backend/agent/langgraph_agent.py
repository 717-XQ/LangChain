# -*- coding: utf-8 -*-
"""
langgraph_agent.py - LangGraph有状态Agent
=============================================
功能：基于StateGraph构建Agent状态机
  - 状态：messages、iteration、tool_calls
  - 节点：agent（LLM决策）、tools（工具执行）
  - 条件边：根据是否有tool_calls判断走向
  - Checkpointer：支持中断恢复
  - Human-in-the-loop：关键操作前暂停等待人工确认
"""

import time
from typing import List, Dict, Any, Annotated, Optional, TypedDict
from loguru import logger

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.prompt import REACT_SYSTEM_PROMPT
from agent.react_agent import AgentCallback
from llm_client import LLMRouter


def _merge_messages(left: list, right: list) -> list:
    """消息合并函数（用于LangGraph状态累加）"""
    return left + right


class AgentState(TypedDict):
    """LangGraph Agent状态定义"""
    messages: Annotated[List[BaseMessage], _merge_messages]  # 消息历史（累加）
    iteration: int                                            # 当前迭代次数
    tool_calls: List[Dict[str, Any]]                          # 工具调用记录


class LangGraphAgent:
    """
    LangGraph有状态Agent

    相比ReAct Agent，增加了：
    - 显式状态管理（可持久化、可恢复）
    - 人工介入（Human-in-the-loop）
    - 更灵活的图编排
    """

    def __init__(
        self,
        tools: List[BaseTool],
        config=None,
        memory_manager=None,
        callbacks: Optional[List[AgentCallback]] = None,
        human_in_the_loop: bool = False,
        sensitive_tools: Optional[List[str]] = None,
    ):
        """
        Args:
            tools: 可用工具列表
            config: 应用配置
            memory_manager: 记忆管理器
            callbacks: 回调列表
            human_in_the_loop: 是否启用人工介入
            sensitive_tools: 需要人工确认的工具名列表
        """
        from config import get_config
        if config is None:
            config = get_config()

        self.config = config
        self.memory_manager = memory_manager
        self.callbacks = callbacks or []
        self.human_in_the_loop = human_in_the_loop
        self.sensitive_tools = sensitive_tools or ["PythonExecutor"]

        # 工具映射
        self.tools = list(tools)
        self.tools_by_name = {t.name: t for t in tools}

        # 初始化LLM并绑定工具（多Provider自动降级，技术栈2.1）
        self.llm_router = LLMRouter(config)
        self.llm = self.llm_router.create_model(bind_tools=tools)

        # 系统Prompt
        tools_description = "\n".join(f"- {t.name}: {t.description}" for t in tools)
        self.system_message = SystemMessage(
            content=REACT_SYSTEM_PROMPT.format(tools_description=tools_description)
        )

        # Checkpointer（用于中断恢复）
        self.checkpointer = MemorySaver()

        # 构建图
        self.graph = self._build_graph()

        # 人工确认事件（线程间通信）
        self._approval_events: Dict[str, Any] = {}

    def _build_graph(self):
        """构建LangGraph状态图"""
        # 创建状态图
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tools", self._tools_node)

        # 设置入口
        workflow.set_entry_point("agent")

        # 添加条件边：agent → tools（有工具调用）或 agent → END（无工具调用）
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "tools",
                "end": END,
            },
        )

        # tools → agent（工具执行完回到agent决策）
        workflow.add_edge("tools", "agent")

        # 编译图（带checkpointer）
        return workflow.compile(checkpointer=self.checkpointer)

    def _agent_node(self, state: AgentState) -> Dict:
        """
        Agent节点：LLM决策

        接收当前消息历史，调用LLM决定下一步行动
        """
        messages = state["messages"]
        iteration = state.get("iteration", 0) + 1

        logger.info(f"[LangGraph] Agent节点，迭代 {iteration}")

        # 注入系统消息
        full_messages = [self.system_message] + messages

        # 调用LLM（失败自动降级到下一个Provider重试，技术栈2.1）
        try:
            response = self.llm.invoke(full_messages)
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            if self.llm_router.next_provider():
                logger.warning(f"LangGraph LLM降级重试: {self.llm_router.provider_name}")
                self.llm = self.llm_router.create_model(bind_tools=self.tools)
                try:
                    response = self.llm.invoke(full_messages)
                except Exception as e2:
                    logger.error(f"LangGraph LLM降级后仍失败: {e2}")
                    response = AIMessage(content=f"LLM调用失败: {e2}")
            else:
                response = AIMessage(content=f"LLM调用失败: {e}")

        # 通知回调
        if response.tool_calls:
            for tc in response.tool_calls:
                for cb in self.callbacks:
                    cb.on_tool_start(tc["name"], tc.get("args", {}))
        else:
            for cb in self.callbacks:
                # 使用on_plan而非on_thought，遵循Execution Trace协议，不暴露内部CoT
                cb.on_plan("正在整合信息生成最终答案")

        return {
            "messages": [response],
            "iteration": iteration,
        }

    def _tools_node(self, state: AgentState) -> Dict:
        """
        工具节点：执行工具调用

        遍历最后一条AI消息中的tool_calls，逐个执行
        """
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls if hasattr(last_message, "tool_calls") else []

        tool_messages = []
        tool_call_records = state.get("tool_calls", [])

        for tc in tool_calls:
            tool_name = tc["name"]
            tool_args = tc.get("args", {})
            tool_call_id = tc.get("id", "unknown")

            # 人工介入检查
            if self.human_in_the_loop and tool_name in self.sensitive_tools:
                approved = self._wait_for_human_approval(tool_name, tool_args)
                if not approved:
                    tool_messages.append(ToolMessage(
                        content="用户拒绝了此操作",
                        tool_call_id=tool_call_id,
                    ))
                    continue

            # 执行工具
            logger.info(f"[LangGraph] 执行工具: {tool_name}")
            start_time = time.time()

            try:
                tool = self.tools_by_name.get(tool_name)
                if tool is None:
                    result = f"错误: 未找到工具 {tool_name}"
                else:
                    # 提取工具输入（LangChain工具通常接受单个字符串参数）
                    if isinstance(tool_args, dict):
                        tool_input = tool_args.get("__arg1", "") or next(iter(tool_args.values()), "")
                    else:
                        tool_input = str(tool_args)

                    result = tool.invoke(tool_input)

                duration = time.time() - start_time
                result_str = str(result)

                # 通知回调
                for cb in self.callbacks:
                    cb.on_tool_end(tool_name, tool_args, result_str, duration)

                # 记录工具调用
                tool_call_records.append({
                    "tool": tool_name,
                    "tool_input": tool_args,
                    "output": result_str[:500],
                    "duration": round(duration, 2),
                })

            except Exception as e:
                duration = time.time() - start_time
                result_str = f"工具执行错误: {str(e)}"
                for cb in self.callbacks:
                    cb.on_error(result_str)
                    cb.on_tool_end(tool_name, tool_args, result_str, duration)
                tool_call_records.append({
                    "tool": tool_name,
                    "tool_input": tool_args,
                    "output": result_str,
                    "duration": round(duration, 2),
                    "success": False,
                })

            tool_messages.append(ToolMessage(
                content=result_str[:5000],
                tool_call_id=tool_call_id,
            ))

        return {
            "messages": tool_messages,
            "tool_calls": tool_call_records,
        }

    def _should_continue(self, state: AgentState) -> str:
        """
        条件判断：是否继续执行工具

        Returns:
            "continue" 或 "end"
        """
        last_message = state["messages"][-1]
        iteration = state.get("iteration", 0)

        # 超过最大迭代次数，强制结束
        if iteration >= self.config.agent.max_iterations:
            logger.warning(f"达到最大迭代次数 {self.config.agent.max_iterations}，强制结束")
            return "end"

        # 如果AI消息包含工具调用，继续执行
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"

        # 否则结束
        return "end"

    def _wait_for_human_approval(self, tool_name: str, tool_args: Any) -> bool:
        """
        等待人工确认（简化实现，默认通过）

        生产环境可通过WebSocket/前端实现真正的异步确认
        """
        logger.info(f"[人工介入] 工具 {tool_name} 需要确认，参数: {tool_args}")
        # 简化实现：默认通过
        # 生产环境可通过 threading.Event 等待前端确认
        return True

    def run(
        self,
        query: str,
        session_id: str = "default",
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        运行LangGraph Agent

        Args:
            query: 用户输入
            session_id: 会话ID（记忆系统用）
            thread_id: 线程ID（LangGraph checkpoint用）

        Returns:
            Dict: {
                "answer": 最终回答,
                "tool_calls": 工具调用记录,
                "iteration": 迭代次数
            }
        """
        logger.info(f"[LangGraph] 收到请求: {query[:100]}")

        # 构建消息
        messages = [HumanMessage(content=query)]

        # 注入记忆上下文
        if self.memory_manager:
            memory_context = self.memory_manager.get_memory_context(session_id, query)
            if memory_context["messages"]:
                messages = memory_context["messages"] + messages

        # 初始状态
        initial_state = {
            "messages": messages,
            "iteration": 0,
            "tool_calls": [],
        }

        # 配置（thread_id用于checkpoint）
        config = {"configurable": {"thread_id": thread_id or session_id}}

        try:
            # 执行图
            final_state = self.graph.invoke(initial_state, config=config)

            # 提取最终回答（最后一条AI消息）
            answer = ""
            for msg in reversed(final_state["messages"]):
                if isinstance(msg, AIMessage) and msg.content:
                    answer = msg.content
                    break

            # 保存到记忆
            if self.memory_manager:
                self.memory_manager.add_conversation(session_id, query, answer)

            for cb in self.callbacks:
                cb.on_finish(answer)

            return {
                "answer": answer,
                "tool_calls": final_state.get("tool_calls", []),
                "iteration": final_state.get("iteration", 0),
            }

        except Exception as e:
            error_msg = f"LangGraph Agent执行失败: {str(e)}"
            logger.error(error_msg)
            for cb in self.callbacks:
                cb.on_error(error_msg)
            return {
                "answer": f"抱歉，处理时遇到错误: {str(e)}",
                "tool_calls": [],
                "error": error_msg,
            }
