# -*- coding: utf-8 -*-
"""
mcp_server_real.py - MCP Server 真实系统接入版
=============================================
将MCP工具接入真实系统：
  1. RAG Query → HTTP调用RAG FastAPI服务 (/chat)
  2. SQL Query → sqlite3连接测试数据库 (只读SELECT)
  3. Web Search → DuckDuckGo搜索 (duckduckgo_search库)
  4. Calculator → 本地数学计算

使用前需启动RAG服务：
  cd D:\ronghua_pythoncode\projcet\RAG
  python api.py

MCP协议标准：JSON-RPC 2.0
"""

import json
import sqlite3
import math
import re
from typing import Dict, Any, List, Optional
from loguru import logger

# 导入基础MCP Server类
import sys
sys.path.insert(0, r'D:\ronghua_pythoncode\projcet\LangChain')
from mcp_server import MCPServer, MCPTool


# ============================================================
# 真实工具实现
# ============================================================

class RealRAGTool:
    """
    真实RAG工具 - 通过HTTP调用RAG FastAPI服务

    前提：RAG服务已启动 (默认 http://localhost:8000)
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self._available = None

    def check_available(self) -> bool:
        """检查RAG服务是否可用"""
        if self._available is not None:
            return self._available
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                self._available = data.get("status") == "ok"
        except Exception as e:
            logger.warning(f"RAG服务不可用: {e}")
            self._available = False
        return self._available

    def query(self, arguments: Dict[str, Any]) -> str:
        """执行RAG查询"""
        query = arguments.get("query", "")
        if not query:
            return "错误：请提供查询问题"

        if not self.check_available():
            return (
                f"[RAG服务未启动] 查询: {query}\n"
                f"请先启动RAG服务：\n"
                f"  cd D:\\ronghua_pythoncode\\projcet\\RAG\n"
                f"  python api.py\n"
                f"服务启动后即可通过MCP调用真实RAG检索。"
            )

        try:
            import urllib.request
            payload = json.dumps({"question": query, "use_reranker": True}).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                answer = data.get("answer", "无回答")
                sources = data.get("sources", [])
                citations = "\n".join([f"  - [{s.get('source', '未知')}] {s.get('content', '')[:100]}" for s in sources[:3]])
                return (
                    f"[RAG检索结果] 查询: {query}\n"
                    f"回答: {answer}\n"
                    f"参考来源:\n{citations if citations else '  (无)'}"
                )
        except Exception as e:
            return f"[RAG查询失败] {str(e)}"


class RealSQLTool:
    """
    真实SQL工具 - sqlite3连接测试数据库（只读SELECT）

    测试数据库包含：employees, departments, projects表
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = r'D:\ronghua_pythoncode\projcet\LangChain\tests\test_company.db'
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """确保测试数据库存在并包含测试数据"""
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees'")
        if not cursor.fetchone():
            # 创建表并插入测试数据
            cursor.execute('''
                CREATE TABLE departments (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    city TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE employees (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    position TEXT,
                    salary REAL,
                    dept_id INTEGER,
                    hire_year INTEGER,
                    FOREIGN KEY (dept_id) REFERENCES departments(id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    budget REAL,
                    status TEXT
                )
            ''')

            # 插入部门数据
            departments = [
                (1, '技术部', '北京'),
                (2, '产品部', '上海'),
                (3, '市场部', '广州'),
                (4, '财务部', '深圳'),
            ]
            cursor.executemany('INSERT INTO departments VALUES (?,?,?)', departments)

            # 插入员工数据
            employees = [
                (1, '张伟', '高级工程师', 25000, 1, 2022),
                (2, '王强', '技术总监', 45000, 1, 2020),
                (3, '李娜', '产品经理', 22000, 2, 2021),
                (4, '刘洋', '市场专员', 15000, 3, 2022),
                (5, '陈静', '财务主管', 28000, 4, 2019),
                (6, '赵磊', '工程师', 18000, 1, 2023),
                (7, '孙芳', '产品助理', 12000, 2, 2023),
                (8, '周杰', '市场经理', 30000, 3, 2020),
                (9, '吴敏', '会计', 16000, 4, 2022),
                (10, '郑浩', '架构师', 38000, 1, 2018),
                (11, '冯雪', 'UI设计师', 20000, 2, 2022),
                (12, '褚明', '运维工程师', 21000, 1, 2022),
                (13, '卫龙', '数据分析师', 23000, 1, 2021),
                (14, '蒋欣', '品牌经理', 26000, 3, 2021),
                (15, '沈悦', '出纳', 14000, 4, 2023),
            ]
            cursor.executemany('INSERT INTO employees VALUES (?,?,?,?,?,?)', employees)

            # 插入项目数据
            projects = [
                (1, '智能客服系统', 800000, '进行中'),
                (2, 'APP重构项目', 1200000, '进行中'),
                (3, 'AI Agent平台', 1500000, '进行中'),
                (4, '数据中台建设', 2000000, '已完成'),
                (5, '营销活动系统', 500000, '规划中'),
            ]
            cursor.executemany('INSERT INTO projects VALUES (?,?,?,?)', projects)

            conn.commit()
            logger.info(f"测试数据库已创建: {self.db_path} (15员工/4部门/5项目)")

        conn.close()

    def query(self, arguments: Dict[str, Any]) -> str:
        """执行SQL查询（只读SELECT）"""
        query = arguments.get("query", "").strip()

        if not query:
            return "错误：请提供SQL查询语句"

        # 安全检查：只允许SELECT
        query_upper = query.upper().strip()
        if not query_upper.startswith("SELECT") and not query_upper.startswith("WITH"):
            return "[SQL安全拦截] 只允许SELECT查询，禁止DELETE/UPDATE/INSERT/DROP/ALTER等写操作"

        # 额外安全检查
        dangerous_keywords = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE"]
        for kw in dangerous_keywords:
            if re.search(r'\b' + kw + r'\b', query_upper):
                return f"[SQL安全拦截] 检测到危险关键字: {kw}，只允许只读SELECT查询"

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            if not rows:
                return f"[SQL查询结果] 查询: {query}\n返回0行结果"

            # 格式化输出
            columns = [desc[0] for desc in cursor.description]
            result_lines = [f"[SQL查询结果] 查询: {query}", f"返回{len(rows)}行结果:"]
            result_lines.append("  " + " | ".join(columns))
            result_lines.append("  " + "-+-".join(["---"] * len(columns)))

            for i, row in enumerate(rows[:20]):  # 最多显示20行
                values = [str(row[col]) for col in columns]
                result_lines.append("  " + " | ".join(values))

            if len(rows) > 20:
                result_lines.append(f"  ... 还有{len(rows) - 20}行结果未显示")

            conn.close()
            return "\n".join(result_lines)

        except sqlite3.Error as e:
            return f"[SQL执行错误] {str(e)}"
        except Exception as e:
            return f"[SQL错误] {str(e)}"


class RealSearchTool:
    """
    真实搜索工具 - DuckDuckGo搜索

    依赖：pip install duckduckgo-search
    如未安装则返回模拟结果
    """

    def __init__(self):
        self._available = None

    def check_available(self) -> bool:
        """检查搜索库是否可用"""
        if self._available is not None:
            return self._available
        try:
            from duckduckgo_search import DDGS
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def search(self, arguments: Dict[str, Any]) -> str:
        """执行网络搜索"""
        query = arguments.get("query", "")
        if not query:
            return "错误：请提供搜索关键词"

        if not self.check_available():
            return (
                f"[搜索工具未安装] 查询: {query}\n"
                f"请安装搜索库：pip install duckduckgo-search\n"
                f"安装后即可通过MCP调用真实网络搜索。"
            )

        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            if not results:
                return f"[搜索结果] 查询: {query}\n未找到相关结果"

            result_lines = [f"[搜索结果] 查询: {query}", f"找到{len(results)}条结果:"]
            for i, r in enumerate(results, 1):
                title = r.get('title', '无标题')
                body = r.get('body', '')[:150]
                href = r.get('href', '')
                result_lines.append(f"\n{i}. [{title}]({href})")
                result_lines.append(f"   {body}")

            return "\n".join(result_lines)

        except Exception as e:
            return f"[搜索失败] {str(e)}"


class RealCalculatorTool:
    """真实计算器工具 - 本地数学计算"""

    def calculate(self, arguments: Dict[str, Any]) -> str:
        """执行数学计算"""
        expression = arguments.get("expression", "")
        if not expression:
            return "错误：请提供数学表达式"

        try:
            # 安全计算：使用eval但限制命名空间
            safe_namespace = {
                'math': math,
                'sqrt': math.sqrt,
                'sin': math.sin,
                'cos': math.cos,
                'tan': math.tan,
                'log': math.log,
                'log2': math.log2,
                'log10': math.log10,
                'pi': math.pi,
                'e': math.e,
                'abs': abs,
                'round': round,
                'min': min,
                'max': max,
                'pow': pow,
                'sum': sum,
            }
            result = eval(expression, {"__builtins__": {}}, safe_namespace)
            return f"[计算结果] {expression} = {result}"
        except Exception as e:
            return f"[计算错误] {str(e)}"


# ============================================================
# 创建真实MCP Server
# ============================================================

def create_real_mcp_server(
    rag_url: str = "http://localhost:8000",
    db_path: str = None,
) -> MCPServer:
    """
    创建接入真实系统的MCP Server

    Args:
        rag_url: RAG服务地址
        db_path: 测试数据库路径

    Returns:
        MCPServer: 配置好真实工具的MCP Server
    """
    server = MCPServer(
        server_name="ai-agent-real-mcp-server",
        server_version="1.0.0",
    )

    # 初始化真实工具
    rag_tool = RealRAGTool(base_url=rag_url)
    sql_tool = RealSQLTool(db_path=db_path)
    search_tool = RealSearchTool()
    calc_tool = RealCalculatorTool()

    # 注册RAG工具
    server.register_tool_simple(
        name="rag_query",
        description="基于RAG的文档问答工具，从私有知识库中检索相关文档并生成回答。适用于查询企业内部文档、产品手册、规章制度等。需要先启动RAG服务。",
        parameters={
            "query": {"type": "string", "description": "用户的问题，应尽可能具体明确"},
        },
        handler=rag_tool.query,
    )

    # 注册SQL工具
    server.register_tool_simple(
        name="sql_query",
        description="SQL数据库查询工具，执行只读SELECT查询。测试数据库包含employees(员工)、departments(部门)、projects(项目)三张表。禁止执行DELETE/UPDATE/INSERT等写操作。",
        parameters={
            "query": {"type": "string", "description": "SQL SELECT查询语句，如 'SELECT * FROM employees'"},
        },
        handler=sql_tool.query,
    )

    # 注册搜索工具
    server.register_tool_simple(
        name="web_search",
        description="联网搜索工具，使用DuckDuckGo搜索互联网获取实时信息。适用于查询最新新闻、实时数据、公开知识等。需要安装duckduckgo-search库。",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
        },
        handler=search_tool.search,
    )

    # 注册计算器工具
    server.register_tool_simple(
        name="calculator",
        description="数学计算工具，执行数学表达式计算。支持加减乘除、幂运算、三角函数(sin/cos/tan)、对数(log/log2/log10)、平方根(sqrt)、常数(pi/e)等。",
        parameters={
            "expression": {"type": "string", "description": "数学表达式，如 '2 + 3 * 4' 或 'sin(pi/6) + cos(pi/3)'"},
        },
        handler=calc_tool.calculate,
    )

    logger.info(f"真实MCP Server创建完成，注册了 {len(server._tools)} 个真实工具")
    logger.info(f"  RAG服务: {rag_url} (可用: {rag_tool.check_available()})")
    logger.info(f"  SQL数据库: {sql_tool.db_path}")
    logger.info(f"  搜索库可用: {search_tool.check_available()}")

    return server


# ============================================================
# 模块自测
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("真实MCP Server 自测")
    print("=" * 60)

    # 创建真实MCP Server
    server = create_real_mcp_server()

    # 创建MCP Client
    from mcp_server import MCPClient
    client = MCPClient(server, client_name="test-real-client")

    # 初始化
    print("\n【1. 初始化握手】")
    init_resp = client.initialize()
    print(f"  服务器: {init_resp['result']['serverInfo']}")

    # 列出工具
    print("\n【2. 列出工具】")
    tools = client.list_tools()
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description'][:50]}...")

    # 测试SQL工具（真实数据库）
    print("\n【3. 测试SQL工具（真实数据库）】")
    result = client.call_tool("sql_query", {"query": "SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 3"})
    print(f"  {result['result']['content'][0]['text'][:300]}")

    # 测试计算器工具
    print("\n【4. 测试计算器工具】")
    result = client.call_tool("calculator", {"expression": "sin(pi/6) + cos(pi/3)"})
    print(f"  {result['result']['content'][0]['text']}")

    # 测试SQL安全拦截
    print("\n【5. 测试SQL安全拦截（DELETE应被拒绝）】")
    result = client.call_tool("sql_query", {"query": "DELETE FROM employees"})
    print(f"  {result['result']['content'][0]['text']}")

    # 测试RAG工具（如服务未启动会提示）
    print("\n【6. 测试RAG工具】")
    result = client.call_tool("rag_query", {"query": "如何配置FastAPI？"})
    print(f"  {result['result']['content'][0]['text'][:200]}")

    # 最终状态
    print("\n【7. 最终状态】")
    status = server.get_status()
    print(f"  注册工具: {status['registered_tools']}")
    print(f"  工具列表: {status['tool_names']}")

    print("\n" + "=" * 60)
    print("真实MCP Server 自测完成！")
    print("SQL和计算器工具已接入真实系统，RAG和搜索需启动对应服务/安装依赖")
    print("=" * 60)
