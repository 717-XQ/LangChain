# -*- coding: utf-8 -*-
"""
react_agent.py - ReAct Agent核心实现（Agent Execution Trace协议）
=============================================
功能：基于Function Calling的ReAct Agent
  - 使用LangChain AgentExecutor
  - 支持多工具协作
  - 异常处理（重试、超时、循环保护）
  - 回调机制（Agent Execution Trace，不暴露内部CoT）
  - 迭代上限后智能整合答案
"""

import time
from typing import List, Dict, Any, Optional, Callable
from loguru import logger

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agent.prompt import REACT_SYSTEM_PROMPT
from llm_client import LLMRouter


class AgentCallback:
    """
    Agent回调基类（Agent Execution Trace协议）

    前端可继承此类，重写对应方法来实时展示Agent的执行轨迹。
    注意：不暴露LLM内部Chain-of-Thought，只推送结构化执行事件。
    WebSocket和Gradio前端都通过此回调机制获取实时事件。
    """

    def on_plan(self, plan: str) -> None:
        """Agent规划任务时调用（展示高层规划，不暴露内部CoT）"""
        pass

    def on_thought(self, thought: str) -> None:
        """兼容旧接口：Agent思考时调用（转发到on_plan，不暴露内部CoT）"""
        # 注意：为了遵循Agent Execution Trace协议，不暴露LLM内部CoT
        # 这里只转发高层规划，不传递详细思考内容
        self.on_plan(f"正在分析问题并规划执行步骤")

    def on_status(self, status: str, detail: str = "") -> None:
        """Agent状态变化时调用（thinking/executing/generating/done）"""
        pass

    def on_tool_start(self, tool_name: str, tool_input: Any, risk_level: str = "READ") -> None:
        """工具调用开始时调用"""
        pass

    def on_tool_end(self, tool_name: str, tool_input: Any, output: str, duration: float) -> None:
        """工具调用结束时调用"""
        pass

    def on_approval_required(self, tool_name: str, tool_input: Any, risk_level: str = "DANGEROUS") -> None:
        """高风险操作需人工确认时调用（Human-in-the-loop）"""
        pass

    def on_token(self, token: str) -> None:
        """流式输出token时调用"""
        pass

    def on_error(self, error: str) -> None:
        """发生错误时调用"""
        pass

    def on_finish(self, answer: str) -> None:
        """任务完成时调用"""
        pass


class LoggingCallback(AgentCallback):
    """日志回调（用于调试和命令行模式）"""

    def on_plan(self, plan: str) -> None:
        logger.info(f"[规划] {plan[:200]}")

    def on_status(self, status: str, detail: str = "") -> None:
        logger.info(f"[状态] {status}: {detail}")

    def on_tool_start(self, tool_name: str, tool_input: Any, risk_level: str = "READ") -> None:
        logger.info(f"[工具调用] {tool_name}({str(tool_input)[:100]}) [风险:{risk_level}]")

    def on_tool_end(self, tool_name: str, tool_input: Any, output: str, duration: float) -> None:
        logger.info(f"[工具结果] {tool_name} ({duration:.2f}s): {str(output)[:200]}")

    def on_approval_required(self, tool_name: str, tool_input: Any, risk_level: str = "DANGEROUS") -> None:
        logger.warning(f"[需审批] {tool_name} [风险:{risk_level}] 输入: {str(tool_input)[:100]}")

    def on_error(self, error: str) -> None:
        logger.error(f"[错误] {error}")

    def on_finish(self, answer: str) -> None:
        logger.info(f"[完成] {answer[:100]}...")


def _wrap_tool_with_callback(tool: BaseTool, callback: AgentCallback) -> BaseTool:
    """
    为工具包装回调（在工具执行前后触发回调事件）

    Args:
        tool: 原始工具
        callback: 回调实例

    Returns:
        BaseTool: 包装后的工具
    """
    original_func = tool.func
    tool_name = tool.name

    # 从工具名称推断风险等级（可通过工具元数据覆盖）
    risk_level = getattr(tool, "risk_level", "READ")
    if risk_level == "READ" and tool_name in ("PythonExecutor",):
        risk_level = "SANDBOX"

    def wrapped_func(*args, **kwargs):
        # 确定工具输入
        tool_input = args[0] if args else kwargs

        callback.on_tool_start(tool_name, tool_input, risk_level)
        start_time = time.time()

        try:
            result = original_func(*args, **kwargs)
            duration = time.time() - start_time
            callback.on_tool_end(tool_name, tool_input, str(result), duration)
            return result
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"工具执行错误: {str(e)}"
            callback.on_error(error_msg)
            callback.on_tool_end(tool_name, tool_input, error_msg, duration)
            return error_msg

    tool.func = wrapped_func
    return tool


class ReActAgent:
    """
    ReAct Agent

    基于Function Calling的自主决策Agent，支持：
    - 多工具协作
    - 记忆上下文
    - 流式输出
    - 回调事件（Agent Execution Trace）
    - 异常处理与循环保护
    - 迭代上限后智能整合答案
    """

    def __init__(
        self,
        tools: List[BaseTool],
        config=None,
        memory_manager=None,
        callbacks: Optional[List[AgentCallback]] = None,
    ):
        """
        Args:
            tools: 可用工具列表
            config: 应用配置
            memory_manager: 记忆管理器
            callbacks: 回调列表
        """
        from config import get_config
        if config is None:
            config = get_config()

        self.config = config
        self.memory_manager = memory_manager
        self.callbacks = callbacks or [LoggingCallback()]

        # 初始化LLM（多Provider自动降级，技术栈2.1）
        self.llm_router = LLMRouter(config)
        self.llm = self.llm_router.create_model()

        # 为工具包装回调
        self.tools = [_wrap_tool_with_callback(t, self._composite_callback) for t in tools]

        # 创建Agent执行器
        self.agent_executor = self._create_agent_executor()

    @property
    def _composite_callback(self) -> AgentCallback:
        """组合多个回调为一个"""
        callbacks = self.callbacks

        class CompositeCallback(AgentCallback):
            def on_plan(self, plan):
                for cb in callbacks:
                    cb.on_plan(plan)

            def on_status(self, status, detail=""):
                for cb in callbacks:
                    cb.on_status(status, detail)

            def on_tool_start(self, tool_name, tool_input, risk_level="READ"):
                for cb in callbacks:
                    cb.on_tool_start(tool_name, tool_input, risk_level)

            def on_tool_end(self, tool_name, tool_input, output, duration):
                for cb in callbacks:
                    cb.on_tool_end(tool_name, tool_input, output, duration)

            def on_approval_required(self, tool_name, tool_input, risk_level="DANGEROUS"):
                for cb in callbacks:
                    cb.on_approval_required(tool_name, tool_input, risk_level)

            def on_token(self, token):
                for cb in callbacks:
                    cb.on_token(token)

            def on_error(self, error):
                for cb in callbacks:
                    cb.on_error(error)

            def on_finish(self, answer):
                for cb in callbacks:
                    cb.on_finish(answer)

        return CompositeCallback()

    def _create_agent_executor(self) -> AgentExecutor:
        """创建Agent执行器"""
        # 构建工具描述
        tools_description = "\n".join(
            f"- {tool.name}: {tool.description}" for tool in self.tools
        )

        # 创建Prompt模板
        prompt = ChatPromptTemplate.from_messages([
            ("system", REACT_SYSTEM_PROMPT.format(tools_description=tools_description)),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # 创建tool-calling agent
        agent = create_tool_calling_agent(self.llm, self.tools, prompt)

        # 创建执行器
        # 注意：LangChain 0.3.x 不再支持 early_stopping_method='generate'
        # max_iterations 达到上限时会自动停止并返回最终答案
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            max_iterations=self.config.agent.max_iterations,
            handle_parsing_errors=self.config.agent.handle_parsing_errors,
            verbose=self.config.agent.verbose,
            return_intermediate_steps=self.config.agent.return_intermediate_steps,
        )

        return agent_executor

    def _synthesize_from_steps(self, query: str, intermediate_steps: list) -> str:
        """
        当Agent达到迭代上限时，基于已有的工具调用结果，用LLM生成最终答案。

        这避免了返回"Agent stopped due to iteration limit"这种无意义的消息。

        Args:
            query: 原始用户问题
            intermediate_steps: 已有的工具调用步骤列表

        Returns:
            str: 整合后的最终答案
        """
        if not intermediate_steps:
            return "抱歉，在处理您的问题时未能获取到足够信息，请尝试换一种方式提问。"

        # 整理工具结果
        context_parts = [f"用户问题: {query}\n\n已获取的信息:"]
        for i, step in enumerate(intermediate_steps, 1):
            if isinstance(step, tuple) and len(step) == 2:
                action, observation = step
                tool_name = getattr(action, "tool", "未知工具")
                tool_input = getattr(action, "tool_input", "")
                context_parts.append(f"\n[{i}] 工具: {tool_name}")
                context_parts.append(f"    输入: {tool_input}")
                context_parts.append(f"    结果: {str(observation)[:800]}")

        context = "\n".join(context_parts)

        # 用LLM生成整合答案
        synthesis_prompt = (
            "请根据以下已获取的信息，回答用户的问题。\n\n"
            f"{context}\n\n"
            "要求：\n"
            "1. 综合所有工具返回的信息，给出完整、有条理的回答\n"
            "2. 如果信息不足，明确说明哪些信息未能获取，并基于已有信息给出尽可能有价值的回答\n"
            "3. 不要提及工具调用过程或迭代限制\n"
            "4. 使用中文回答"
        )

        try:
            from langchain_core.messages import HumanMessage
            response = self.llm_router.invoke([HumanMessage(content=synthesis_prompt)])
            return response.content
        except Exception as e:
            logger.error(f"整合答案失败: {e}")
            return "抱歉，处理您的问题时遇到了一些困难。已获取部分信息但未能完整整合，请尝试简化问题后重试。"

    def run(
        self,
        query: str,
        session_id: str = "default",
        chat_history: Optional[List[BaseMessage]] = None,
    ) -> Dict[str, Any]:
        """
        运行Agent（非流式）

        Args:
            query: 用户输入
            session_id: 会话ID
            chat_history: 额外的对话历史

        Returns:
            Dict: {
                "answer": 最终回答,
                "tool_calls": 工具调用记录,
                "intermediate_steps": 中间步骤
            }
        """
        logger.info(f"Agent收到请求: {query[:100]}")

        # 构建记忆上下文
        memory_context = None
        if self.memory_manager:
            memory_context = self.memory_manager.get_memory_context(session_id, query)
            chat_history = memory_context["messages"]

        # 通知规划开始（Agent Execution Trace，不暴露内部CoT）
        self._composite_callback.on_plan(f"正在分析问题并规划执行步骤")
        self._composite_callback.on_status("thinking", "Agent正在分析问题")

        try:
            # 执行Agent（失败自动降级到下一个Provider重试，技术栈2.1）
            try:
                result = self.agent_executor.invoke({
                    "input": query,
                    "chat_history": chat_history or [],
                })
            except Exception as e:
                if self.llm_router.next_provider():
                    logger.warning(f"LLM Provider调用失败({e})，降级重试")
                    self.llm = self.llm_router.create_model()
                    self.agent_executor = self._create_agent_executor()
                    result = self.agent_executor.invoke({
                        "input": query,
                        "chat_history": chat_history or [],
                    })
                else:
                    raise

            answer = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])

            # 解析工具调用记录
            tool_calls = []
            for step in intermediate_steps:
                if isinstance(step, tuple) and len(step) == 2:
                    action, observation = step
                    tool_calls.append({
                        "tool": getattr(action, "tool", str(action)),
                        "tool_input": getattr(action, "tool_input", ""),
                        "output": str(observation)[:500],
                    })

            # 关键修复：如果达到迭代上限返回了默认停止消息，
            # 则用LLM基于已有的工具结果生成最终答案
            if "stopped due to iteration limit" in answer.lower() or "iteration limit" in answer.lower():
                logger.warning("Agent达到迭代上限，使用LLM基于已有结果生成最终答案")
                self._composite_callback.on_status("generating", "达到迭代上限，整合已有信息生成答案")
                answer = self._synthesize_from_steps(query, intermediate_steps)

            # 保存到记忆
            if self.memory_manager:
                self.memory_manager.add_conversation(session_id, query, answer)

            self._composite_callback.on_status("done", "任务完成")
            self._composite_callback.on_finish(answer)

            return {
                "answer": answer,
                "tool_calls": tool_calls,
                "intermediate_steps": intermediate_steps,
            }

        except Exception as e:
            error_msg = f"Agent执行失败: {str(e)}"
            logger.error(error_msg)
            self._composite_callback.on_error(error_msg)
            return {
                "answer": f"抱歉，处理您的问题时遇到错误: {str(e)}",
                "tool_calls": [],
                "error": error_msg,
            }

    def add_callback(self, callback: AgentCallback) -> None:
        """添加回调"""
        self.callbacks.append(callback)
