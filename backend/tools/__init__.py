# -*- coding: utf-8 -*-
"""
tools 包 - Agent工具集合
=============================================
包含6类工具：
  - search_tool: 联网搜索
  - calculator: 数学计算
  - python_executor: Python代码执行
  - sql_query: SQL数据库查询
  - doc_qa: 文档问答（RAG）
  - memory_tools: 记忆操作
"""

from tools.search_tool import get_search_tool
from tools.calculator import calculator
from tools.python_executor import python_executor
from tools.sql_query import sql_query, get_sql_schema
from tools.memory_tools import remember_fact, recall_fact
from tools.weather_tool import get_weather_tool


def get_all_tools(memory_manager=None, doc_qa_tool=None):
    """
    获取所有工具列表（供Agent绑定使用）

    Args:
        memory_manager: 记忆管理器实例（记忆工具需要）
        doc_qa_tool: 文档问答工具实例（可选，延迟初始化）

    Returns:
        list: LangChain Tool列表
    """
    from langchain_core.tools import Tool, StructuredTool
    from pydantic import BaseModel, Field

    class EmptyInput(BaseModel):
        """空输入（无参数工具使用）"""
        pass

    tools = [
        get_search_tool(),
        get_weather_tool(),
        calculator,
        python_executor,
        Tool(
            name="SQLQuery",
            func=sql_query,
            description="查询SQL数据库。输入SQL SELECT语句，返回格式化的查询结果。"
                        "使用前可先调用GetDBSchema查看表结构。仅支持SELECT查询。"
        ),
        StructuredTool(
            name="GetDBSchema",
            func=lambda **kwargs: get_sql_schema(),
            description="查看数据库的表结构信息，包括表名、字段名和字段类型。"
                        "在编写SQL查询前应先调用此工具了解数据库结构。无需输入参数。",
            args_schema=EmptyInput,
        ),
    ]

    # 文档问答工具（如果已初始化）
    if doc_qa_tool is not None:
        tools.append(doc_qa_tool)

    # 记忆工具（需要记忆管理器）
    if memory_manager is not None:
        tools.extend([
            Tool(
                name="RememberFact",
                func=lambda text: remember_fact(text, memory_manager),
                description="将重要事实存入长期记忆。输入一个事实字符串，"
                            "例如'用户偏好Python语言'。当用户提供需要记住的信息时使用。"
            ),
            Tool(
                name="RecallFact",
                func=lambda query: recall_fact(query, memory_manager),
                description="从长期记忆中检索相关事实。输入查询关键词或问题，"
                            "返回语义相关的记忆事实。当需要回忆之前对话中的信息时使用。"
            ),
        ])

    return tools
