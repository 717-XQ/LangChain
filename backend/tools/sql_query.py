# -*- coding: utf-8 -*-
"""
sql_query.py - SQL数据库查询工具
=============================================
功能：执行只读SQL查询，返回格式化结果
安全限制：
  - 只允许SELECT语句
  - 禁止INSERT/UPDATE/DELETE/DROP/ALTER/CREATE等写操作
  - 限制返回行数
"""

import re
from typing import List, Dict, Any
from loguru import logger

from sqlalchemy import create_engine, text, inspect
from langchain_core.tools import Tool


# 禁止的SQL关键字（写操作）
FORBIDDEN_SQL_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "TRUNCATE", "REPLACE", "GRANT", "REVOKE", "ATTACH",
    "DETACH", "PRAGMA", "VACUUM",
}


def _is_read_only_query(sql: str) -> bool:
    """
    检查SQL是否为只读查询

    Args:
        sql: SQL语句

    Returns:
        bool: 是否只读
    """
    # 去除注释和空白，转大写
    sql_clean = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    sql_clean = re.sub(r"/\*.*?\*/", "", sql_clean, flags=re.DOTALL)
    sql_upper = sql_clean.strip().upper()

    # 必须以SELECT或WITH开头
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return False

    # 检查是否包含禁止关键字
    for keyword in FORBIDDEN_SQL_KEYWORDS:
        # 使用单词边界匹配
        if re.search(r"\b" + keyword + r"\b", sql_upper):
            return False

    return True


def _get_engine():
    """获取数据库引擎（延迟初始化）"""
    from config import get_config
    config = get_config()

    engine = create_engine(
        config.tools.sql_query.database_uri,
        echo=False,
    )
    return engine


def get_sql_schema() -> str:
    """
    获取数据库Schema信息（表名、字段、类型）

    Returns:
        str: 格式化的表结构信息
    """
    try:
        engine = _get_engine()
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        if not tables:
            return "数据库中没有表。"

        schema_parts = ["数据库表结构:"]
        for table_name in tables:
            columns = inspector.get_columns(table_name)
            schema_parts.append(f"\n表: {table_name}")
            for col in columns:
                col_type = str(col["type"])
                pk = " [主键]" if col.get("primary_key") else ""
                nullable = "" if col.get("nullable", True) else " [非空]"
                schema_parts.append(f"  - {col['name']} ({col_type}){pk}{nullable}")

        return "\n".join(schema_parts)

    except Exception as e:
        logger.error(f"获取数据库Schema失败: {e}")
        return f"获取数据库结构失败: {e}"


def sql_query(sql: str) -> str:
    """
    执行只读SQL查询

    Args:
        sql: SQL SELECT语句

    Returns:
        str: 格式化的查询结果（表格形式）
    """
    from config import get_config
    config = get_config()
    max_rows = config.tools.sql_query.max_rows

    logger.info(f"SQL查询: {sql[:100]}")

    # 安全检查
    if not _is_read_only_query(sql):
        return ("错误: 只允许执行SELECT查询语句。"
                "禁止INSERT/UPDATE/DELETE/DROP/ALTER/CREATE等写操作。")

    try:
        engine = _get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchmany(max_rows + 1)  # 多取一行判断是否截断

            if not rows:
                return "查询完成，返回0行数据。"

            # 获取列名
            columns = list(result.keys())

            # 格式化输出
            truncated = len(rows) > max_rows
            display_rows = rows[:max_rows]

            # 计算列宽
            col_widths = [len(str(col)) for col in columns]
            for row in display_rows:
                for i, val in enumerate(row):
                    col_widths[i] = max(col_widths[i], len(str(val)))

            # 构建表格
            header = " | ".join(
                str(col).ljust(col_widths[i]) for i, col in enumerate(columns)
            )
            separator = "-+-".join("-" * w for w in col_widths)
            data_lines = []
            for row in display_rows:
                data_lines.append(" | ".join(
                    str(val).ljust(col_widths[i]) for i, val in enumerate(row)
                ))

            output = f"{header}\n{separator}\n" + "\n".join(data_lines)
            output += f"\n\n共 {len(display_rows)} 行"
            if truncated:
                output += f"（结果已截断，最多显示{max_rows}行）"

            logger.info(f"SQL查询完成，返回{len(display_rows)}行")
            return output

    except Exception as e:
        logger.error(f"SQL查询失败: {e}")
        return f"SQL查询错误: {e}"


# LangChain工具对象（在__init__.py中创建，这里提供函数）
def get_sql_tool() -> Tool:
    """获取SQL查询工具"""
    return Tool(
        name="SQLQuery",
        func=sql_query,
        description="查询SQL数据库。输入SQL SELECT语句，返回格式化的查询结果。"
                    "使用前可先调用GetDBSchema查看表结构。仅支持SELECT查询。"
    )


# 模块测试
if __name__ == "__main__":
    print(get_sql_schema())
    print()
    print(sql_query("SELECT name FROM sqlite_master WHERE type='table'"))
