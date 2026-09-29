# -*- coding: utf-8 -*-
"""
create_sample_db.py - 创建示例SQLite数据库
=============================================
创建一个模拟企业数据库，包含员工表、部门表、薪资表，
供SQL查询工具测试使用。
"""

import sqlite3
import os
from pathlib import Path


def create_sample_db(db_path: str = "data/example.db"):
    """创建示例数据库"""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果数据库已存在，先删除
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # ---------- 部门表 ----------
    cursor.execute("""
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        manager TEXT,
        budget REAL,
        location TEXT
    )
    """)

    departments = [
        (1, "技术部", "张三", 5000000, "北京"),
        (2, "产品部", "李四", 3000000, "北京"),
        (3, "市场部", "王五", 4000000, "上海"),
        (4, "人力资源部", "赵六", 1500000, "北京"),
        (5, "财务部", "钱七", 2000000, "深圳"),
    ]
    cursor.executemany("INSERT INTO departments VALUES (?,?,?,?,?)", departments)

    # ---------- 员工表 ----------
    cursor.execute("""
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        department_id INTEGER,
        position TEXT,
        salary REAL,
        hire_date TEXT,
        email TEXT,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )
    """)

    employees = [
        (1, "张伟", 1, "高级工程师", 25000, "2022-03-15", "zhangwei@company.com"),
        (2, "李娜", 1, "工程师", 18000, "2023-01-10", "lina@company.com"),
        (3, "王强", 1, "技术总监", 45000, "2020-06-20", "wangqiang@company.com"),
        (4, "刘洋", 2, "产品经理", 22000, "2022-09-01", "liuyang@company.com"),
        (5, "陈静", 2, "产品助理", 12000, "2024-02-14", "chenjing@company.com"),
        (6, "杨帆", 3, "市场经理", 20000, "2021-11-08", "yangfan@company.com"),
        (7, "赵敏", 3, "市场专员", 13000, "2023-07-22", "zhaomin@company.com"),
        (8, "孙磊", 4, "HR主管", 19000, "2021-04-18", "sunlei@company.com"),
        (9, "周婷", 4, "HR专员", 11000, "2024-01-05", "zhouting@company.com"),
        (10, "吴昊", 5, "财务主管", 21000, "2020-12-01", "wuhao@company.com"),
        (11, "郑爽", 5, "会计", 14000, "2023-03-20", "zhengshuang@company.com"),
        (12, "冯雪", 1, "前端工程师", 20000, "2022-08-10", "fengxue@company.com"),
        (13, "褚明", 1, "后端工程师", 22000, "2022-05-25", "chuming@company.com"),
        (14, "卫龙", 3, "市场总监", 38000, "2019-03-12", "weilong@company.com"),
        (15, "蒋欣", 2, "高级产品经理", 28000, "2021-07-30", "jiangxin@company.com"),
    ]
    cursor.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?,?)", employees)

    # ---------- 项目表 ----------
    cursor.execute("""
    CREATE TABLE projects (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        department_id INTEGER,
        budget REAL,
        status TEXT,
        start_date TEXT,
        end_date TEXT,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )
    """)

    projects = [
        (1, "智能客服系统", 1, 800000, "进行中", "2025-06-01", "2026-12-31"),
        (2, "移动端APP改版", 2, 500000, "进行中", "2025-09-15", "2026-06-30"),
        (3, "品牌推广计划", 3, 1200000, "已完成", "2025-01-01", "2025-12-31"),
        (4, "ERP系统升级", 5, 600000, "规划中", "2026-03-01", "2026-12-31"),
        (5, "AI Agent平台", 1, 1500000, "进行中", "2025-10-01", "2026-09-30"),
    ]
    cursor.executemany("INSERT INTO projects VALUES (?,?,?,?,?,?,?)", projects)

    conn.commit()
    conn.close()

    print(f"示例数据库已创建: {db_path}")
    print(f"  - departments: {len(departments)} 条")
    print(f"  - employees: {len(employees)} 条")
    print(f"  - projects: {len(projects)} 条")


if __name__ == "__main__":
    create_sample_db()
