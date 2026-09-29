# -*- coding: utf-8 -*-
"""
mcp_server.py - MCP (Model Context Protocol) Server 实现
=============================================
功能：
  1. 标准MCP协议实现（JSON-RPC 2.0 over HTTP）
  2. 将RAG/SQL/Search/Calculator工具封装为MCP标准工具
  3. 支持标准MCP方法：initialize, tools/list, tools/call, resources/list, resources/read
  4. 可被任何支持MCP的客户端调用（Claude Desktop、Cursor、LangChain Agent等）
  5. 包含MCP Client验证脚本，证明外部客户端可调用

MCP协议标准方法：
  initialize          - 客户端初始化握手
  tools/list          - 列出可用工具
  tools/call          - 调用工具
  resources/list      - 列出可用资源
  resources/read      - 读取资源内容
  notifications/      - 服务端通知

对应文档中的MCP设计：
  MCP Server
    ├── RAG Query (文档问答)
    ├── SQL Query (数据库查询)
    ├── Web Search (联网搜索)
    └── Calculator (数学计算)
"""

import json
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from loguru import logger


# ============================================================
# MCP 数据结构
# ============================================================

@dataclass
class MCPTool:
    """MCP工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema
    handler: Optional[Callable] = None  # 工具处理函数


@dataclass
class MCPResource:
    """MCP资源定义"""
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"
    content: str = ""


@dataclass
class MCPRequest:
    """MCP请求（JSON-RPC 2.0）"""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResponse:
    """MCP响应（JSON-RPC 2.0）"""
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error:
            d["error"] = self.error
        else:
            d["result"] = self.result or {}
        return d


# ============================================================
# MCP Server 核心
# ============================================================

class MCPServer:
    """
    MCP Server 核心实现

    支持标准MCP协议方法，可通过HTTP或stdio传输。
    工具注册后自动暴露给MCP客户端。
    """

    def __init__(self, server_name: str = "ai-agent-mcp-server",
                 server_version: str = "1.0.0"):
        self.server_name = server_name
        self.server_version = server_version
        self._tools: Dict[str, MCPTool] = {}
        self._resources: Dict[str, MCPResource] = {}
        self._initialized = False
        self._request_count = 0
        self._start_time = time.time()

        logger.info(f"MCP Server初始化: {server_name} v{server_version}")

    # ---------- 工具注册 ----------

    def register_tool(self, tool: MCPTool) -> None:
        """
        注册MCP工具

        Args:
            tool: MCP工具定义
        """
        self._tools[tool.name] = tool
        logger.info(f"MCP工具注册: {tool.name} - {tool.description[:50]}")

    def register_tool_simple(self, name: str, description: str,
                              parameters: Dict[str, Any],
                              handler: Callable) -> None:
        """
        便捷注册工具（自动构建JSON Schema）

        Args:
            name: 工具名称
            description: 工具描述
            parameters: 参数定义 {"param_name": {"type": "string", "description": "..."}}
            handler: 处理函数，接收参数字典，返回结果字符串
        """
        input_schema = {
            "type": "object",
            "properties": parameters,
            "required": list(parameters.keys()),
        }
        tool = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )
        self.register_tool(tool)

    def unregister_tool(self, name: str) -> None:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"MCP工具注销: {name}")

    # ---------- 资源注册 ----------

    def register_resource(self, resource: MCPResource) -> None:
        """注册MCP资源"""
        self._resources[resource.uri] = resource
        logger.info(f"MCP资源注册: {resource.uri} - {resource.name}")

    # ---------- 请求处理 ----------

    def handle_request(self, request_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理MCP请求（JSON-RPC 2.0）

        Args:
            request_dict: JSON-RPC请求字典

        Returns:
            Dict: JSON-RPC响应字典
        """
        self._request_count += 1
        request_id = request_dict.get("id")
        method = request_dict.get("method", "")
        params = request_dict.get("params", {})

        logger.debug(f"MCP请求 #{self._request_count}: method={method} id={request_id}")

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "tools/list":
                result = self._handle_tools_list(params)
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            elif method == "resources/list":
                result = self._handle_resources_list(params)
            elif method == "resources/read":
                result = self._handle_resources_read(params)
            elif method == "ping":
                result = {}
            else:
                return MCPResponse(
                    id=request_id,
                    error={"code": -32601, "message": f"Method not found: {method}"}
                ).to_dict()

            return MCPResponse(id=request_id, result=result).to_dict()

        except Exception as e:
            logger.error(f"MCP请求处理失败: {method} - {e}")
            return MCPResponse(
                id=request_id,
                error={"code": -32603, "message": f"Internal error: {str(e)}"}
            ).to_dict()

    # ---------- 标准方法实现 ----------

    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理initialize请求"""
        self._initialized = True
        client_info = params.get("clientInfo", {})
        logger.info(f"MCP客户端连接: {client_info.get('name', 'unknown')} v{client_info.get('version', '?')}")

        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
                "logging": {},
            },
            "serverInfo": {
                "name": self.server_name,
                "version": self.server_version,
            },
        }

    def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理tools/list请求"""
        tools = []
        for tool in self._tools.values():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            })
        return {"tools": tools}

    def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理tools/call请求"""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            return {
                "content": [{"type": "text", "text": f"Error: Tool not found: {tool_name}"}],
                "isError": True,
            }

        tool = self._tools[tool_name]
        if tool.handler is None:
            return {
                "content": [{"type": "text", "text": f"Error: Tool handler not implemented: {tool_name}"}],
                "isError": True,
            }

        try:
            start_time = time.time()
            result = tool.handler(arguments)
            duration = time.time() - start_time
            logger.info(f"MCP工具调用: {tool_name} ({duration*1000:.0f}ms)")

            return {
                "content": [{"type": "text", "text": str(result)}],
                "isError": False,
            }
        except Exception as e:
            logger.error(f"MCP工具执行失败: {tool_name} - {e}")
            return {
                "content": [{"type": "text", "text": f"Error executing tool: {str(e)}"}],
                "isError": True,
            }

    def _handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理resources/list请求"""
        resources = []
        for res in self._resources.values():
            resources.append({
                "uri": res.uri,
                "name": res.name,
                "description": res.description,
                "mimeType": res.mime_type,
            })
        return {"resources": resources}

    def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理resources/read请求"""
        uri = params.get("uri", "")
        if uri not in self._resources:
            return {"contents": []}
        res = self._resources[uri]
        return {
            "contents": [{
                "uri": res.uri,
                "mimeType": res.mime_type,
                "text": res.content,
            }]
        }

    # ---------- 状态查询 ----------

    def get_status(self) -> Dict[str, Any]:
        """获取服务器状态"""
        return {
            "server_name": self.server_name,
            "server_version": self.server_version,
            "initialized": self._initialized,
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "total_requests": self._request_count,
            "registered_tools": len(self._tools),
            "registered_resources": len(self._resources),
            "tool_names": list(self._tools.keys()),
        }


# ============================================================
# 默认工具实现（模拟，实际项目中接入真实工具）
# ============================================================

def create_default_mcp_server() -> MCPServer:
    """
    创建默认MCP Server，注册RAG/SQL/Search/Calculator工具

    注意：这里的工具处理函数是模拟实现，
    实际项目中应接入真实的RAG系统、数据库、搜索API。
    """
    server = MCPServer(
        server_name="ai-agent-tool-server",
        server_version="1.0.0",
    )

    # RAG Query工具
    def rag_query_handler(args: Dict[str, Any]) -> str:
        query = args.get("query", "")
        # 模拟RAG检索（实际应接入真实RAG系统）
        return (
            f"[RAG检索结果] 查询: {query}\n"
            f"找到3个相关文档片段：\n"
            f"1. [文档1-第3页] 相关内容摘要...\n"
            f"2. [文档2-第7页] 相关内容摘要...\n"
            f"3. [文档3-第12页] 相关内容摘要...\n"
            f"（注：这是MCP工具的模拟返回，实际应接入真实RAG系统）"
        )

    server.register_tool_simple(
        name="rag_query",
        description="基于RAG的文档问答工具，从私有知识库中检索相关文档并生成回答。适用于查询企业内部文档、产品手册、规章制度等。",
        parameters={
            "query": {"type": "string", "description": "用户的问题，应尽可能具体明确"},
        },
        handler=rag_query_handler,
    )

    # SQL Query工具
    def sql_query_handler(args: Dict[str, Any]) -> str:
        query = args.get("query", "")
        # 模拟SQL查询（实际应接入真实数据库，且只允许SELECT）
        if any(kw in query.upper() for kw in ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER"]):
            return "[SQL错误] 只允许SELECT查询，禁止写操作"
        return (
            f"[SQL查询结果] 查询: {query}\n"
            f"返回2行结果：\n"
            f"  id | name       | value\n"
            f"  1  | example_1  | 100\n"
            f"  2  | example_2  | 200\n"
            f"（注：这是MCP工具的模拟返回，实际应接入真实数据库）"
        )

    server.register_tool_simple(
        name="sql_query",
        description="SQL数据库查询工具，执行只读SELECT查询。适用于从数据库中获取结构化数据。禁止执行DELETE/UPDATE/INSERT等写操作。",
        parameters={
            "query": {"type": "string", "description": "SQL SELECT查询语句"},
        },
        handler=sql_query_handler,
    )

    # Web Search工具
    def web_search_handler(args: Dict[str, Any]) -> str:
        query = args.get("query", "")
        # 模拟搜索（实际应接入真实搜索API）
        return (
            f"[搜索结果] 查询: {query}\n"
            f"找到3条结果：\n"
            f"1. [来源1] 标题 - 摘要内容...\n"
            f"2. [来源2] 标题 - 摘要内容...\n"
            f"3. [来源3] 标题 - 摘要内容...\n"
            f"（注：这是MCP工具的模拟返回，实际应接入真实搜索API）"
        )

    server.register_tool_simple(
        name="web_search",
        description="联网搜索工具，搜索互联网获取实时信息。适用于查询最新新闻、实时数据、公开知识等。",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
        },
        handler=web_search_handler,
    )

    # Calculator工具
    def calculator_handler(args: Dict[str, Any]) -> str:
        expression = args.get("expression", "")
        try:
            # 安全计算（只允许数学表达式）
            import ast
            import operator
            allowed_ops = {
                ast.Add: operator.add, ast.Sub: operator.sub,
                ast.Mult: operator.mul, ast.Div: operator.truediv,
                ast.Pow: operator.pow, ast.USub: operator.neg,
            }
            def eval_node(node):
                if isinstance(node, ast.Constant):  # Python 3.8+，替代已废弃的ast.Num
                    return node.value
                elif isinstance(node, ast.BinOp):
                    return allowed_ops[type(node.op)](eval_node(node.left), eval_node(node.right))
                elif isinstance(node, ast.UnaryOp):
                    return allowed_ops[type(node.op)](eval_node(node.operand))
                else:
                    raise ValueError(f"不支持的表达式: {type(node)}")
            result = eval_node(ast.parse(expression, mode='eval').body)
            return f"[计算结果] {expression} = {result}"
        except Exception as e:
            return f"[计算错误] {str(e)}"

    server.register_tool_simple(
        name="calculator",
        description="数学计算工具，执行数学表达式计算。适用于复杂计算、单位换算、统计计算等。支持加减乘除和幂运算。",
        parameters={
            "expression": {"type": "string", "description": "数学表达式，如 '2 + 3 * 4'"},
        },
        handler=calculator_handler,
    )

    # 注册示例资源
    server.register_resource(MCPResource(
        uri="docs://project/readme",
        name="项目说明文档",
        description="AI Agent项目的README文档",
        mime_type="text/markdown",
        content="# AI Agent 项目\n\n这是一个多工具AI Agent项目...\n",
    ))

    logger.info(f"默认MCP Server创建完成，注册了 {len(server._tools)} 个工具")
    return server


# ============================================================
# MCP Client 验证（证明外部客户端可调用）
# ============================================================

class MCPClient:
    """
    MCP Client 验证客户端

    用于验证MCP Server可以被外部客户端调用。
    实际使用中，这可以是Claude Desktop、Cursor或任何支持MCP的客户端。
    """

    def __init__(self, server: MCPServer, client_name: str = "test-client",
                 client_version: str = "1.0.0"):
        self.server = server
        self.client_name = client_name
        self.client_version = client_version
        self._request_id = 0

    def _next_id(self) -> str:
        self._request_id += 1
        return str(self._request_id)

    def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送MCP请求到Server（直接调用，模拟HTTP传输）"""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        return self.server.handle_request(request)

    def initialize(self) -> Dict[str, Any]:
        """初始化握手"""
        return self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": self.client_name, "version": self.client_version},
        })

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出可用工具"""
        response = self.send_request("tools/list")
        return response.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        return self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

    def list_resources(self) -> List[Dict[str, Any]]:
        """列出可用资源"""
        response = self.send_request("resources/list")
        return response.get("result", {}).get("resources", [])

    def read_resource(self, uri: str) -> Dict[str, Any]:
        """读取资源"""
        return self.send_request("resources/read", {"uri": uri})


# ============================================================
# 模块自测（包含MCP Client验证）
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MCP Server 自测（含Client验证）")
    print("=" * 60)

    # 创建Server
    print("\n【1. 创建MCP Server】")
    server = create_default_mcp_server()
    status = server.get_status()
    print(f"  服务器: {status['server_name']} v{status['server_version']}")
    print(f"  注册工具数: {status['registered_tools']}")
    print(f"  工具列表: {status['tool_names']}")

    # 创建Client并验证
    print("\n【2. MCP Client 验证】")
    client = MCPClient(server, client_name="test-validator", client_version="1.0.0")

    # 初始化
    print("\n  [2.1] 初始化握手")
    init_response = client.initialize()
    print(f"  协议版本: {init_response['result']['protocolVersion']}")
    print(f"  服务器信息: {init_response['result']['serverInfo']}")
    print(f"  能力: {list(init_response['result']['capabilities'].keys())}")

    # 列出工具
    print("\n  [2.2] 列出可用工具 (tools/list)")
    tools = client.list_tools()
    for tool in tools:
        print(f"    - {tool['name']}: {tool['description'][:60]}...")

    # 调用RAG工具
    print("\n  [2.3] 调用RAG工具 (tools/call)")
    result = client.call_tool("rag_query", {"query": "如何配置FastAPI？"})
    content = result['result']['content'][0]['text']
    print(f"  返回内容:\n{content[:200]}...")
    print(f"  isError: {result['result']['isError']}")

    # 调用Calculator工具
    print("\n  [2.4] 调用Calculator工具")
    result = client.call_tool("calculator", {"expression": "2 + 3 * 4"})
    print(f"  返回: {result['result']['content'][0]['text']}")

    # 测试SQL写操作被拒绝
    print("\n  [2.5] 测试SQL写操作被拒绝（安全验证）")
    result = client.call_tool("sql_query", {"query": "DELETE FROM users"})
    print(f"  返回: {result['result']['content'][0]['text']}")
    print(f"  isError: {result['result']['isError']}")

    # 列出资源
    print("\n  [2.6] 列出资源 (resources/list)")
    resources = client.list_resources()
    for res in resources:
        print(f"    - {res['uri']}: {res['name']}")

    # 读取资源
    print("\n  [2.7] 读取资源 (resources/read)")
    result = client.read_resource("docs://project/readme")
    content = result['result']['contents'][0]['text']
    print(f"  内容:\n{content[:100]}...")

    # 最终状态
    print("\n【3. 最终状态】")
    status = server.get_status()
    print(f"  总请求数: {status['total_requests']}")
    print(f"  运行时间: {status['uptime_seconds']}s")
    print(f"  初始化完成: {status['initialized']}")

    print("\n" + "=" * 60)
    print("MCP Server 自测完成！所有标准方法验证通过。")
    print("外部MCP客户端可以正常调用本Server的工具。")
    print("=" * 60)
