# -*- coding: utf-8 -*-
"""
websocket_handler.py - WebSocket实时通信（Agent Execution Trace协议）
=============================================
端点：/ws
客户端发送：{"type": "message", "content": "...", "session_id": "...", "agent_type": "react"}
服务端推送事件（Agent Execution Trace，不暴露LLM内部CoT）：
  - plan: Agent规划任务时
  - tool_start: 工具调用开始
  - tool_end: 工具调用结束
  - status: Agent状态变化（thinking/executing/generating）
  - token: LLM流式token
  - approval_required: 高风险操作需人工确认（Human-in-the-loop）
  - done: 任务完成
  - error: 发生错误
"""

import json
import asyncio
from typing import Dict, Set, Optional
from loguru import logger
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from agent.react_agent import AgentCallback
from server.schemas import WSEvent
from server.auth import verify_ws_token


class WebSocketCallback(AgentCallback):
    """
    WebSocket回调：将Agent执行轨迹事件推送到前端

    在独立线程中运行Agent，通过asyncio将事件发送到WebSocket。
    采用Agent Execution Trace协议，只推送结构化执行事件，
    不暴露LLM内部Chain-of-Thought。
    """

    def __init__(self, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
        """
        Args:
            websocket: WebSocket连接
            loop: 主事件循环（用于跨线程发送）
        """
        self.websocket = websocket
        self.loop = loop
        self.tool_calls = []

    def _send(self, event_type: str, content: str = "", data: dict = None):
        """线程安全地发送事件"""
        event = {"type": event_type, "content": content}
        if data:
            event["data"] = data

        # Agent在同步线程中运行，需要通过run_coroutine_threadsafe发送
        asyncio.run_coroutine_threadsafe(
            self.websocket.send_json(event),
            self.loop,
        )

    def on_plan(self, plan: str) -> None:
        """Agent规划任务时调用（替代原on_thought，不暴露内部CoT）"""
        self._send("plan", plan)

    def on_status(self, status: str, detail: str = "") -> None:
        """Agent状态变化时调用"""
        self._send("status", status, {"detail": detail})

    def on_tool_start(self, tool_name: str, tool_input, risk_level: str = "READ") -> None:
        self._send("tool_start", tool_name, {
            "input": str(tool_input)[:500],
            "risk_level": risk_level,
        })

    def on_tool_end(self, tool_name: str, tool_input, output: str, duration: float) -> None:
        record = {
            "tool": tool_name,
            "input": str(tool_input)[:500],
            "output": output[:1000],
            "duration": round(duration, 2),
        }
        self.tool_calls.append(record)
        self._send("tool_end", tool_name, record)

    def on_approval_required(self, tool_name: str, tool_input, risk_level: str = "DANGEROUS") -> None:
        """高风险操作需人工确认时调用（Human-in-the-loop）"""
        self._send("approval_required", tool_name, {
            "input": str(tool_input)[:500],
            "risk_level": risk_level,
        })

    def on_token(self, token: str) -> None:
        self._send("token", token)

    def on_error(self, error: str) -> None:
        self._send("error", error)

    def on_finish(self, answer: str) -> None:
        pass  # done事件由主流程发送


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket连接建立，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket连接断开，当前连接数: {len(self.active_connections)}")


def setup_websocket(app: FastAPI, agent_manager):
    """
    在FastAPI应用上注册WebSocket端点

    Args:
        app: FastAPI应用
        agent_manager: Agent管理器
    """
    manager = ConnectionManager()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        # JWT认证（技术栈2.1）：从query参数校验Token，失败则拒绝连接
        token = websocket.query_params.get("token", "")
        user = verify_ws_token(token) if token else None
        if user is None:
            await websocket.close(code=4401, reason="未认证：请在连接URL中携带 ?token=<access_token>")
            return

        await manager.connect(websocket)
        loop = asyncio.get_event_loop()

        try:
            while True:
                # 接收客户端消息
                raw = await websocket.receive_text()

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "content": "无效的JSON格式"})
                    continue

                msg_type = data.get("type", "message")

                if msg_type == "stop":
                    await websocket.send_json({"type": "done", "content": "已停止"})
                    continue

                if msg_type == "approve":
                    # Human-in-the-loop：用户确认高风险操作
                    tool_name = data.get("tool_name", "")
                    logger.info(f"用户确认执行高风险操作: {tool_name}")
                    # 这里可以通过agent_manager通知Agent继续执行
                    continue

                if msg_type == "reject":
                    # Human-in-the-loop：用户拒绝高风险操作
                    tool_name = data.get("tool_name", "")
                    logger.info(f"用户拒绝执行高风险操作: {tool_name}")
                    await websocket.send_json({"type": "status", "content": "操作已被用户取消"})
                    continue

                if msg_type != "message":
                    continue

                content = data.get("content", "").strip()
                session_id = data.get("session_id", "default")
                agent_type = data.get("agent_type", "react")

                if not content:
                    await websocket.send_json({"type": "error", "content": "消息不能为空"})
                    continue

                # 创建WebSocket回调
                ws_callback = WebSocketCallback(websocket, loop)

                # 在后台线程中运行Agent（避免阻塞事件循环）
                def run_agent():
                    try:
                        # 发送状态变化
                        ws_callback.on_status("thinking", "Agent正在分析问题")

                        result = agent_manager.run_agent(
                            query=content,
                            session_id=session_id,
                            agent_type=agent_type,
                            extra_callbacks=[ws_callback],
                        )
                        # 发送完成事件
                        answer = result.get("answer", "")
                        ws_callback.on_status("done", "任务完成")
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_json({
                                "type": "done",
                                "content": answer,
                                "data": {
                                    "tool_calls": ws_callback.tool_calls,
                                    "iterations": len(ws_callback.tool_calls),
                                }
                            }),
                            loop,
                        )
                    except Exception as e:
                        logger.error(f"WebSocket Agent执行失败: {e}")
                        asyncio.run_coroutine_threadsafe(
                            websocket.send_json({"type": "error", "content": str(e)}),
                            loop,
                        )

                # 启动后台线程
                import threading
                thread = threading.Thread(target=run_agent, daemon=True)
                thread.start()

        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"WebSocket错误: {e}")
            manager.disconnect(websocket)
