# -*- coding: utf-8 -*-
"""
database.py - 数据库引擎与会话（技术栈2.1：SQLAlchemy 2.0）
=============================================
用户/认证数据存储：开发默认SQLite，生产可配置MySQL/PostgreSQL（config.database.url）
"""

from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from loguru import logger

from config import get_config


class Base(DeclarativeBase):
    """ORM声明基类"""
    pass


def get_engine(db_url: Optional[str] = None):
    """
    创建SQLAlchemy引擎

    Args:
        db_url: 数据库连接URI（默认从 config.database.url 读取）

    Returns:
        Engine
    """
    cfg = get_config()
    url = db_url or cfg.database.url

    # 确保SQLite数据目录存在
    if url.startswith("sqlite"):
        db_path = url.replace("sqlite:///", "")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # SQLite需要 check_same_thread=False（FastAPI多线程场景）
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_engine(url, echo=False, future=True, **kwargs)
    return engine


def init_db(db_url: Optional[str] = None) -> None:
    """
    初始化数据库（建表）

    Args:
        db_url: 数据库连接URI（默认从配置读取）
    """
    from models import User  # noqa: F401  （确保模型注册到Base.metadata）

    engine = get_engine(db_url)

    # MySQL等需要先确保数据库存在
    cfg = get_config()
    if cfg.database.url.startswith("mysql"):
        _ensure_mysql_database(cfg.database.url)

    Base.metadata.create_all(engine)
    logger.info(f"数据库初始化完成: {cfg.database.url}")


def _ensure_mysql_database(url: str) -> None:
    """MySQL首次运行时自动建库（连接串中的database若不存在则创建）"""
    import re
    import pymysql

    m = re.match(r"mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/([^?]+)", url)
    if not m:
        logger.warning(f"无法解析MySQL连接串: {url}")
        return
    user, pwd, host, port, db = m.groups()
    try:
        conn = pymysql.connect(host=host, port=int(port), user=user, password=pwd, charset="utf8mb4")
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        conn.close()
        logger.info(f"MySQL数据库已确保存在: {db}")
    except Exception as e:
        logger.warning(f"MySQL自动建库失败（请手动创建）: {e}")


def get_session_factory(db_url: Optional[str] = None):
    """创建会话工厂"""
    engine = get_engine(db_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


# 全局会话工厂（延迟初始化）
_session_factory = None


def get_db():
    """FastAPI依赖：获取数据库会话"""
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory()
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()
