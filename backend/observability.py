# -*- coding: utf-8 -*-
"""
observability.py - 可观测性模块（请求追踪 + 性能监控 + 成本统计）
=============================================
功能：
  1. request_id / trace_id 全链路追踪
  2. 性能指标统计（总耗时、LLM调用次数、token用量、工具耗时）
  3. 工具调用成功率统计
  4. LLM成本估算（按token单价计算）
  5. 结构化日志（loguru）
  6. 指标导出（JSON格式，可对接Prometheus/Grafana）

对应文档中的可观测性设计：
  request_id + trace_id全链路追踪
  token usage / latency / tool latency / error rate统计
  loguru结构化日志
"""

import time
import uuid
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from loguru import logger


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ToolCallRecord:
    """工具调用记录"""
    tool_name: str
    input: str
    output: str
    duration: float       # 秒
    success: bool
    error: str = ""
    risk_level: str = "READ"


@dataclass
class LLMRoundRecord:
    """LLM调用记录"""
    round_num: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration: float = 0.0
    tool_call: Optional[str] = None  # 本轮是否调用了工具


@dataclass
class RequestMetrics:
    """单次请求的完整指标"""
    request_id: str
    trace_id: str
    session_id: str = ""
    query: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration: float = 0.0
    llm_rounds: List[LLMRoundRecord] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    success: bool = True
    error: str = ""
    agent_type: str = "react"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于JSON导出）"""
        return {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "query": self.query[:200],
            "total_duration_ms": round(self.total_duration * 1000, 2),
            "llm_rounds": len(self.llm_rounds),
            "tool_calls": len(self.tool_calls),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.estimated_cost, 6),
            "success": self.success,
            "error": self.error,
            "agent_type": self.agent_type,
            "tool_details": [
                {
                    "tool": t.tool_name,
                    "duration_ms": round(t.duration * 1000, 2),
                    "success": t.success,
                    "risk_level": t.risk_level,
                }
                for t in self.tool_calls
            ],
        }


# ============================================================
# LLM 成本估算（按常见模型单价）
# ============================================================

# 模型单价（美元/1K tokens），用于成本估算
MODEL_PRICING = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "qwen2.5-72b-instruct": {"input": 0.0, "output": 0.0},  # 本地模型免费
    "default": {"input": 0.001, "output": 0.002},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    估算LLM调用成本

    Args:
        model: 模型名称
        prompt_tokens: 输入token数
        completion_tokens: 输出token数

    Returns:
        float: 估算成本（美元）
    """
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])
    cost = (prompt_tokens / 1000 * pricing["input"] +
            completion_tokens / 1000 * pricing["output"])
    return cost


# ============================================================
# 请求追踪上下文管理器
# ============================================================

class RequestTracer:
    """
    请求追踪器

    用法：
        with RequestTracer(query="你好", session_id="abc") as tracer:
            # 执行业务逻辑
            tracer.add_tool_call("Search", "query", "result", 0.23, True)
            tracer.add_llm_round(1, 100, 50, 1.2)
        # 自动计算总耗时和成本
        metrics = tracer.metrics
    """

    def __init__(self, query: str = "", session_id: str = "",
                 agent_type: str = "react", model: str = "default"):
        self.metrics = RequestMetrics(
            request_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            session_id=session_id,
            query=query,
            agent_type=agent_type,
        )
        self._model = model
        self._current_llm_round = 0

    def __enter__(self):
        self.metrics.start_time = time.time()
        logger.info(
            f"[Trace] 请求开始 | request_id={self.metrics.request_id} "
            f"trace_id={self.metrics.trace_id} query={self.metrics.query[:50]}"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.metrics.end_time = time.time()
        self.metrics.total_duration = self.metrics.end_time - self.metrics.start_time

        if exc_val:
            self.metrics.success = False
            self.metrics.error = str(exc_val)[:500]
            logger.error(
                f"[Trace] 请求失败 | request_id={self.metrics.request_id} "
                f"error={self.metrics.error} duration={self.metrics.total_duration:.2f}s"
            )
        else:
            logger.info(
                f"[Trace] 请求完成 | request_id={self.metrics.request_id} "
                f"duration={self.metrics.total_duration:.2f}s "
                f"tokens={self.metrics.total_tokens} "
                f"tools={len(self.metrics.tool_calls)} "
                f"cost=${self.metrics.estimated_cost:.6f}"
            )

        # 记录到全局统计
        _global_stats.record(self.metrics)
        return False  # 不吞异常

    def add_tool_call(self, tool_name: str, tool_input: str, output: str,
                      duration: float, success: bool, error: str = "",
                      risk_level: str = "READ") -> None:
        """记录工具调用"""
        record = ToolCallRecord(
            tool_name=tool_name,
            input=str(tool_input)[:500],
            output=str(output)[:500],
            duration=duration,
            success=success,
            error=error,
            risk_level=risk_level,
        )
        self.metrics.tool_calls.append(record)
        logger.debug(
            f"[Trace] 工具调用 | {tool_name} {duration*1000:.0f}ms "
            f"success={success} risk={risk_level}"
        )

    def add_llm_round(self, prompt_tokens: int = 0, completion_tokens: int = 0,
                      duration: float = 0.0, tool_call: Optional[str] = None) -> None:
        """记录LLM调用轮次"""
        self._current_llm_round += 1
        total = prompt_tokens + completion_tokens
        round_cost = estimate_cost(self._model, prompt_tokens, completion_tokens)

        record = LLMRoundRecord(
            round_num=self._current_llm_round,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            duration=duration,
            tool_call=tool_call,
        )
        self.metrics.llm_rounds.append(record)
        self.metrics.total_prompt_tokens += prompt_tokens
        self.metrics.total_completion_tokens += completion_tokens
        self.metrics.total_tokens += total
        self.metrics.estimated_cost += round_cost

        logger.debug(
            f"[Trace] LLM轮次#{self._current_llm_round} | "
            f"tokens={total} duration={duration*1000:.0f}ms "
            f"tool_call={tool_call or 'none'} cost=${round_cost:.6f}"
        )

    def set_success(self, success: bool, error: str = "") -> None:
        """设置请求结果"""
        self.metrics.success = success
        if error:
            self.metrics.error = error[:500]


# ============================================================
# 全局统计
# ============================================================

class GlobalStats:
    """全局统计（进程级，生产环境应接入Prometheus）"""

    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.total_duration = 0.0
        self.tool_call_count = defaultdict(int)
        self.tool_success_count = defaultdict(int)
        self.agent_type_count = defaultdict(int)

    def record(self, metrics: RequestMetrics) -> None:
        """记录一次请求的指标"""
        self.total_requests += 1
        if metrics.success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        self.total_tokens += metrics.total_tokens
        self.total_cost += metrics.estimated_cost
        self.total_duration += metrics.total_duration
        self.agent_type_count[metrics.agent_type] += 1

        for tool in metrics.tool_calls:
            self.tool_call_count[tool.tool_name] += 1
            if tool.success:
                self.tool_success_count[tool.tool_name] += 1

    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        avg_duration = self.total_duration / self.total_requests if self.total_requests > 0 else 0
        success_rate = self.successful_requests / self.total_requests if self.total_requests > 0 else 0

        tool_stats = {}
        for tool, count in self.tool_call_count.items():
            success = self.tool_success_count.get(tool, 0)
            tool_stats[tool] = {
                "total": count,
                "success": success,
                "success_rate": round(success / count, 4) if count > 0 else 0,
            }

        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": round(success_rate, 4),
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 6),
            "avg_duration_ms": round(avg_duration * 1000, 2),
            "agent_type_distribution": dict(self.agent_type_count),
            "tool_stats": tool_stats,
        }

    def reset(self) -> None:
        """重置统计"""
        self.__init__()


# 全局单例
_global_stats = GlobalStats()


def get_global_stats() -> GlobalStats:
    """获取全局统计单例"""
    return _global_stats


# ============================================================
# 便捷函数
# ============================================================

def create_tracer(query: str = "", session_id: str = "",
                  agent_type: str = "react", model: str = "default") -> RequestTracer:
    """创建请求追踪器（便捷函数）"""
    return RequestTracer(
        query=query,
        session_id=session_id,
        agent_type=agent_type,
        model=model,
    )


def export_metrics_json(metrics: RequestMetrics, filepath: str) -> None:
    """
    导出请求指标为JSON文件

    Args:
        metrics: 请求指标
        filepath: 输出文件路径
    """
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(metrics.to_dict(), f, ensure_ascii=False, indent=2)
    logger.info(f"指标已导出: {filepath}")


# ============================================================
# 模块自测
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("可观测性模块自测")
    print("=" * 60)

    # 测试请求追踪
    print("\n【测试请求追踪】")
    with create_tracer(query="帮我查一下今天的天气", session_id="test_001",
                       agent_type="react", model="gpt-4o-mini") as tracer:
        # 模拟LLM第一轮
        tracer.add_llm_round(prompt_tokens=150, completion_tokens=30,
                              duration=0.8, tool_call="Search")
        # 模拟工具调用
        tracer.add_tool_call("Search", "成都天气", "晴，25度", 0.23, True, risk_level="READ")
        # 模拟LLM第二轮
        tracer.add_llm_round(prompt_tokens=200, completion_tokens=50, duration=1.2)

    # 查看指标
    print(f"\n请求指标:")
    metrics_dict = tracer.metrics.to_dict()
    for key, value in metrics_dict.items():
        if key != "tool_details":
            print(f"  {key}: {value}")

    # 测试全局统计
    print("\n【测试全局统计】")
    stats = get_global_stats()
    summary = stats.get_summary()
    print(f"  总请求数: {summary['total_requests']}")
    print(f"  成功率: {summary['success_rate']}")
    print(f"  总token: {summary['total_tokens']}")
    print(f"  平均耗时: {summary['avg_duration_ms']}ms")
    print(f"  工具统计: {summary['tool_stats']}")

    # 测试成本估算
    print("\n【测试成本估算】")
    cost = estimate_cost("gpt-4o", 1000, 500)
    print(f"  GPT-4o (1000输入+500输出): ${cost:.4f}")
    cost2 = estimate_cost("gpt-4o-mini", 1000, 500)
    print(f"  GPT-4o-mini (1000输入+500输出): ${cost2:.6f}")

    print("\n" + "=" * 60)
    print("自测完成")
    print("=" * 60)
