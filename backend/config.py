# -*- coding: utf-8 -*-
"""
config.py - 配置管理模块（对齐技术栈2.1：pydantic-settings）
=============================================
统一管理LLM（多Provider自动降级）、Agent、记忆、工具、服务端、认证等所有配置。
- 基于 pydantic-settings（BaseSettings + YAML + 环境变量三级覆盖）
- API Key 一律通过环境变量注入（DEEPSEEK_API_KEY / DASHSCOPE_API_KEY / OPENAI_API_KEY / SERPAPI_KEY）
- 支持 from_yaml / to_yaml / to_dict / get_config 兼容接口
"""

import os
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any, Type

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# HuggingFace国内镜像（Embedding模型下载用）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# ---- 加载 .env（backend/.env 优先，兼容从项目根/任意目录运行；不覆盖已有环境变量）----
_config_dir = Path(__file__).resolve().parent          # backend/
load_dotenv(_config_dir / ".env")                      # backend/.env（主）
load_dotenv(_config_dir.parent / ".env")               # 项目根 .env（兜底）
load_dotenv()                                          # 当前工作目录 .env（兜底）


# ============================================================
# LLM 多Provider配置（技术栈2.1：自动降级）
# ============================================================

class LLMProvider(BaseModel):
    """单个LLM Provider（OpenAI兼容接口）"""
    name: str = "deepseek"                                      # 标识：deepseek / dashscope / openai
    model: str = "deepseek-chat"                                # 模型名称
    base_url: str = "https://api.deepseek.com/v1"              # OpenAI兼容API地址
    api_key: str = ""                                           # API Key（环境变量注入，不入库）
    priority: int = 1                                           # 降级优先级（1最高）


class LLMConfig(BaseSettings):
    """大模型配置（多Provider，按priority自动降级）"""
    model_config = SettingsConfigDict(extra="ignore", arbitrary_types_allowed=True)

    providers: List[LLMProvider] = [
        LLMProvider(name="deepseek", model="deepseek-chat",
                    base_url="https://api.deepseek.com/v1", priority=1),
        LLMProvider(name="dashscope", model="qwen-plus",
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", priority=2),
        LLMProvider(name="openai", model="gpt-4o-mini",
                    base_url="https://api.openai.com/v1", priority=3),
    ]
    temperature: float = 0.0                                    # 温度（0最确定）
    max_tokens: int = 2048                                      # 最大生成token数
    streaming: bool = True                                      # 是否流式输出
    request_timeout: int = 60                                   # 请求超时（秒）

    # ---- 兼容字段（取第一个Provider，供旧代码 config.llm.model/api_key/base_url 使用）----
    @property
    def model(self) -> str:
        return self.providers[0].model if self.providers else ""

    @property
    def base_url(self) -> str:
        return self.providers[0].base_url if self.providers else ""

    @property
    def api_key(self) -> str:
        return self.providers[0].api_key if self.providers else ""

    def get_provider(self, name: str) -> Optional[LLMProvider]:
        """按名称获取Provider"""
        for p in self.providers:
            if p.name == name:
                return p
        return None

    def available_providers(self) -> List[LLMProvider]:
        """返回配置了API Key的可用Provider（按priority排序）"""
        eps = [p for p in self.providers if p.api_key]
        return sorted(eps, key=lambda p: p.priority)


# ============================================================
# Agent 配置
# ============================================================

class AgentConfig(BaseModel):
    """Agent配置"""
    max_iterations: int = 4                   # 最大工具调用轮次（防无限循环，4足够大多数任务）
    early_stopping_method: str = "generate"   # 达上限时强制生成答案
    handle_parsing_errors: bool = True        # 解析错误时自动重试
    verbose: bool = True                      # 打印思考过程
    return_intermediate_steps: bool = True    # 返回中间步骤（工具调用记录）


# ============================================================
# 记忆系统 配置
# ============================================================

class MemoryConfig(BaseModel):
    """记忆系统配置"""
    short_term_window: int = 5                                   # 短期记忆窗口（最近5轮）
    long_term_embedding_model: str = "BAAI/bge-small-zh-v1.5"   # 长期记忆Embedding模型
    long_term_top_k: int = 3                                     # 长期记忆检索TopK
    long_term_persist_dir: str = "./faiss_memory"                # 长期记忆持久化目录
    similarity_threshold: float = 0.9                            # 记忆去重相似度阈值


# ============================================================
# 工具 配置
# ============================================================

class SearchConfig(BaseModel):
    """联网搜索配置"""
    provider: str = "duckduckgo"          # 搜索引擎：duckduckgo（免费）或 serpapi
    serpapi_key: str = ""                 # SerpAPI Key（使用serpapi时需要）
    num_results: int = 5                  # 返回结果条数


class PythonExecConfig(BaseModel):
    """Python代码执行配置"""
    timeout: int = 30                     # 执行超时（秒）
    max_output_length: int = 10000        # 最大输出长度（字符）


class SQLConfig(BaseModel):
    """SQL数据库配置"""
    database_uri: str = "sqlite:///data/example.db"  # 数据库连接URI（支持MySQL/PostgreSQL）
    read_only: bool = True                            # 只读模式（禁止写操作）
    max_rows: int = 50                                # 最大返回行数


class DocQAConfig(BaseModel):
    """文档问答（RAG）配置"""
    docs_dir: str = "./docs"                            # 文档目录
    embedding_model: str = "BAAI/bge-small-zh-v1.5"    # Embedding模型
    persist_dir: str = "./faiss_docs"                   # 向量库持久化目录
    top_k: int = 3                                      # 检索TopK
    chunk_size: int = 500                               # 文本分块大小
    chunk_overlap: int = 50                             # 分块重叠


class ToolsConfig(BaseModel):
    """工具总配置"""
    search: SearchConfig = Field(default_factory=SearchConfig)
    python_executor: PythonExecConfig = Field(default_factory=PythonExecConfig)
    sql_query: SQLConfig = Field(default_factory=SQLConfig)
    doc_qa: DocQAConfig = Field(default_factory=DocQAConfig)


# ============================================================
# 数据库 配置（技术栈2.1：SQLAlchemy）
# ============================================================

class DatabaseConfig(BaseModel):
    """用户/认证数据存储（开发SQLite，生产MySQL/PostgreSQL）"""
    url: str = "sqlite:///data/app.db"    # 连接URI（sqlite:/// 或 mysql+pymysql://user:pass@host:port/db?charset=utf8mb4）


# ============================================================
# 服务端 & 认证 配置（技术栈2.1：JWT）
# ============================================================

class ServerConfig(BaseModel):
    """服务端配置"""
    host: str = "0.0.0.0"
    port: int = 8000
    websocket_timeout: int = 300


class AuthConfig(BaseSettings):
    """JWT认证配置（技术栈2.1：python-jose + bcrypt）"""
    model_config = SettingsConfigDict(extra="ignore")

    jwt_secret: str = "change-me-in-production"      # JWT签名密钥（生产必须通过环境变量 JWT_SECRET 设置）
    jwt_algorithm: str = "HS256"                      # 签名算法
    access_token_expire_minutes: int = 30             # 访问Token有效期（30分钟）
    refresh_token_expire_days: int = 7                # 刷新Token有效期（7天）

    @property
    def secret(self) -> str:
        return self.jwt_secret


# ============================================================
# 应用总配置
# ============================================================

class AppConfig(BaseSettings):
    """应用总配置（pydantic-settings 对齐）"""
    model_config = SettingsConfigDict(extra="ignore", arbitrary_types_allowed=True)

    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    # ---- 环境变量注入敏感Key（优先级最高，不入库）----
    def model_post_init(self, __context: Any) -> None:
        env_keys = {
            "deepseek": os.environ.get("DEEPSEEK_API_KEY"),
            "dashscope": os.environ.get("DASHSCOPE_API_KEY"),
            "openai": os.environ.get("OPENAI_API_KEY"),
        }
        for p in self.llm.providers:
            ek = env_keys.get(p.name)
            if ek:
                p.api_key = ek
        if os.environ.get("SERPAPI_KEY"):
            self.tools.search.serpapi_key = os.environ["SERPAPI_KEY"]
        if os.environ.get("JWT_SECRET"):
            self.auth.jwt_secret = os.environ["JWT_SECRET"]
        if os.environ.get("DATABASE_URL"):
            self.database.url = os.environ["DATABASE_URL"]

    # ---- 序列化 ----
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), allow_unicode=True, sort_keys=False)

    @classmethod
    def from_yaml(cls: Type["AppConfig"], yaml_str: str) -> "AppConfig":
        data = yaml.safe_load(yaml_str) or {}
        merged = cls().model_dump()
        _deep_update(merged, data)
        return cls(**merged)

    @classmethod
    def load(cls: Type["AppConfig"], config_path: str = "config.yaml") -> "AppConfig":
        """从YAML文件加载（不存在时使用默认配置）"""
        path = Path(config_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            merged = cls().model_dump()
            _deep_update(merged, data)
            return cls(**merged)
        return cls()


def _deep_update(base: dict, override: dict) -> dict:
    """递归更新字典（用于合并YAML配置到默认配置）"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


# ============================================================
# 兼容加载接口
# ============================================================

def load_config(config_path: str = "config.yaml") -> AppConfig:
    """从YAML文件加载配置（兼容旧接口）"""
    return AppConfig.load(config_path)


# 全局配置单例（延迟加载）
_global_config: Optional[AppConfig] = None


def get_config(config_path: str = "config.yaml") -> AppConfig:
    """获取全局配置单例"""
    global _global_config
    if _global_config is None:
        _global_config = load_config(config_path)
    return _global_config
