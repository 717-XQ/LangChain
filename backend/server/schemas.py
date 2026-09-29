# -*- coding: utf-8 -*-
"""
schemas.py - 请求/响应数据模型
=============================================
定义REST API和WebSocket的Pydantic模型
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# ============================================================
# REST API 模型
# ============================================================

class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户输入消息", min_length=1)
    session_id: str = Field(default="default", description="会话ID")
    agent_type: str = Field(default="react", description="Agent类型: react/langgraph/planner")


class ToolCallRecord(BaseModel):
    """工具调用记录"""
    tool: str = Field(..., description="工具名称")
    tool_input: Any = Field(default="", description="输入参数")
    output: str = Field(default="", description="输出结果")
    duration: Optional[float] = Field(default=None, description="执行耗时(秒)")


class ChatResponse(BaseModel):
    """聊天响应"""
    answer: str = Field(..., description="Agent回答")
    tool_calls: List[ToolCallRecord] = Field(default_factory=list, description="工具调用记录")
    thinking_process: str = Field(default="", description="思考过程")
    session_id: str = Field(default="default")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    version: str = "1.0.0"


class ToolInfo(BaseModel):
    """工具信息"""
    name: str
    description: str


class MemoryAddRequest(BaseModel):
    """手动添加记忆请求"""
    content: str = Field(..., description="事实内容", min_length=1)
    fact_type: str = Field(default="manual", description="事实类型")
    session_id: str = Field(default="default")


class MemoryQueryRequest(BaseModel):
    """查询记忆请求"""
    query: str = Field(..., description="查询关键词")
    top_k: int = Field(default=3, ge=1, le=10)


class MemoryResponse(BaseModel):
    """记忆响应"""
    facts: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


# ============================================================
# 认证 模型（技术栈2.1：JWT）
# ============================================================

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=64, description="用户名（3-64字符）")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码（至少6位）")


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class RefreshRequest(BaseModel):
    """刷新Token请求"""
    refresh_token: str = Field(..., description="刷新Token")


class UserInfo(BaseModel):
    """用户信息"""
    id: int
    username: str
    email: str


class TokenResponse(BaseModel):
    """Token响应（技术栈2.1：JWT访问+刷新）"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(default=1800, description="访问Token有效期（秒）")
    user: UserInfo


# ============================================================
# WebSocket 消息模型
# ============================================================

class WSMessage(BaseModel):
    """WebSocket客户端消息"""
    type: str = Field(..., description="消息类型: message/stop")
    content: str = Field(default="", description="消息内容")
    session_id: str = Field(default="default")
    agent_type: str = Field(default="react")


class WSEvent(BaseModel):
    """WebSocket服务端事件"""
    type: str = Field(..., description="事件类型: token/tool_start/tool_end/thought/done/error")
    content: str = Field(default="")
    data: Optional[Dict[str, Any]] = None
