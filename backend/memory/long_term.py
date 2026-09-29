# -*- coding: utf-8 -*-
"""
long_term.py - 长期记忆（向量存储）
=============================================
功能：存储关键事实、用户偏好，按语义检索
实现：FAISS向量库 + BGE Embedding
每条记忆带元数据：类型、时间戳、来源
支持持久化到本地磁盘
"""

import os
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


class LongTermMemory:
    """
    长期记忆：FAISS向量存储

    将事实文本通过BGE模型向量化，存入FAISS索引。
    检索时将查询向量化，做余弦相似度搜索，返回TopK最相关事实。
    """

    def __init__(
        self,
        embedding_model: str = "BAAI/bge-small-zh-v1.5",
        persist_dir: str = "./faiss_memory",
        top_k: int = 3,
        similarity_threshold: float = 0.9,
    ):
        """
        Args:
            embedding_model: Embedding模型名称
            persist_dir: 持久化目录
            top_k: 检索返回TopK
            similarity_threshold: 去重相似度阈值
        """
        self.persist_dir = Path(persist_dir)
        self.top_k = top_k
        self.similarity_threshold = similarity_threshold
        self.embedding_model_name = embedding_model

        # 延迟初始化（避免启动时就加载模型）
        self._embeddings = None
        self._vectorstore = None
        self._facts: List[Dict[str, Any]] = []  # 事实元数据列表

        # 尝试加载已有数据
        self._load_facts_metadata()

    def _init_embeddings(self):
        """延迟初始化Embedding模型"""
        if self._embeddings is None:
            from langchain_huggingface import HuggingFaceEmbeddings
            logger.info(f"初始化长期记忆Embedding模型: {self.embedding_model_name}")
            self._embeddings = HuggingFaceEmbeddings(
                model_name=self.embedding_model_name,
                model_kwargs={"device": "cuda"},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embeddings

    def _init_vectorstore(self):
        """延迟初始化FAISS向量库"""
        if self._vectorstore is None:
            from langchain_community.vectorstores import FAISS

            embeddings = self._init_embeddings()
            index_file = self.persist_dir / "index.faiss"

            if index_file.exists():
                try:
                    self._vectorstore = FAISS.load_local(
                        str(self.persist_dir),
                        embeddings,
                        allow_dangerous_deserialization=True,
                    )
                    logger.info(f"加载长期记忆索引: {self.persist_dir}")
                    return
                except Exception as e:
                    logger.warning(f"加载长期记忆索引失败: {e}")

            # 创建空索引（用一个占位文本初始化）
            self._vectorstore = FAISS.from_texts(
                ["__placeholder__"], embeddings, metadatas=[{"placeholder": True}]
            )
            logger.info("创建新的长期记忆索引")

    def _load_facts_metadata(self):
        """加载事实元数据"""
        meta_file = self.persist_dir / "facts_metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    self._facts = json.load(f)
                logger.info(f"加载长期记忆元数据: {len(self._facts)} 条事实")
            except Exception as e:
                logger.warning(f"加载记忆元数据失败: {e}")
                self._facts = []

    def _save_facts_metadata(self):
        """保存事实元数据"""
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        meta_file = self.persist_dir / "facts_metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(self._facts, f, ensure_ascii=False, indent=2)

    def add_fact(
        self,
        content: str,
        fact_type: str = "general",
        source: str = "unknown",
        metadata: Optional[Dict] = None,
    ) -> bool:
        """
        添加一条事实到长期记忆

        Args:
            content: 事实内容
            fact_type: 事实类型（user_fact/preference/general等）
            source: 来源
            metadata: 额外元数据

        Returns:
            bool: 是否添加成功（False表示与已有记忆重复）
        """
        self._init_vectorstore()

        # 去重检查：与已有记忆相似度超过阈值则不存储
        if self._facts:
            similar = self._vectorstore.similarity_search_with_score(content, k=1)
            if similar and similar[0][1] < (1 - self.similarity_threshold):
                # FAISS返回的是L2距离（归一化向量后约等于2-2*cos），距离越小越相似
                # 归一化向量: L2距离 < 0.2 约等于 cos > 0.9
                logger.debug(f"事实与已有记忆相似，跳过存储: {content[:30]}")
                return False

        # 生成事实ID和元数据
        fact_id = str(uuid.uuid4())[:8]
        fact_meta = {
            "id": fact_id,
            "content": content,
            "type": fact_type,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        }
        if metadata:
            fact_meta.update(metadata)

        # 存入FAISS
        self._vectorstore.add_texts(
            [content],
            metadatas=[{k: v for k, v in fact_meta.items() if k != "content"}],
        )

        # 保存元数据
        self._facts.append(fact_meta)
        self._save_facts_metadata()

        # 持久化FAISS索引
        self._vectorstore.save_local(str(self.persist_dir))

        logger.info(f"长期记忆添加事实 [{fact_id}]: {content[:50]}")
        return True

    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        语义检索相关事实

        Args:
            query: 查询文本
            top_k: 返回条数（默认使用配置值）

        Returns:
            List[Dict]: 相关事实列表，每条含content/metadata/score
        """
        if not self._facts:
            return []

        self._init_vectorstore()
        k = top_k or self.top_k

        try:
            results = self._vectorstore.similarity_search_with_score(query, k=k)
        except Exception as e:
            logger.error(f"长期记忆检索失败: {e}")
            return []

        facts = []
        for doc, score in results:
            # 跳过占位符
            if doc.metadata.get("placeholder"):
                continue
            # 转换L2距离为相似度分数（归一化向量: similarity = 1 - L2/2）
            similarity = max(0, 1 - score / 2)
            facts.append({
                "content": doc.page_content,
                "metadata": doc.metadata,
                "similarity": round(similarity, 4),
            })

        return facts

    def get_all_facts(self) -> List[Dict[str, Any]]:
        """获取所有事实"""
        return self._facts.copy()

    def clear(self) -> None:
        """清空长期记忆"""
        self._facts = []
        self._vectorstore = None
        # 删除持久化文件
        import shutil
        if self.persist_dir.exists():
            shutil.rmtree(self.persist_dir)
        logger.info("长期记忆已清空")

    @property
    def count(self) -> int:
        """事实数量"""
        return len(self._facts)
