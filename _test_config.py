# -*- coding: utf-8 -*-
"""config.py pydantic-settings 兼容性自测"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
os.environ["DEEPSEEK_API_KEY"] = "test-deepseek-key"

from config import AppConfig, get_config, load_config

# 1. 从 config.yaml 加载
CFG = os.path.join(os.path.dirname(__file__), "backend", "config.yaml")
c = load_config(CFG)
assert c.llm.model == "deepseek-chat", f"model: {c.llm.model}"
assert c.llm.api_key == "test-deepseek-key", f"api_key: {c.llm.api_key}"
assert c.llm.base_url.startswith("https://api.deepseek.com")
assert c.agent.max_iterations == 4
assert c.memory.long_term_top_k == 3
assert c.tools.sql_query.database_uri.endswith("example.db")
assert c.server.port == 8000

# 2. 多 Provider
provs = c.llm.available_providers()
assert len(provs) == 1 and provs[0].name == "deepseek", [p.name for p in provs]
assert c.llm.get_provider("dashscope") is not None

# 3. 序列化
d = c.to_dict()
assert d["llm"]["providers"][0]["name"] == "deepseek"
y = c.to_yaml()
assert "deepseek" in y

# 4. from_yaml 往返
c2 = AppConfig.from_yaml(y)
assert c2.llm.providers[0].model == "deepseek-chat"

# 5. 单例（get_config 全局单例）
g1 = get_config(CFG)
g2 = get_config(CFG)
assert g1 is g2

# 6. 下游依赖字段（agent/react_agent.py 等用到的）
assert c.llm.temperature == 0.0
assert c.llm.max_tokens == 2048
assert c.llm.streaming is True
assert c.llm.request_timeout == 60

print("ALL CONFIG TESTS PASSED")
