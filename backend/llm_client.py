# -*- coding: utf-8 -*-
"""
llm_client.py - 多Provider LLM客户端（技术栈2.1：自动降级）
=============================================
功能：
  1. 从 config.llm.providers 构建可用Provider列表（api_key非空，按priority排序）
  2. create_model() 创建OpenAI兼容 ChatOpenAI 实例
  3. LLMRouter 统一路由：调用失败自动切换到下一个Provider重试
  4. Agent 绑定工具、流式等场景均通过 Router 创建模型
"""

import time
from typing import List, Optional, Dict, Any
from loguru import logger

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage


class LLMRouter:
    """
    多Provider路由与自动降级

    用法：
      router = LLMRouter(config)
      llm = router.create_model()          # 当前Provider的ChatOpenAI
      router.invoke(messages)              # 带自动降级的调用
      router.next_provider()               # 手动切换到下一个Provider
    """

    def __init__(self, config):
        self.config = config
        # 可用Provider：已配置API Key的，按priority升序
        self.providers = config.llm.available_providers()
        if not self.providers:
            logger.warning("未配置任何可用Provider的API Key，LLM调用将失败")
        self._index = 0

    # ---------- 基础属性 ----------
    @property
    def current_provider(self) -> Optional[Any]:
        if self.providers:
            return self.providers[self._index]
        return None

    @property
    def provider_name(self) -> str:
        p = self.current_provider
        return p.name if p else "none"

    def next_provider(self) -> bool:
        """切换到下一个Provider，返回是否还有可切换的"""
        if self._index < len(self.providers) - 1:
            self._index += 1
            logger.info(f"LLM降级到Provider: {self.current_provider.name} "
                        f"(模型: {self.current_provider.model})")
            return True
        return False

    def reset(self) -> None:
        """重置到优先级最高的Provider"""
        self._index = 0

    def provider_count(self) -> int:
        return len(self.providers)

    # ---------- 模型创建 ----------
    def create_model(
        self,
        provider: Optional[Any] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        streaming: Optional[bool] = None,
        bind_tools: Optional[List[Any]] = None,
    ) -> ChatOpenAI:
        """
        创建OpenAI兼容ChatOpenAI实例

        Args:
            provider: 指定Provider（默认当前Provider）
            temperature: 覆盖全局温度
            max_tokens: 覆盖全局max_tokens
            streaming: 覆盖全局streaming
            bind_tools: 如需绑定工具（LangGraph Agent用）

        Returns:
            ChatOpenAI: 模型实例
        """
        p = provider or self.current_provider
        if p is None:
            raise RuntimeError("没有可用的LLM Provider（请配置API Key环境变量）")

        model = ChatOpenAI(
            model=p.model,
            api_key=p.api_key,
            base_url=p.base_url,
            temperature=temperature if temperature is not None else self.config.llm.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.config.llm.max_tokens,
            timeout=self.config.llm.request_timeout,
            streaming=streaming if streaming is not None else self.config.llm.streaming,
        )
        if bind_tools:
            model = model.bind_tools(bind_tools)
        return model

    # ---------- 带自动降级的调用 ----------
    def invoke(
        self,
        messages: List[BaseMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        retries: int = 1,
    ) -> Any:
        """
        调用LLM，失败时自动降级到下一个Provider并重试

        Args:
            messages: 消息列表
            temperature: 覆盖温度
            max_tokens: 覆盖max_tokens
            retries: 每个Provider内的重试次数（应对瞬时错误）

        Returns:
            AIMessage: 模型回复
        """
        if not self.providers:
            raise RuntimeError("没有可用的LLM Provider（请配置API Key环境变量）")

        start_index = self._index
        last_error: Optional[Exception] = None

        # 从当前Provider开始，遍历所有可用Provider
        for offset in range(len(self.providers)):
            idx = (start_index + offset) % len(self.providers)
            provider = self.providers[idx]
            self._index = idx

            for attempt in range(retries + 1):
                try:
                    model = self.create_model(
                        provider=provider,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    resp = model.invoke(messages)
                    logger.debug(f"LLM调用成功: {provider.name}/{provider.model}")
                    return resp
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"LLM调用失败 Provider={provider.name} 模型={provider.model} "
                        f"尝试={attempt + 1}: {str(e)[:200]}"
                    )
                    if attempt < retries:
                        time.sleep(1)  # 瞬时错误短暂等待后重试
                        continue
                    break

        # 全部Provider失败
        raise RuntimeError(f"所有LLM Provider均调用失败: {last_error}")

    # ---------- 便捷方法 ----------
    def get_primary_model(self, **kwargs) -> ChatOpenAI:
        """获取优先级最高的Provider模型（不降级，用于Agent绑定）"""
        if not self.providers:
            raise RuntimeError("没有可用的LLM Provider（请配置API Key环境变量）")
        return self.create_model(provider=self.providers[0], **kwargs)


def get_llm_router(config) -> LLMRouter:
    """获取LLM路由（多Provider自动降级）"""
    return LLMRouter(config)


def create_agent_llm(config, bind_tools: Optional[List[Any]] = None) -> ChatOpenAI:
    """
    为Agent创建LLM（取优先级最高的可用Provider）

    Args:
        config: 应用配置
        bind_tools: 需要绑定的工具列表

    Returns:
        ChatOpenAI: 绑定后的模型实例
    """
    router = LLMRouter(config)
    return router.create_model(bind_tools=bind_tools)
