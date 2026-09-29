# -*- coding: utf-8 -*-
"""
api.py - FastAPI REST接口
=============================================
提供非流式问答、健康检查、工具列表、记忆管理等REST API
"""

from typing import Dict, List, Optional
from loguru import logger
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from server.schemas import (
    ChatRequest, ChatResponse, ToolCallRecord,
    HealthResponse, ToolInfo,
    MemoryAddRequest, MemoryQueryRequest, MemoryResponse,
)
from server.auth import router as auth_router, get_current_user


class APIServer:
    """
    FastAPI REST API服务器

    封装Agent和记忆管理器，提供HTTP接口
    """

    def __init__(self, agent_manager):
        """
        Args:
            agent_manager: Agent管理器（包含agent、planner、memory等）
        """
        self.manager = agent_manager
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""
        app = FastAPI(
            title="AI Agent助手 API",
            description="基于LangChain + LangGraph的多功能AI Agent",
            version="1.0.0",
        )

        # CORS配置（允许前端跨域访问）
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # JWT认证路由（技术栈2.1：注册/登录/刷新/当前用户）
        app.include_router(auth_router)

        # ---------- 健康检查（公开） ----------
        @app.get("/api/health", response_model=HealthResponse)
        async def health():
            return HealthResponse()

        # ---------- 非流式问答（需认证） ----------
        @app.post("/api/chat", response_model=ChatResponse)
        async def chat(
            request: ChatRequest,
            current_user=Depends(get_current_user),
        ):
            try:
                result = self.manager.run_agent(
                    query=request.message,
                    session_id=request.session_id,
                    agent_type=request.agent_type,
                )

                # 转换工具调用记录
                tool_calls = [
                    ToolCallRecord(
                        tool=tc.get("tool", ""),
                        tool_input=tc.get("tool_input", ""),
                        output=tc.get("output", ""),
                        duration=tc.get("duration"),
                    )
                    for tc in result.get("tool_calls", [])
                ]

                return ChatResponse(
                    answer=result.get("answer", ""),
                    tool_calls=tool_calls,
                    thinking_process=result.get("thinking_process", ""),
                    session_id=request.session_id,
                )

            except Exception as e:
                logger.error(f"API聊天失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # ---------- 获取工具列表（需认证） ----------
        @app.get("/api/tools", response_model=List[ToolInfo])
        async def list_tools(current_user=Depends(get_current_user)):
            return [
                ToolInfo(name=t.name, description=t.description)
                for t in self.manager.tools
            ]

        # ---------- 添加记忆（需认证） ----------
        @app.post("/api/memory", response_model=MemoryResponse)
        async def add_memory(
            request: MemoryAddRequest,
            current_user=Depends(get_current_user),
        ):
            try:
                success = self.manager.memory.add_long_term_fact(
                    content=request.content,
                    fact_type=request.fact_type,
                    source="api",
                )
                return MemoryResponse(
                    facts=[{"content": request.content, "stored": success}],
                    total=self.manager.memory._long_term.count,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        # ---------- 查询记忆（需认证） ----------
        @app.get("/api/memory", response_model=MemoryResponse)
        async def query_memory(
            query: str,
            top_k: int = 3,
            current_user=Depends(get_current_user),
        ):
            try:
                facts = self.manager.memory.search_long_term(query, top_k)
                return MemoryResponse(facts=facts, total=len(facts))
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        # ---------- 记忆统计（需认证） ----------
        @app.get("/api/memory/stats")
        async def memory_stats(current_user=Depends(get_current_user)):
            return self.manager.memory.get_stats()

        return app


def create_app(agent_manager) -> FastAPI:
    """创建FastAPI应用的工厂函数"""
    server = APIServer(agent_manager)
    return server.app
