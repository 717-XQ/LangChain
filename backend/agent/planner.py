# -*- coding: utf-8 -*-
"""
planner.py - Plan-and-Execute规划器
=============================================
功能：处理复杂多步骤任务
  1. 规划器：LLM将任务拆解为有序子步骤
  2. 执行器：逐步用ReAct Agent执行每个子步骤
  3. 动态调整：根据上一步结果修改后续步骤
  4. 结果整合：LLM整合所有步骤结果给出最终回答
"""

import json
from typing import List, Dict, Any, Optional
from loguru import logger

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from agent.prompt import PLANNER_PROMPT, SYNTHESIS_PROMPT
from agent.react_agent import ReActAgent, AgentCallback
from llm_client import LLMRouter


class PlanAndExecuteAgent:
    """
    Plan-and-Execute Agent

    适用于复杂多步骤任务，如"搜索数据→计算→画图→分析"。
    先制定计划，再逐步执行，最后整合结果。
    """

    def __init__(
        self,
        react_agent: ReActAgent,
        config=None,
        callbacks: Optional[List[AgentCallback]] = None,
    ):
        """
        Args:
            react_agent: ReAct Agent实例（用于执行子步骤）
            config: 应用配置
            callbacks: 回调列表
        """
        from config import get_config
        if config is None:
            config = get_config()

        self.config = config
        self.react_agent = react_agent
        self.callbacks = callbacks or []

        # 规划用LLM（多Provider自动降级，技术栈2.1；温度稍高增加规划多样性）
        self.llm_router = LLMRouter(config)
        self.planner_llm = self.llm_router.create_model(
            temperature=0.2,
            max_tokens=1024,
        )

    def plan(self, task: str) -> List[Dict[str, Any]]:
        """
        将任务拆解为子步骤

        Args:
            task: 用户任务

        Returns:
            List[Dict]: 子步骤列表，每个含step/description/tool
        """
        logger.info(f"规划任务: {task[:100]}")

        try:
            response = self.llm_router.invoke(
                PLANNER_PROMPT.format(task=task),
                temperature=0.2,
                max_tokens=1024,
            )
            text = response.content.strip()

            # 清理JSON
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            steps = json.loads(text)
            if not isinstance(steps, list):
                raise ValueError("规划结果不是列表")

            logger.info(f"生成 {len(steps)} 个子步骤")
            for s in steps:
                logger.info(f"  步骤{s.get('step')}: {s.get('description')} (工具: {s.get('tool')})")

            return steps

        except Exception as e:
            logger.error(f"任务规划失败: {e}")
            # 降级：返回单个步骤，直接用ReAct处理
            return [{"step": 1, "description": task, "tool": "reasoning"}]

    def execute_step(
        self,
        step: Dict[str, Any],
        previous_results: List[Dict[str, Any]],
        session_id: str,
    ) -> Dict[str, Any]:
        """
        执行单个子步骤

        Args:
            step: 子步骤
            previous_results: 之前步骤的结果
            session_id: 会话ID

        Returns:
            Dict: 步骤执行结果
        """
        description = step["description"]
        tool = step.get("tool", "reasoning")

        logger.info(f"执行步骤 {step['step']}: {description}")

        # 通知回调（使用on_plan而非on_thought，遵循Execution Trace协议）
        for cb in self.callbacks:
            cb.on_plan(f"[步骤{step['step']}] {description}")

        # 构建步骤上下文（包含之前步骤的结果）
        context = ""
        if previous_results:
            context = "之前步骤的结果：\n"
            for prev in previous_results:
                context += f"步骤{prev['step']}结果: {prev['result'][:300]}\n"
            context += "\n"

        # 构建子任务
        subtask = f"{context}请完成以下任务：{description}"

        # 用ReAct Agent执行
        result = self.react_agent.run(subtask, session_id=f"{session_id}_step{step['step']}")

        step_result = {
            "step": step["step"],
            "description": description,
            "tool": tool,
            "result": result["answer"],
            "tool_calls": result.get("tool_calls", []),
            "success": "error" not in result,
        }

        for cb in self.callbacks:
            cb.on_tool_end(f"步骤{step['step']}", description, result["answer"][:200], 0)

        return step_result

    def synthesize(
        self,
        task: str,
        steps: List[Dict[str, Any]],
        step_results: List[Dict[str, Any]],
    ) -> str:
        """
        整合所有步骤结果，生成最终回答

        Args:
            task: 原始任务
            steps: 执行计划
            step_results: 各步骤结果

        Returns:
            str: 最终回答
        """
        logger.info("整合所有步骤结果...")

        # 格式化计划
        plan_text = "\n".join(
            f"{s['step']}. {s['description']} (工具: {s.get('tool', 'N/A')})"
            for s in steps
        )

        # 格式化结果
        results_text = "\n\n".join(
            f"步骤{r['step']}: {r['description']}\n结果: {r['result']}"
            for r in step_results
        )

        try:
            response = self.llm_router.invoke(
                SYNTHESIS_PROMPT.format(
                    task=task,
                    plan=plan_text,
                    step_results=results_text,
                )
            )
            return response.content
        except Exception as e:
            logger.error(f"结果整合失败: {e}")
            # 降级：直接拼接结果
            return f"任务完成，但结果整合失败。各步骤结果：\n\n{results_text}"

    def should_replan(
        self,
        step_result: Dict[str, Any],
        remaining_steps: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        """
        根据步骤结果判断是否需要重新规划

        Args:
            step_result: 当前步骤结果
            remaining_steps: 剩余步骤

        Returns:
            新的步骤列表（如果需要重新规划），否则None
        """
        # 如果步骤失败，尝试简化后续计划
        if not step_result.get("success", True):
            logger.warning(f"步骤{step_result['step']}失败，考虑调整计划")
            # 简化实现：不重新规划，继续执行
            # 生产环境可调用LLM重新规划
        return None

    def run(
        self,
        task: str,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """
        执行Plan-and-Execute完整流程

        Args:
            task: 用户任务
            session_id: 会话ID

        Returns:
            Dict: {
                "answer": 最终回答,
                "steps": 执行计划,
                "step_results": 各步骤结果,
                "tool_calls": 所有工具调用记录
            }
        """
        logger.info(f"Plan-and-Execute开始: {task[:100]}")

        # 1. 规划
        steps = self.plan(task)

        # 2. 逐步执行
        step_results = []
        all_tool_calls = []

        for i, step in enumerate(steps):
            result = self.execute_step(step, step_results, session_id)
            step_results.append(result)
            all_tool_calls.extend(result.get("tool_calls", []))

            # 动态调整检查
            remaining = steps[i + 1:]
            new_steps = self.should_replan(result, remaining)
            if new_steps is not None:
                steps = steps[:i + 1] + new_steps

        # 3. 整合结果
        answer = self.synthesize(task, steps, step_results)

        for cb in self.callbacks:
            cb.on_finish(answer)

        return {
            "answer": answer,
            "steps": steps,
            "step_results": step_results,
            "tool_calls": all_tool_calls,
        }
