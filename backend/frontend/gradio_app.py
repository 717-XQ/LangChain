# -*- coding: utf-8 -*-
"""
gradio_app.py - Gradio前端界面
=============================================
功能：
  - 聊天界面（消息列表、输入框）
  - 推理过程展示（可展开/收起）
  - 工具调用链路可视化
  - 流式输出效果
  - 会话管理
  - Agent模式切换（ReAct/LangGraph/Planner）
"""

import uuid
from typing import List, Tuple, Optional
from loguru import logger

import gradio as gr

from agent.react_agent import AgentCallback
from agent_manager import AgentManager


class GradioCallback(AgentCallback):
    """
    Gradio回调：收集Agent事件，供前端展示

    由于Gradio的yield机制，这里将事件收集到列表中
    """

    def __init__(self):
        self.events = []
        self.tool_calls = []
        self.current_thought = ""

    def on_thought(self, thought: str) -> None:
        self.events.append(("thought", thought))
        self.current_thought = thought

    def on_tool_start(self, tool_name: str, tool_input) -> None:
        self.events.append(("tool_start", tool_name, str(tool_input)))

    def on_tool_end(self, tool_name: str, tool_input, output: str, duration: float) -> None:
        record = {
            "tool": tool_name,
            "input": str(tool_input)[:300],
            "output": output[:500],
            "duration": round(duration, 2),
        }
        self.tool_calls.append(record)
        self.events.append(("tool_end", tool_name, output, duration))

    def on_error(self, error: str) -> None:
        self.events.append(("error", error))

    def on_finish(self, answer: str) -> None:
        self.events.append(("finish", answer))


def format_tool_calls(tool_calls: List[dict]) -> str:
    """将工具调用记录格式化为可展示的Markdown"""
    if not tool_calls:
        return ""

    parts = ["### 工具调用链路\n"]
    for i, tc in enumerate(tool_calls, 1):
        tool_name = tc.get("tool", tc.get("name", "未知工具"))
        tool_input = str(tc.get("tool_input", tc.get("input", "")))[:100]
        tool_output = str(tc.get("output", tc.get("result", "")))[:200]
        duration = tc.get("duration", "?")
        parts.append(f"**{i}. {tool_name}** ({duration}s)")
        parts.append(f"- 输入: `{tool_input}`")
        parts.append(f"- 输出: {tool_output}")
        parts.append("")

    return "\n".join(parts)


def create_gradio_app(manager: AgentManager) -> gr.Blocks:
    """
    创建Gradio应用

    Args:
        manager: Agent管理器

    Returns:
        gr.Blocks: Gradio应用
    """

    def chat_response(
        message: str,
        history: List[Tuple[str, str]],
        session_id: str,
        agent_type: str,
    ):
        """
        处理聊天消息并生成响应

        Yields:
            更新后的聊天历史和工具调用信息
        """
        if not message.strip():
            yield history, "", ""
            return

        # 添加用户消息到历史
        history = history + [(message, "")]

        # 创建回调收集事件
        callback = GradioCallback()

        # 运行Agent
        try:
            result = manager.run_agent(
                query=message,
                session_id=session_id,
                agent_type=agent_type,
                extra_callbacks=[callback],
            )
            answer = result.get("answer", "")
            tool_calls = result.get("tool_calls", [])

        except Exception as e:
            answer = f"处理时发生错误: {str(e)}"
            tool_calls = []
            logger.error(f"Gradio聊天错误: {e}")

        # 更新最后一条消息（AI回复）
        history[-1] = (message, answer)

        # 格式化工具调用信息
        tool_info = format_tool_calls(tool_calls)

        yield history, tool_info, session_id

    # 生成会话ID
    default_session = str(uuid.uuid4())[:8]

    # 自定义CSS
    custom_css = """
    .tool-panel { border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px; background: #fafafa; }
    #chatbot { height: 500px; }
    """

    with gr.Blocks(title="AI Agent助手", css=custom_css, theme=gr.themes.Soft()) as app:
        gr.Markdown("# AI Agent助手")
        gr.Markdown("基于LangChain + LangGraph的多功能AI Agent | 支持联网搜索、数学计算、代码执行、SQL查询、文档问答")

        with gr.Row():
            # 左侧：聊天区
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="对话",
                    height=500,
                    show_label=False,
                )

                with gr.Row():
                    msg_input = gr.Textbox(
                        placeholder="输入你的问题...（支持多步任务，如'搜索今天新闻并总结'）",
                        show_label=False,
                        scale=4,
                    )
                    send_btn = gr.Button("发送", variant="primary", scale=1)

                with gr.Row():
                    agent_type = gr.Radio(
                        choices=["react", "langgraph", "planner"],
                        value="react",
                        label="Agent模式",
                        info="react: 快速响应 | langgraph: 有状态编排 | planner: 复杂任务规划",
                    )
                    session_id = gr.Textbox(
                        value=default_session,
                        label="会话ID",
                        scale=1,
                    )
                    clear_btn = gr.Button("新会话", scale=1)

            # 右侧：工具调用链路
            with gr.Column(scale=2):
                gr.Markdown("### 推理过程与工具调用")
                tool_output = gr.Markdown(
                    value="发送消息后，这里将展示Agent的思考过程和工具调用链路。",
                    elem_classes=["tool-panel"],
                )

        # 事件绑定
        send_btn.click(
            chat_response,
            inputs=[msg_input, chatbot, session_id, agent_type],
            outputs=[chatbot, tool_output, session_id],
        ).then(lambda: "", outputs=msg_input)

        msg_input.submit(
            chat_response,
            inputs=[msg_input, chatbot, session_id, agent_type],
            outputs=[chatbot, tool_output, session_id],
        ).then(lambda: "", outputs=msg_input)

        def new_session():
            return [], str(uuid.uuid4())[:8], ""

        clear_btn.click(
            new_session,
            outputs=[chatbot, session_id, tool_output],
        )

    return app


def launch_gradio(manager: AgentManager, host: str = "0.0.0.0", port: int = 7860):
    """启动Gradio前端"""
    app = create_gradio_app(manager)
    logger.info(f"启动Gradio前端: http://{host}:{port}")
    app.launch(server_name=host, server_port=port, share=False)


if __name__ == "__main__":
    from config import get_config
    config = get_config()
    manager = AgentManager(config)
    launch_gradio(manager)
