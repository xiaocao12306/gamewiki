"""
build_vector_index.py
---------------------
把 Markdown 攻略文章切块 → 嵌入 → 建 FAISS 向量库（CPU 版即可）
"""

import os
from pathlib import Path

# ------- 1. 依赖 --------
from langchain_community.document_loaders import TextLoader              # 文本加载器
from langchain_text_splitters import (                                  # 两级切块
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_community.embeddings import HuggingFaceEmbeddings        # 中文多语向量
from langchain_community.vectorstores import FAISS                      # 向量库
import faiss                                                            # 数值后端

# ------- 2. 路径配置 --------
BASE_DIR = Path(__file__).resolve().parents[3]     # <project>/src/...
MD_PATH  = BASE_DIR / "data" / "warbondmd.md"

# ------- 3. 读取并分块 --------
loader = TextLoader(MD_PATH, encoding="utf-8")
raw_docs = loader.load()                                               # List[Document]
markdown_text = raw_docs[0].page_content

# 3.1 按 Markdown 标题切
headers_to_split_on = [("#", "H1"), ("##", "H2"), ("###", "H3")]
hdr_splitter = MarkdownHeaderTextSplitter(headers_to_split_on)
section_docs = hdr_splitter.split_text(markdown_text)                  # List[Document]

# 3.2 再按长度切
rc_splitter = RecursiveCharacterTextSplitter(chunk_size=400,
                                             chunk_overlap=50)
docs = rc_splitter.split_documents(section_docs)

# ------- 4. 构建向量库 --------
model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
embedder   = HuggingFaceEmbeddings(model_name=model_name)

vector_store = FAISS.from_documents(docs, embedder)                    # 一行搞定
vector_store.save_local("helljump2_faiss")                             # 文件夹持久化

print(f"Saved {len(docs)} chunks → helljump2_faiss/")

# ------- 5. 重新加载 & 简单查询验证 --------
vec_store = FAISS.load_local(
    "helljump2_faiss",
    embeddings=embedder,
    allow_dangerous_deserialization=True          # <0.2.x 版本仍需
)

retriever = vec_store.as_retriever(search_type="similarity", k=3)
query = "地狱潜兵2 虫族最佳配装思路"
hits  = retriever.invoke(query)

print("\n--- Top-3 相似片段 ---")
for i, d in enumerate(hits, 1):
    header = d.metadata.get("H3") or d.metadata.get("H2") \
             or d.metadata.get("H1") or "N/A"
    print(f"{i}. [{header}] {d.page_content[:70]}…")
