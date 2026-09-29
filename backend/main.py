# -*- coding: utf-8 -*-
"""
main.py - 项目主入口（命令行工具）
=============================================
功能：统一入口，串联Agent交互、服务启动、评估等功能

使用方式：
  python main.py chat                    # 命令行交互聊天
  python main.py serve                   # 启动FastAPI + WebSocket服务
  python main.py web                     # 启动Gradio前端
  python main.py eval                    # 运行评估测试集
  python main.py init-db                 # 创建示例数据库
  python main.py tools                   # 查看可用工具列表
"""

import os
import sys
import argparse

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from loguru import logger


def cmd_chat(args):
    """命令行交互聊天"""
    from agent_manager import get_agent_manager

    manager = get_agent_manager()
    agent_type = args.agent_type
    session_id = args.session_id

    print("=" * 60)
    print(f"AI Agent助手（{agent_type}模式）")
    print("输入问题开始对话，输入 'quit' 或 'exit' 退出")
    print("输入 'tools' 查看可用工具，输入 'memory' 查看记忆状态")
    print("=" * 60)

    while True:
        try:
            query = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "退出"):
            break
        if query.lower() == "tools":
            print("\n可用工具:")
            for t in manager.tools:
                print(f"  - {t.name}: {t.description[:80]}...")
            continue
        if query.lower() == "memory":
            stats = manager.memory.get_stats(session_id)
            print(f"\n记忆状态: {stats}")
            continue

        print("\nAgent: 思考中...")
        result = manager.run_agent(query, session_id=session_id, agent_type=agent_type)

        # 打印工具调用
        tool_calls = result.get("tool_calls", [])
        if tool_calls:
            print(f"\n[工具调用] ({len(tool_calls)}次)")
            for tc in tool_calls:
                print(f"  → {tc.get('tool', '?')}: {str(tc.get('tool_input', ''))[:60]}")

        print(f"\n{result.get('answer', '')}")

    print("\n再见！")


def cmd_serve(args):
    """启动FastAPI + WebSocket服务"""
    import uvicorn
    from agent_manager import get_agent_manager
    from server.api import create_app
    from server.websocket_handler import setup_websocket
    from database import init_db

    # 确保认证数据库表存在（幂等）
    init_db()

    manager = get_agent_manager()
    app = create_app(manager)
    setup_websocket(app, manager)

    logger.info(f"启动API服务: http://{args.host}:{args.port}")
    logger.info(f"  REST API: http://{args.host}:{args.port}/api/chat")
    logger.info(f"  WebSocket: ws://{args.host}:{args.port}/ws")
    logger.info(f"  文档: http://{args.host}:{args.port}/docs")

    uvicorn.run(app, host=args.host, port=args.port)


def cmd_web(args):
    """启动Gradio前端"""
    from agent_manager import get_agent_manager
    from frontend.gradio_app import launch_gradio

    manager = get_agent_manager()
    launch_gradio(manager, host=args.host, port=args.port)


def cmd_eval(args):
    """运行评估"""
    from agent_manager import get_agent_manager
    from evaluator import AgentEvaluator

    manager = get_agent_manager()
    evaluator = AgentEvaluator(manager, test_data_path=args.test_data)
    evaluator.run_evaluation(output_dir=args.output_dir)


def cmd_init_db(args):
    """创建示例数据库（业务SQL查询用）"""
    from create_sample_db import create_sample_db
    create_sample_db(args.path)


def cmd_db_init(args):
    """初始化认证数据库（users表，JWT认证用，技术栈2.1）"""
    from database import init_db
    init_db()
    print("认证数据库初始化完成（users表）")


def cmd_tools(args):
    """查看可用工具"""
    from agent_manager import get_agent_manager
    manager = get_agent_manager()
    print("可用工具列表:")
    for i, t in enumerate(manager.tools, 1):
        print(f"\n{i}. {t.name}")
        print(f"   {t.description}")


def main():
    parser = argparse.ArgumentParser(
        description="AI Agent助手 - 命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ---------- chat ----------
    p_chat = subparsers.add_parser("chat", help="命令行交互聊天")
    p_chat.add_argument("--agent_type", default="react",
                        choices=["react", "langgraph", "planner"],
                        help="Agent类型")
    p_chat.add_argument("--session_id", default="cli_session")
    p_chat.set_defaults(func=cmd_chat)

    # ---------- serve ----------
    p_serve = subparsers.add_parser("serve", help="启动FastAPI + WebSocket服务")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    # ---------- web ----------
    p_web = subparsers.add_parser("web", help="启动Gradio前端")
    p_web.add_argument("--host", default="0.0.0.0")
    p_web.add_argument("--port", type=int, default=7860)
    p_web.set_defaults(func=cmd_web)

    # ---------- eval ----------
    p_eval = subparsers.add_parser("eval", help="运行评估测试集")
    p_eval.add_argument("--test_data", default="tests/eval_tasks.json")
    p_eval.add_argument("--output_dir", default="eval_results")
    p_eval.set_defaults(func=cmd_eval)

    # ---------- init-db ----------
    p_db = subparsers.add_parser("init-db", help="创建示例SQLite数据库")
    p_db.add_argument("--path", default="data/example.db")
    p_db.set_defaults(func=cmd_init_db)

    # ---------- db-init ----------
    p_db_init = subparsers.add_parser("db-init", help="初始化认证数据库（users表，JWT认证用）")
    p_db_init.set_defaults(func=cmd_db_init)

    # ---------- tools ----------
    p_tools = subparsers.add_parser("tools", help="查看可用工具列表")
    p_tools.set_defaults(func=cmd_tools)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
