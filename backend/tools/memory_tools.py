# -*- coding: utf-8 -*-
"""
memory_tools.py - 记忆操作工具
=============================================
功能：
  - RememberFact: 将重要事实存入长期记忆
  - RecallFact: 从长期记忆检索相关事实
这两个工具供Agent调用，实现跨会话记忆能力
"""

from loguru import logger


def remember_fact(fact_text: str, memory_manager) -> str:
    """
    将事实存入长期记忆（供Agent作为工具调用）

    Args:
        fact_text: 要记住的事实内容
        memory_manager: 记忆管理器实例

    Returns:
        str: 存储结果
    """
    if not fact_text or not fact_text.strip():
        return "错误: 事实内容不能为空"

    try:
        success = memory_manager.add_long_term_fact(
            content=fact_text.strip(),
            source="agent_conversation",
            fact_type="user_fact",
        )
        if success:
            logger.info(f"事实已存入长期记忆: {fact_text[:50]}")
            return f"已记住: {fact_text.strip()}"
        else:
            return "该事实与已有记忆高度相似，未重复存储"
    except Exception as e:
        logger.error(f"存储记忆失败: {e}")
        return f"记忆存储失败: {e}"


def recall_fact(query: str, memory_manager) -> str:
    """
    从长期记忆检索相关事实（供Agent作为工具调用）

    Args:
        query: 检索查询
        memory_manager: 记忆管理器实例

    Returns:
        str: 检索到的相关事实
    """
    if not query or not query.strip():
        return "错误: 查询内容不能为空"

    try:
        facts = memory_manager.search_long_term(query.strip(), top_k=3)

        if not facts:
            return "长期记忆中没有找到相关事实。"

        result_parts = ["从长期记忆中检索到以下事实:"]
        for i, fact in enumerate(facts):
            result_parts.append(f"  {i+1}. {fact['content']}")

        return "\n".join(result_parts)
    except Exception as e:
        logger.error(f"检索记忆失败: {e}")
        return f"记忆检索失败: {e}"
