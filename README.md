# AI Agent助手 - 基于LangChain + LangGraph

多功能AI Agent助手，支持联网搜索、数学计算、Python代码执行、SQL数据库查询、文档问答（RAG）等多工具协作，通过ReAct范式自主决策，支持Plan-and-Execute复杂任务规划。

## 功能特性

- **6类工具**：联网搜索（DuckDuckGo/SerpAPI）、安全数学计算、Python代码执行、SQL查询、文档问答（RAG）、记忆操作
- **混合记忆**：短期滑动窗口（5轮）+ 长期FAISS向量记忆（BGE Embedding），自动事实提取与去重
- **三种Agent模式**：
  - ReAct Agent：基于Function Calling，快速响应单步/多步任务
  - LangGraph Agent：有状态图编排，支持中断恢复与人工介入
  - Plan-and-Execute：复杂任务先规划再逐步执行
- **完善容错**：max_iterations循环保护、工具超时、异常捕获、解析错误重试
- **实时交互**：FastAPI REST + WebSocket流式推送，Vue3 + Element Plus 企业级前端
- **工具权限系统**：READ / SANDBOX / DANGEROUS 三级风险分级，高风险操作需Human-in-the-loop审批
- **MCP协议支持**：标准MCP Server，暴露RAG/SQL/Search/Calculator工具，支持外部Agent客户端调用
- **可观测性**：request_id / trace_id 全链路追踪，LLM调用/Tool调用/Token用量/耗时统计
- **评估体系**：30条多步任务测试集，自动统计完成率/工具准确率/平均轮次

## 快速开始

### 1. 安装依赖

```bash
cd LangChain
pip install -r requirements.txt
```

### 2. 配置

编辑 `config.yaml`，确认API Key已填入（已预填DeepSeek Key）。

### 3. 初始化示例数据库

```bash
python main.py init-db
```

### 4. 命令行交互

```bash
python main.py chat
# 或使用Plan-and-Execute模式处理复杂任务
python main.py chat --agent_type planner
```

### 5. 启动Vue3前端

```bash
cd frontend-vue
npm install
npm run dev
# 访问 http://localhost:5174
```

前端技术栈：Vue3 + TypeScript + Vite + Element Plus + Pinia + WebSocket
功能：聊天界面、工具调用时间线、Agent模式切换、会话管理、Human-in-the-loop审批弹窗、Execution Trace实时展示

### 6. 启动API服务

```bash
python main.py serve
# REST API: http://localhost:8000/api/chat
# WebSocket: ws://localhost:8000/ws
# 文档: http://localhost:8000/docs
```

### 7. 运行评估

```bash
python main.py eval
```

## 工具说明

| 工具 | 名称 | 功能 | 安全限制 | 风险等级 |
|------|------|------|----------|----------|
| 联网搜索 | Search | DuckDuckGo/SerpAPI搜索实时信息 | - | READ |
| 数学计算 | Calculator | 安全求值数学表达式 | 禁用builtins，仅math函数 | READ |
| Python执行 | PythonExecutor | 子进程执行Python代码 | 30秒超时，禁止网络/文件写入 | SANDBOX |
| SQL查询 | SQLQuery | SQLAlchemy执行SELECT查询 | 只读，禁止写操作，限50行 | READ |
| 表结构 | GetDBSchema | 查看数据库表结构 | - | READ |
| 文档问答 | DocQA | FAISS+BGE检索内部文档 | 支持txt/md/pdf/docx | READ |
| 记住事实 | RememberFact | 存入长期向量记忆 | 相似度>0.9去重 | READ |
| 回忆事实 | RecallFact | 语义检索长期记忆 | TopK=3 | READ |

## 项目结构

```
LangChain/
├── config.py                  # 配置管理
├── config.yaml                # 配置文件
├── agent_manager.py           # Agent统一管理器
├── main.py                    # 命令行入口
├── evaluator.py               # 评估模块
├── create_sample_db.py        # 示例数据库创建
├── observability.py           # 全链路可观测性（trace_id/request_id）
├── mcp_server.py              # MCP Server（标准协议）
├── mcp_server_real.py         # MCP Server（真实系统接入：SQL/RAG/Search/Calculator）
├── tools/                     # 工具模块
│   ├── search_tool.py         # 联网搜索
│   ├── calculator.py          # 数学计算
│   ├── python_executor.py     # Python执行（SANDBOX风险隔离）
│   ├── sql_query.py           # SQL查询
│   ├── doc_qa.py              # 文档问答RAG
│   ├── memory_tools.py        # 记忆工具
│   └── tool_permission.py     # 工具权限系统（READ/SANDBOX/DANGEROUS三级）
├── memory/                    # 记忆系统
│   ├── short_term.py          # 短期滑动窗口
│   ├── long_term.py           # 长期FAISS向量记忆
│   └── memory_manager.py      # 记忆管理器
├── agent/                     # Agent核心
│   ├── react_agent.py         # ReAct Agent（回调基类+风险等级）
│   ├── langgraph_agent.py     # LangGraph有状态Agent（HITL中断恢复）
│   ├── planner.py             # Plan-and-Execute
│   └── prompt.py              # Prompt模板
├── server/                    # 服务端
│   ├── api.py                 # FastAPI REST
│   ├── websocket_handler.py   # WebSocket（Execution Trace事件协议）
│   └── schemas.py             # 数据模型
├── frontend-vue/              # Vue3前端工程
│   ├── src/
│   │   ├── api/agent.ts       # API + WebSocket封装
│   │   ├── stores/agent.ts    # Pinia状态管理
│   │   ├── types/index.ts     # TypeScript类型定义（AgentEvent联合类型）
│   │   ├── components/        # Vue组件
│   │   │   ├── ChatMessage.vue       # 聊天消息+工具调用折叠
│   │   │   ├── ToolTimeline.vue      # 工具调用时间线
│   │   │   ├── ApprovalDialog.vue    # HITL高风险操作审批弹窗
│   │   │   └── SessionSidebar.vue    # 会话列表侧边栏
│   │   └── App.vue            # 主界面（三栏布局）
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── data/
│   └── example.db             # 示例SQLite数据库
├── docs/                      # RAG文档目录（放入自己的文档）
├── tests/
│   ├── eval_tasks.json        # 30条评估测试集（含标准答案）
│   ├── evaluate_agent.py      # 自动评估脚本（输出26/30=86.67%）
│   └── test_company.db        # MCP真实测试数据库
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## API使用示例

### REST API

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "查询技术部有多少员工", "session_id": "user1"}'
```

### WebSocket

```python
import websockets, json

async def chat():
    async with websockets.connect("ws://localhost:8000/ws") as ws:
        await ws.send(json.dumps({
            "type": "message",
            "content": "搜索今天的新闻",
            "session_id": "user1"
        }))
        while True:
            event = json.loads(await ws.recv())
            print(f"[{event['type']}] {event['content']}")
            if event["type"] == "done":
                break
```

WebSocket事件协议（Execution Trace）：
- `plan` - Agent规划步骤
- `status` - 状态变化
- `tool_start` - 工具调用开始
- `tool_end` - 工具调用结束
- `approval_required` - 高风险操作需人工审批
- `token` - 流式输出token
- `done` - 任务完成
- `error` - 错误

## 扩展工具

在 `tools/` 下创建新工具，使用LangChain的 `Tool` 封装：

```python
from langchain_core.tools import Tool

def my_tool(input: str) -> str:
    return f"结果: {input}"

my_tool = Tool(
    name="MyTool",
    func=my_tool,
    description="清晰描述工具功能，LLM据此选择工具"
)
```

然后在 `tools/__init__.py` 的 `get_all_tools()` 中添加，并在 `tools/tool_permission.py` 中注册风险等级。

## 常见问题

**Q: 搜索工具报错？**
A: DuckDuckGo在国内可能不稳定，可在config.yaml中切换为serpapi并配置Key，或安装duckduckgo-search库。

**Q: 文档问答工具不工作？**
A: 将文档放入 `docs/` 目录（支持txt/md/pdf/docx），首次查询时自动构建索引。MCP真实RAG工具需要先启动RAG服务（http://localhost:8000）。

**Q: Python执行安全吗？**
A: 通过AST静态检查+子进程隔离+超时限制+资源限制，标记为SANDBOX风险等级。这是进程级风险隔离，不是强安全沙箱，生产环境建议Docker容器隔离。

**Q: 如何使用自己的数据库？**
A: 修改config.yaml中 `tools.sql_query.database_uri`，支持SQLite/MySQL/PostgreSQL。

**Q: MCP工具如何被外部客户端调用？**
A: 运行 `python mcp_server_real.py` 启动MCP Server，支持标准JSON-RPC 2.0协议的tools/list和tools/call，可被Claude Desktop、Cursor或其他LangChain Agent直接调用。
