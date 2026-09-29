# -*- coding: utf-8 -*-
"""
python_executor.py - Python代码执行工具（风险隔离，非强安全沙箱）
=============================================
功能：在子进程中执行Python代码，返回stdout输出

风险隔离措施（注意：这不是完全安全的沙箱）：
  - 子进程隔离执行，设置超时（默认30秒）
  - 临时目录执行
  - 限制输出长度
  - AST静态检查，禁止危险模块和函数调用

重要安全声明：
  subprocess ≠ sandbox。进程级隔离不能视为强安全边界，
  存在潜在的逃逸风险。生产环境应使用Docker容器沙箱、
  seccomp系统调用过滤、网络隔离、资源配额等机制。

  本工具仅用于个人项目的风险降低，不保证绝对安全。
"""

import sys
import ast
import tempfile
import subprocess
import textwrap
from pathlib import Path
from loguru import logger

from langchain_core.tools import Tool


# 禁止导入的危险模块
FORBIDDEN_MODULES = {
    "os", "subprocess", "shutil", "sys", "socket",
    "requests", "urllib", "http", "ftplib", "smtplib",
    "ctypes", "multiprocessing", "threading",
}

# 禁止调用的危险函数
FORBIDDEN_CALLS = {
    "system", "popen", "exec", "eval", "compile",
    "__import__", "open", "remove", "unlink",
    "rmdir", "mkdir", "chmod", "chown",
}


def _check_code_safety(code: str) -> tuple:
    """
    检查代码安全性（AST静态分析）

    注意：这是基础的静态检查，不能保证100%安全。
    危险代码可能通过反射、动态导入等方式绕过检查。

    Args:
        code: Python代码

    Returns:
        tuple: (是否安全, 原因)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"语法错误: {e}"

    for node in ast.walk(tree):
        # 检查import语句
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                    return False, f"禁止导入模块: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_MODULES:
                return False, f"禁止导入模块: {node.module}"

        # 检查危险函数调用
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_CALLS:
                    return False, f"禁止调用函数: {node.func.id}"
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in FORBIDDEN_CALLS:
                    return False, f"禁止调用方法: {node.func.attr}"

    return True, "通过基础安全检查"


def execute_python(code: str) -> str:
    """
    执行Python代码并返回输出

    安全声明：本函数使用subprocess进程级隔离，仅用于降低风险，
    不能视为强安全沙箱。生产环境请使用Docker容器隔离。

    Args:
        code: 完整的Python代码字符串

    Returns:
        str: 执行输出（stdout）或错误信息
    """
    from config import get_config

    config = get_config()
    timeout = config.tools.python_executor.timeout
    max_output = config.tools.python_executor.max_output_length

    logger.info(f"执行Python代码 ({len(code)} 字符)")

    # 基础安全检查（AST静态分析）
    is_safe, reason = _check_code_safety(code)
    if not is_safe:
        return f"代码安全检查失败: {reason}"

    # 去除多余缩进
    code = textwrap.dedent(code).strip()

    # 在临时目录中执行（进程级隔离，非强安全沙箱）
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "script.py"
        script_path.write_text(code, encoding="utf-8")

        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                encoding="utf-8",
                errors="replace",
            )

            output_parts = []

            # stdout
            if result.stdout:
                output_parts.append(result.stdout.strip())

            # stderr（如果有错误）
            if result.stderr:
                stderr = result.stderr.strip()
                # 过滤掉Python警告信息
                error_lines = [
                    line for line in stderr.split("\n")
                    if not line.startswith("Failed to send telemetry")
                    and "warnings.warn" not in line
                    and "FutureWarning" not in line
                ]
                if error_lines:
                    output_parts.append("错误输出:\n" + "\n".join(error_lines))

            output = "\n".join(output_parts) if output_parts else "(代码执行完成，无输出)"

            # 限制输出长度
            if len(output) > max_output:
                output = output[:max_output] + f"\n... (输出已截断，共{len(output)}字符)"

            logger.info(f"Python执行完成，输出{len(output)}字符")
            return output

        except subprocess.TimeoutExpired:
            return f"代码执行超时（{timeout}秒），可能存在死循环或计算量过大"
        except Exception as e:
            return f"执行失败: {str(e)[:300]}"


# LangChain工具对象
# 风险等级：SANDBOX（子进程隔离，非强安全沙箱）
python_executor = Tool(
    name="PythonExecutor",
    func=execute_python,
    description=(
        "在隔离的子进程中执行Python代码并返回标准输出。"
        "输入完整的Python代码字符串，可用于复杂计算、数据处理、算法验证、逻辑推理等。"
        "代码中使用print()输出结果。"
        "安全限制：禁止网络访问、文件系统操作、系统命令执行等危险操作。"
        "注意：这是进程级风险隔离，不是强安全沙箱，请勿执行不可信代码。"
        "示例输入：\n"
        "```python\n"
        "total = sum(range(1, 101))\n"
        "print('1到100的和:', total)\n"
        "```"
    )
)
# 工具风险等级由 tools/tool_permission.py 统一管理
# PythonExecutor 在 react_agent.py 中自动识别为 SANDBOX 等级
# 无需在此处动态赋值（Pydantic v2 不允许 Tool 对象动态添加字段）


# 模块测试
if __name__ == "__main__":
    test_code = """
import math
for i in range(5):
    print(f"{i}! = {math.factorial(i)}")
"""
    print(execute_python(test_code))
