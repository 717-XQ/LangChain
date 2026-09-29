# -*- coding: utf-8 -*-
"""
doc_qa.py - 文档问答工具（RAG）
=============================================
功能：基于内部文档库回答问题
实现：FAISS向量库 + BGE Embedding + LLM生成回答
支持格式：.txt、.md、.pdf、.docx
首次使用时自动构建向量索引
"""

import os
from pathlib import Path
from typing import Optional, List
from loguru import logger

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from langchain_core.tools import Tool


class DocumentQATool:
    """
    文档问答工具（RAG）

    工作流程：
      1. 加载docs_dir中的文档
      2. 文本分块
      3. BGE向量化存入FAISS
      4. 问题向量化检索TopK相关块
      5. LLM基于检索内容生成回答
    """

    def __init__(self, config=None):
        """
        初始化文档问答工具

        Args:
            config: 应用配置（为None时从全局加载）
        """
        from config import get_config
        from langchain_huggingface import HuggingFaceEmbeddings

        if config is None:
            config = get_config()

        self.config = config
        self.qa_config = config.tools.doc_qa
        self.vectorstore = None
        self.llm = None

        # 初始化Embedding模型
        logger.info(f"初始化文档QA Embedding模型: {self.qa_config.embedding_model}")
        self.embeddings = HuggingFaceEmbeddings(
            model_name=self.qa_config.embedding_model,
            model_kwargs={"device": "cuda"},
            encode_kwargs={"normalize_embeddings": True},
        )

    def _load_documents(self) -> list:
        """加载文档目录中的所有文档"""
        from langchain_community.document_loaders import (
            TextLoader, PyMuPDFLoader, Docx2txtLoader
        )
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        docs_dir = Path(self.qa_config.docs_dir)
        if not docs_dir.exists():
            logger.warning(f"文档目录不存在: {docs_dir}")
            return []

        documents = []
        supported_extensions = {".txt", ".md", ".pdf", ".docx"}

        for file_path in docs_dir.rglob("*"):
            if file_path.suffix.lower() not in supported_extensions:
                continue

            try:
                if file_path.suffix.lower() in (".txt", ".md"):
                    loader = TextLoader(str(file_path), encoding="utf-8")
                elif file_path.suffix.lower() == ".pdf":
                    loader = PyMuPDFLoader(str(file_path))
                elif file_path.suffix.lower() == ".docx":
                    loader = Docx2txtLoader(str(file_path))
                else:
                    continue

                docs = loader.load()
                # 添加来源元数据
                for doc in docs:
                    doc.metadata["source"] = file_path.name
                documents.extend(docs)
                logger.info(f"加载文档: {file_path.name} ({len(docs)} 段)")

            except Exception as e:
                logger.error(f"加载文档失败 {file_path}: {e}")

        # 文本分块
        if documents:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.qa_config.chunk_size,
                chunk_overlap=self.qa_config.chunk_overlap,
                separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            )
            documents = splitter.split_documents(documents)
            logger.info(f"文档分块完成: {len(documents)} 个文本块")

        return documents

    def build_index(self) -> bool:
        """
        构建向量索引

        Returns:
            bool: 是否成功构建
        """
        from langchain_community.vectorstores import FAISS

        persist_dir = Path(self.qa_config.persist_dir)

        # 如果已有持久化索引，直接加载
        index_file = persist_dir / "index.faiss"
        if index_file.exists():
            try:
                logger.info(f"加载已有文档索引: {persist_dir}")
                self.vectorstore = FAISS.load_local(
                    str(persist_dir),
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                return True
            except Exception as e:
                logger.warning(f"加载索引失败，重新构建: {e}")

        # 加载文档并构建索引
        documents = self._load_documents()
        if not documents:
            logger.warning("没有可索引的文档")
            return False

        logger.info(f"构建文档向量索引 ({len(documents)} 个块)...")
        self.vectorstore = FAISS.from_documents(documents, self.embeddings)

        # 持久化
        persist_dir.mkdir(parents=True, exist_ok=True)
        self.vectorstore.save_local(str(persist_dir))
        logger.info(f"文档索引已保存: {persist_dir}")
        return True

    def _get_llm(self):
        """获取LLM实例（延迟初始化）"""
        if self.llm is None:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=self.config.llm.model,
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url,
                temperature=0.1,
                max_tokens=self.config.llm.max_tokens,
            )
        return self.llm

    def query(self, question: str) -> str:
        """
        查询文档并生成回答

        Args:
            question: 用户问题

        Returns:
            str: 基于文档的回答
        """
        # 确保索引已构建
        if self.vectorstore is None:
            if not self.build_index():
                return ("文档库为空或未初始化。请将文档(.txt/.md/.pdf/.docx)放入 "
                       f"{self.qa_config.docs_dir} 目录。")

        # 检索相关文档
        try:
            docs = self.vectorstore.similarity_search(question, k=self.qa_config.top_k)
        except Exception as e:
            return f"文档检索失败: {e}"

        if not docs:
            return "在文档库中未找到相关内容。"

        # 构建上下文
        context_parts = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "未知来源")
            context_parts.append(f"[文档{i+1}] (来源: {source})\n{doc.page_content}")
        context = "\n\n".join(context_parts)

        # LLM生成回答
        prompt = f"""你是一个文档问答助手。请根据以下参考文档内容回答用户问题。
要求：
1. 只基于提供的文档内容回答，不要编造信息
2. 如果文档中没有相关信息，明确说明
3. 回答时标注信息来源

参考文档：
{context}

用户问题：{question}

请给出回答："""

        try:
            response = self._get_llm().invoke(prompt)
            answer = response.content
            logger.info(f"文档QA完成: {question[:50]}...")
            return answer
        except Exception as e:
            return f"生成回答失败: {e}"


def get_doc_qa_tool(config=None) -> Optional[Tool]:
    """
    创建文档问答LangChain工具

    Args:
        config: 应用配置

    Returns:
        Tool: 文档问答工具（如果初始化失败返回None）
    """
    try:
        qa_tool = DocumentQATool(config)
        # 尝试构建索引（如果文档目录为空则不创建工具）
        return Tool(
            name="DocQA",
            func=qa_tool.query,
            description="查询内部文档库获取答案。输入问题字符串，基于公司文档、产品手册、"
                        "规章制度等内部资料回答。适用场景：公司制度查询、产品文档问答、"
                        "内部知识检索。示例输入：'公司的考勤制度是什么？'"
        )
    except Exception as e:
        logger.warning(f"文档QA工具初始化失败: {e}")
        return None
