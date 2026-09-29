# -*- coding: utf-8 -*-
"""
calculator.py - 安全数学计算工具
=============================================
功能：安全求值数学表达式，支持math库常用函数
安全限制：
  - 禁用所有__builtins__
  - 只允许math库函数和基本运算符
  - 禁止属性访问（防止os.system等）
"""

import ast
import math
import operator
from typing import Any
from loguru import logger

from langchain_core.tools import Tool


# ============================================================
# 安全的AST求值器
# ============================================================

# 允许的二元运算符
SAFE_BIN_OPS = {
    ast.Add: operator.add,       # +
    ast.Sub: operator.sub,       # -
    ast.Mult: operator.mul,      # *
    ast.Div: operator.truediv,   # /
    ast.FloorDiv: operator.floordiv,  # //
    ast.Mod: operator.mod,       # %
    ast.Pow: operator.pow,       # **
}

# 允许的一元运算符
SAFE_UNARY_OPS = {
    ast.UAdd: operator.pos,      # +x
    ast.USub: operator.neg,      # -x
}

# 允许的math库函数和常量
SAFE_MATH_FUNCTIONS = {
    # 基本函数
    "sqrt": math.sqrt, "cbrt": getattr(math, "cbrt", lambda x: x ** (1/3)),
    "pow": math.pow, "exp": math.exp, "log": math.log,
    "log2": math.log2, "log10": math.log10,
    # 三角函数
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2, "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    # 取整/绝对值
    "ceil": math.ceil, "floor": math.floor, "fabs": math.fabs,
    "trunc": math.trunc, "round": round, "abs": abs,
    # 其他
    "factorial": math.factorial, "gcd": math.gcd,
    "degrees": math.degrees, "radians": math.radians,
    "hypot": math.hypot, "pi": math.pi, "e": math.e, "tau": math.tau,
    "min": min, "max": max, "sum": sum,
}


def _safe_eval_node(node: ast.AST) -> Any:
    """
    递归求值AST节点（仅允许安全节点）

    Args:
        node: AST节点

    Returns:
        求值结果
    """
    # 数字
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value)}")

    # 二元运算（如 2 + 3）
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_BIN_OPS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        return SAFE_BIN_OPS[op_type](left, right)

    # 一元运算（如 -5）
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in SAFE_UNARY_OPS:
            raise ValueError(f"不支持的一元运算符: {op_type.__name__}")
        return SAFE_UNARY_OPS[op_type](_safe_eval_node(node.operand))

    # 函数调用（如 sqrt(16)）
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("不支持的函数调用方式")
        func_name = node.func.id
        if func_name not in SAFE_MATH_FUNCTIONS:
            raise ValueError(f"不允许的函数: {func_name}")
        args = [_safe_eval_node(arg) for arg in node.args]
        return SAFE_MATH_FUNCTIONS[func_name](*args)

    # 名称（如 pi, e）
    elif isinstance(node, ast.Name):
        if node.id in SAFE_MATH_FUNCTIONS:
            return SAFE_MATH_FUNCTIONS[node.id]
        raise ValueError(f"未定义的变量: {node.id}")

    # 比较运算（如 1 < 2）
    elif isinstance(node, ast.Compare):
        left = _safe_eval_node(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = _safe_eval_node(comparator)
            if isinstance(op, ast.Lt) and not left < right:
                return False
            elif isinstance(op, ast.LtE) and not left <= right:
                return False
            elif isinstance(op, ast.Gt) and not left > right:
                return False
            elif isinstance(op, ast.GtE) and not left >= right:
                return False
            elif isinstance(op, ast.Eq) and not left == right:
                return False
            elif isinstance(op, ast.NotEq) and not left != right:
                return False
            left = right
        return True

    else:
        raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


def safe_calculate(expression: str) -> str:
    """
    安全计算数学表达式

    Args:
        expression: 数学表达式字符串，如 "2+3*4"、"sqrt(16)"、"sin(pi/2)"

    Returns:
        str: 计算结果
    """
    logger.info(f"数学计算: {expression}")

    # 清理输入
    expression = expression.strip()
    if not expression:
        return "错误: 表达式为空"

    try:
        # 解析为AST
        tree = ast.parse(expression, mode="eval")
        # 安全求值
        result = _safe_eval_node(tree.body)

        # 格式化结果（整数不显示小数点）
        if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
            result = int(result)

        logger.info(f"计算结果: {expression} = {result}")
        return f"{expression} = {result}"

    except ZeroDivisionError:
        return "错误: 除数不能为零"
    except ValueError as e:
        return f"计算错误: {e}"
    except Exception as e:
        return f"表达式解析失败: {e}。请检查表达式格式，支持: +、-、*、/、**、sqrt()、sin()、cos()、pi、e等"


# LangChain工具对象
calculator = Tool(
    name="Calculator",
    func=safe_calculate,
    description="安全数学计算器。输入数学表达式字符串，返回计算结果。"
                "支持基本运算（+、-、*、/、**、%）和math库函数"
                "（sqrt、sin、cos、tan、log、exp、ceil、floor、abs、factorial等），"
                "以及常量pi、e。示例输入：'2+3*4'、'sqrt(16)'、'sin(pi/2)'、'factorial(5)'"
)


# 模块测试
if __name__ == "__main__":
    test_cases = ["2+3*4", "sqrt(16)", "sin(pi/2)", "factorial(5)", "2**10", "log10(1000)"]
    for expr in test_cases:
        print(safe_calculate(expr))
