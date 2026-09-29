# AI Agent助手 - 基于LangChain + LangGraph

多功能AI Agent助手，支持联网搜索、数学计算、Python代码执行、SQL数据库查询、文档问答（RAG）等多工具协作，通过ReAct范式自主决策，支持Plan-and-Execute复杂任务规划。技术栈已按规范对齐（后端2.1 / 前端2.2），前后端目录分离。

## 功能特性

- **6类工具**：联网搜索（DuckDuckGo/SerpAPI）、安全数学计算、Python代码执行、SQL查询、文档问答（RAG）、记忆操作
- **混合记忆**：短期滑动窗口（5轮）+ 长期FAISS向量记忆（BGE Embedding），自动事实提取与去重
- **三种Agent模式**：
  - ReAct Agent：基于Function Calling，快速响应单步/多步任务
  - LangGraph Agent：有状态图编排，支持中断恢复与人工介入
  - Plan-and-Execute：复杂任务先规划再逐步执行
- **多Provider自动降级**（技术栈2.1）：DeepSeek / DashScope(通义千问) / OpenAI 按优先级自动降级
- **JWT认证**（技术栈2.1/2.2）：python-jose + bcrypt，注册/登录/刷新Token，前端Token自动续期
- **配置管理**（技术栈2.1）：pydantic-settings（YAML + 环境变量三级覆盖），API Key不入库
- **完善容错**：max_iterations循环保护、工具超时、异常捕获、解析错误重试
- **实时交互**：FastAPI REST + WebSocket流式推送（携带Token鉴权），Vue3 + Element Plus 企业级前端
- **工具权限系统**：READ / SANDBOX / DANGEROUS 三级风险分级，高风险操作需Human-in-the-loop审批
- **MCP协议支持**：标准MCP Server，暴露RAG/SQL/Search/Calculator工具，支持外部Agent客户端调用
- **可观测性**：request_id / trace_id 全链路追踪，LLM调用/Tool调用/Token用量/耗时统计
- **评估体系**：30条多步任务测试集，自动统计完成率/工具准确率/平均轮次

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| Agent编排 | LangChain 0.3 + LangGraph 0.2（ReAct / 状态图 / 规划执行） |
| 大模型 | 多Provider自动降级：DeepSeek / DashScope / OpenAI（OpenAI兼容API） |
| 配置管理 | pydantic-settings（YAML + 环境变量 `*_API_KEY` / `JWT_SECRET` 注入） |
| 认证 | python-jose（JWT双Token）+ bcrypt（技术栈2.1） |
| 用户存储 | SQLAlchemy 2.0（开发SQLite / 生产MySQL/PG，`config.yaml` 可配） |
| 向量存储 | FAISS（长期记忆 / 文档RAG），BGE-small-zh Embedding |
| 实时通信 | WebSocket（Agent Execution Trace协议，Token鉴权） |
| 前端框架 | Vue3 + TypeScript + Vite + Element Plus + Pinia + Vue Router + Axios（技术栈2.2） |
| Markdown渲染 | markdown-it + highlight.js（代码高亮） |
| 图表 | ECharts（工具调用统计） |
| 评估 | 自研AgentEvaluator（30条多步任务测试集） |

## 快速开始

### 1. 安装依赖

```bash
cd LangChain/backend        # 后端整合在 backend/ 目录（前端为 frontend-vue/）
pip install -r requirements.txt
```

### 2. 配置（API Key通过环境变量）

复制模板并编辑环境变量（`backend/.env`，已被 .gitignore 排除，不入库）：

```bash
cd backend
# .env 已存在则直接编辑；不存在则复制模板
copy .env.example .env
```

```ini
# backend/.env（关键项）
DEEPSEEK_API_KEY=sk-...            # DeepSeek（priority 1）
# DASHSCOPE_API_KEY=sk-...         # 通义千问（priority 2，可选）
# OPENAI_API_KEY=sk-...            # OpenAI（priority 3，可选）
# JWT_SECRET=your-random-secret    # 生产环境必填
HF_ENDPOINT=https://hf-mirror.com  # HuggingFace国内镜像
```

> 系统按 `config.yaml` 中 `llm.providers` 的 `priority` 顺序调用各Provider，失败自动降级到下一个。

### 3. 初始化认证数据库（JWT用户表）

```bash
cd backend
python main.py db-init        # 建 users 表（SQLite默认，MySQL可改 config.yaml database.url）
python main.py init-db        # 创建示例业务数据库（SQL查询工具用）
```

### 4. 命令行交互

```bash
python main.py chat
# 或使用Plan-and-Execute模式处理复杂任务
python main.py chat --agent_type planner
```

### 5. 启动API服务

```bash
python main.py serve
# REST API: http://localhost:8000/api/chat（需Bearer Token）
# WebSocket: ws://localhost:8000/ws?token=<access_token>
# 认证API: http://localhost:8000/api/auth/*（注册/登录/刷新）
# 文档: http://localhost:8000/docs
```

### 6. 启动Vue3前端

```bash
cd frontend-vue
npm install
npm run dev
# 访问 http://localhost:5174 （自动跳转登录页）
```

前端技术栈：Vue3 + TypeScript + Vite + Element Plus + Pinia + Vue Router + Axios + markdown-it + highlight.js + ECharts
功能：登录/注册、聊天界面、Agent模式切换、会话管理、Human-in-the-loop审批弹窗、Execution Trace实时展示、右侧可折叠"工具调用"面板（ECharts统计图 + 完整调用过程时间线，按钮开关不遮挡会话内容）、Token自动刷新

### 7. 运行评估

```bash
cd backend
python main.py eval
```

## 认证使用（技术栈2.1：JWT双Token）

> 认证API挂载在 `/api/auth/*`（与业务API同 `/api` 前缀，前端代理直接可达）。

```bash
# 注册（自动登录）
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test_user","email":"test@example.com","password":"test123456"}'

# 登录（返回 access_token / refresh_token）
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test_user","password":"test123456"}'

# 刷新Token
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'

# 当前用户
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

- 访问Token有效期30分钟，刷新Token 7天；前端Axios拦截器自动续期
- 业务API（`/api/chat`、`/api/tools`、`/api/memory`）需携带 `Authorization: Bearer <access_token>`
- WebSocket连接需携带 `?token=<access_token>`，否则返回 4401

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
├── backend/                    # 后端（对齐技术栈2.1，与 frontend-vue/ 平行区分）
│   ├── server/                 # FastAPI服务（REST + WebSocket + JWT认证）
│   │   ├── api.py              # FastAPI REST（业务API均需Bearer Token）
│   │   ├── auth.py             # JWT认证（python-jose + bcrypt，/api/auth/*）
│   │   ├── websocket_handler.py# WebSocket（Agent Execution Trace协议，Token鉴权）
│   │   └── schemas.py          # 数据模型
│   ├── agent/                  # Agent核心
│   │   ├── react_agent.py      # ReAct Agent（回调基类+风险等级+多Provider降级）
│   │   ├── langgraph_agent.py  # LangGraph有状态Agent（HITL中断恢复）
│   │   ├── planner.py          # Plan-and-Execute
│   │   └── prompt.py           # Prompt模板
│   ├── tools/                  # 工具模块（6类工具+权限系统）
│   ├── memory/                 # 记忆系统（短期滑动窗口 + 长期FAISS向量记忆）
│   ├── frontend/               # Gradio轻量前端（可选备用）
│   ├── config.py               # 配置管理（pydantic-settings，多Provider）
│   ├── config.yaml             # 配置文件（无密钥，可入库）
│   ├── config.yaml.example     # 配置文件模板
│   ├── llm_client.py           # 多Provider LLM客户端（自动降级）
│   ├── database.py             # SQLAlchemy引擎与会话（SQLite/MySQL）
│   ├── models.py               # ORM模型（users表）
│   ├── main.py                 # 命令行入口（chat/serve/db-init/eval）
│   ├── agent_manager.py        # Agent统一管理器
│   ├── evaluator.py            # 评估模块
│   ├── observability.py        # 全链路可观测性
│   ├── mcp_server.py           # MCP Server（标准协议）
│   ├── mcp_server_real.py      # MCP Server（真实系统接入）
│   ├── create_sample_db.py     # 示例业务数据库创建
│   ├── requirements.txt
│   ├── data/                   # 业务数据库（example.db，生成物不入库）
│   ├── docs/                   # RAG文档目录（放入自己的文档）
│   └── tests/                  # 评估测试集与脚本
├── frontend-vue/               # Vue3前端工程（对齐技术栈2.2）
│   ├── src/
│   │   ├── api/agent.ts        # Axios（Token自动刷新）+ WebSocket + 认证API
│   │   ├── stores/agent.ts     # Pinia Agent状态
│   │   ├── stores/auth.ts      # Pinia认证状态
│   │   ├── router/             # Vue Router（登录/主页 + 路由守卫）
│   │   ├── views/              # 页面（LoginView / HomeView）
│   │   ├── components/         # ChatMessage/MarkdownContent/ToolTimeline/ToolStatsChart/ApprovalDialog/SessionSidebar
│   │   └── types/index.ts      # TypeScript类型定义
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── Dockerfile                  # 镜像（后端在 backend/ 下）
├── docker-compose.yml
├── README.md                   # 项目说明
└── .gitignore
```

## API使用示例

### REST API（需认证）

```bash
# 先登录获取Token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test_user","password":"test123456"}' | jq -r .access_token)

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "查询技术部有多少员工", "session_id": "user1"}'
```

### WebSocket（需携带Token）

```python
import websockets, json, urllib.request

# 1. 登录获取Token
req = urllib.request.Request(
    "http://localhost:8000/api/auth/login",
    data=json.dumps({"username": "test_user", "password": "test123456"}).encode(),
    headers={"Content-Type": "application/json"})
token = json.loads(urllib.request.urlopen(req).read())["access_token"]

# 2. 连接WebSocket（带Token）
async def chat():
    async with websockets.connect(f"ws://localhost:8000/ws?token={token}") as ws:
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

WebSocket事件协议（Agent Execution Trace）：
- `plan` - Agent规划步骤
- `status` - 状态变化
- `tool_start` / `tool_end` - 工具调用开始/结束
- `approval_required` - 高风险操作需人工审批
- `token` - 流式输出token
- `done` - 任务完成
- `error` - 错误

## 多Provider配置（技术栈2.1）

`backend/config.yaml` 的 `llm.providers` 定义了降级顺序：

```yaml
llm:
  providers:
    - name: "deepseek"                    # DEEPSEEK_API_KEY
      model: "deepseek-chat"
      base_url: "https://api.deepseek.com/v1"
      api_key: ""                         # 留空，环境变量注入
      priority: 1
    - name: "dashscope"                   # DASHSCOPE_API_KEY
      model: "qwen-plus"
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
      api_key: ""
      priority: 2
    - name: "openai"                      # OPENAI_API_KEY
      model: "gpt-4o-mini"
      base_url: "https://api.openai.com/v1"
      api_key: ""
      priority: 3
```

当前Provider调用失败（余额/网络/超时）时自动降级到下一个；API Key 一律通过环境变量注入，不写入仓库。

## 扩展工具

在 `backend/tools/` 下创建新工具，使用LangChain的 `Tool` 封装：

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

## Docker 部署

```bash
# 设置环境变量（API Key / JWT密钥）
export DEEPSEEK_API_KEY="你的Key"
export JWT_SECRET="随机字符串"

# 构建并启动（后端API + Gradio，镜像内使用 backend/ 目录）
docker-compose up -d

# 前端单独构建（部署到Nginx）
cd frontend-vue
npm run build
# dist目录部署到Nginx，反向代理 /api 与 /ws 到后端

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

## 常见问题

**Q: 搜索工具报错？**
A: DuckDuckGo在国内可能不稳定，可在config.yaml中切换为serpapi并配置Key，或安装duckduckgo-search库。

**Q: 文档问答工具不工作？**
A: 将文档放入 `backend/docs/` 目录（支持txt/md/pdf/docx），首次查询时自动构建索引。MCP真实RAG工具需要先启动RAG服务（http://localhost:8000）。

**Q: Python执行安全吗？**
A: 通过AST静态检查+子进程隔离+超时限制+资源限制，标记为SANDBOX风险等级。这是进程级风险隔离，不是强安全沙箱，生产环境建议Docker容器隔离。

**Q: 如何使用自己的数据库？**
A: 修改config.yaml中 `tools.sql_query.database_uri`，支持SQLite/MySQL/PostgreSQL。

**Q: 登录提示"无法登录/注册"？**
A: 先执行 `python main.py db-init` 初始化users表；确认后端已启动且前端请求代理到8000端口。

**Q: WebSocket连接失败（4401）？**
A: 连接URL需携带 `?token=<access_token>`；Token过期时前端会通过 `/api/auth/refresh` 自动续期后重连。

**Q: MCP工具如何被外部客户端调用？**
A: 运行 `python mcp_server_real.py` 启动MCP Server，支持标准JSON-RPC 2.0协议的tools/list和tools/call，可被Claude Desktop、Cursor或其他LangChain Agent直接调用。

## 许可证

MIT License
