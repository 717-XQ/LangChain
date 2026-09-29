# -*- coding: utf-8 -*-
"""认证模块冒烟测试（TestClient）"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
os.environ["DEEPSEEK_API_KEY"] = "test-key-for-smoke"
os.environ["JWT_SECRET"] = "test-secret-2026"

from fastapi.testclient import TestClient
from agent_manager import get_agent_manager
from server.api import create_app
from server.websocket_handler import setup_websocket
from database import init_db

init_db()  # 建 users 表

manager = get_agent_manager()
app = create_app(manager)
setup_websocket(app, manager)
client = TestClient(app)

BASE = "http://testserver"
results = []

# 1. 健康检查（公开）
r = client.get("/api/health")
assert r.status_code == 200 and r.json()["status"] == "ok"
results.append("health 200")

# 2. 无Token访问业务API → 401
r = client.post("/api/chat", json={"message": "你好"})
assert r.status_code == 401, r.status_code
results.append("无Token 401")

# 3. 注册
r = client.post("/auth/register", json={
    "username": "smoke_user", "email": "smoke@test.com", "password": "smoke123456"
})
assert r.status_code == 201, (r.status_code, r.text)
tokens = r.json()
assert tokens["access_token"] and tokens["refresh_token"]
results.append("register 201 + 双Token")

# 4. 重复注册 → 400
r = client.post("/auth/register", json={
    "username": "smoke_user", "email": "smoke@test.com", "password": "smoke123456"
})
assert r.status_code == 400
results.append("重复注册 400")

# 5. 登录（错误密码 → 401）
r = client.post("/auth/login", json={"username": "smoke_user", "password": "wrong"})
assert r.status_code == 401
results.append("错误密码 401")

# 6. 登录（正确）
r = client.post("/auth/login", json={"username": "smoke_user", "password": "smoke123456"})
assert r.status_code == 200
tokens = r.json()
access = tokens["access_token"]
refresh = tokens["refresh_token"]
results.append("登录 200")

# 7. 带Token访问 /api/tools
r = client.get("/api/tools", headers={"Authorization": f"Bearer {access}"})
assert r.status_code == 200
assert isinstance(r.json(), list)
results.append("带Token /api/tools 200")

# 8. /auth/me
r = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
assert r.status_code == 200 and r.json()["username"] == "smoke_user"
results.append("/auth/me 200")

# 9. 刷新Token
r = client.post("/auth/refresh", json={"refresh_token": refresh})
assert r.status_code == 200
new_access = r.json()["access_token"]
results.append("刷新Token 200")

# 10. 新Token仍有效
r = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
assert r.status_code == 200
results.append("刷新后Token有效")

print("AUTH SMOKE TESTS:", len(results), "PASSED")
for item in results:
    print("  -", item)
