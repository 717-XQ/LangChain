# -*- coding: utf-8 -*-
"""
update_eval_answers.py - 将标准答案写入eval_tasks.json
=============================================
将用户提供的30条任务标准答案（answer + check）写入eval_tasks.json
"""

import json

# 用户提供的标准答案
ANSWERS = {
    1: {"answer": "12288", "check": "结果为 12288"},
    2: {"answer": "39", "check": "12 + 27 = 39"},
    3: {"answer": "1060", "check": "质数 [2,3,5,...,97] 之和为 1060"},
    4: {"answer": "1,1,2,3,5,8,13,21,34,55,89,144,233,377,610,987,1597,2584,4181,6765", "check": "输出应包含 1,1,2,3,5,8 且共20项"},
    5: {"answer": "[11,12,22,25,34,64,90]", "check": "排序后应为升序 [11,12,22,25,34,64,90]"},
    6: {"answer": "employees, departments, projects", "check": "应返回三张表", "sql": "SHOW TABLES;"},
    7: {"answer": "5", "check": "技术部员工数 = 5", "sql": "SELECT COUNT(*) FROM employees e JOIN departments d ON e.dept_id = d.id WHERE d.name = '技术部';"},
    8: {"answer": "王强, 45000", "check": "最高薪资员工为王强 45000", "sql": "SELECT name, salary FROM employees ORDER BY salary DESC LIMIT 1;"},
    9: {"answer": "技术部 > 产品部 > 市场部", "check": "降序返回各部门平均薪资，含技术部/产品部/市场部"},
    10: {"answer": "张伟, 冯雪, 褚明, 刘洋", "check": "应包含 张伟、冯雪、褚明、刘洋"},
    11: {"answer": "智能客服(系统)、APP、Agent 等项目", "check": "应包含 智能客服、APP、Agent 相关项目"},
    12: {"answer": "参考要点：2026-09 OpenAI 发布 GPT-6 Astra（宣称进入 AGI 时代）；多模态大模型、智能体（Agent）、空间智能、AI 具身智能、AI 治理与安全等为年度主线。", "check": "回复应提到 AI / 人工智能 相关进展"},
    13: {"answer": "运行当天日期，如 2026-09-04 星期五", "check": "应输出运行当日日期（年份为2026）与星期"},
    14: {"answer": "≈ 176.71", "check": "π×7.5² = 56.25π ≈ 176.71（约176）"},
    15: {"answer": "hello:3, world:1, python:1, ai:1", "check": "hello 出现 3 次"},
    16: {"answer": "王强、张伟、褚明、蒋欣、卫龙", "check": "应包含 王强/张伟/褚明/蒋欣/卫龙"},
    17: {"answer": "120", "check": "10!/(3!7!) = 120"},
    18: {"answer": "12321 → True, 12345 → False", "check": "12321 为回文(True)，12345 不是(False)"},
    19: {"answer": "深圳", "check": "财务部城市 = 深圳", "sql": "SELECT city FROM departments WHERE name = '财务部';"},
    20: {"answer": "要点：实验性 JIT 编译器(PEP 744)、可选的自由线程(无 GIL, PEP 703)、全新交互式 REPL、typing.Self / typing.Never、PEP 695 原生泛型语法、collections.Counter 性能优化等。", "check": "回复应提到 Python 及 3.13 相关新特性"},
    21: {"answer": "最大值=9, 最小值=1, 平均值=5.0", "check": "max=9, min=1, avg=5"},
    22: {"answer": "AI Agent, 1500000", "check": "预算最高项目为 AI Agent，金额 1500000", "sql": "SELECT name, budget FROM projects ORDER BY budget DESC LIMIT 1;"},
    23: {"answer": "1", "check": "0.5 + 0.5 = 1"},
    24: {"answer": "无固定答案（数据自定义），关键是输出按成绩降序排列", "check": "输出应为按成绩从高到低排序的学生字典"},
    25: {"answer": "1", "check": "已完成项目数 = 1", "sql": "SELECT COUNT(*) FROM projects WHERE status = '已完成';"},
    26: {"answer": "RAG = Retrieval-Augmented Generation，检索增强生成：先从外部知识库检索相关文档，再作为上下文提供给大模型生成更准确的回答，解决知识过时/幻觉/私有数据问题。", "check": "回复应包含 检索 与 生成 概念"},
    27: {"answer": "30", "check": "10 × 3 = 30"},
    28: {"answer": "无固定答案（矩阵随机生成），关键是输出该矩阵对应的行列式数值", "check": "应输出一个行列式数值；示例(seed=42)矩阵行列式为 -4812"},
    29: {"answer": "示例：张伟 / 技术部 / 25000", "check": "应包含 张伟-技术部-25000 等联表结果"},
    30: {"answer": "LangChain 1.0 于 2025-10 发布（langchain-core / LangGraph 1.0 编排运行时 / create_agent 标准入口）；核心能力：统一模型抽象、Prompt/Chain、工具调用、RAG、Agent 编排、可观测(LangSmith)。", "check": "回复应提到 LangChain 及主要功能/版本"},
}

# 读取现有eval_tasks.json
eval_path = r'D:\ronghua_pythoncode\projcet\LangChain\tests\eval_tasks.json'
with open(eval_path, 'r', encoding='utf-8') as f:
    tasks = json.load(f)

# 备份
backup_path = eval_path.replace('.json', '_backup.json')
with open(backup_path, 'w', encoding='utf-8') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)
print(f"原文件已备份到: {backup_path}")

# 将标准答案写入
updated = 0
for task in tasks:
    task_id = task['id']
    if task_id in ANSWERS:
        ans = ANSWERS[task_id]
        task['answer'] = ans['answer']
        task['check'] = ans['check']
        if 'sql' in ans:
            task['expected_sql'] = ans['sql']
        updated += 1

print(f"已更新 {updated}/{len(tasks)} 条任务的标准答案")

# 保存
with open(eval_path, 'w', encoding='utf-8') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)

print(f"已保存到: {eval_path}")
print(f"第一条任务现在的字段: {list(tasks[0].keys())}")
print(f"示例: id={tasks[0]['id']}, answer={tasks[0]['answer'][:50]}, check={tasks[0]['check'][:50]}")
