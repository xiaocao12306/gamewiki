from langchain_community.embeddings import HuggingFaceEmbeddings        # 中文多语向量
from langchain_community.vectorstores import FAISS

model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
embedder   = HuggingFaceEmbeddings(model_name=model_name)

# ------- 5. 重新加载 & 简单查询验证 --------
vec_store = FAISS.load_local(
    "helljump2_faiss",
    embeddings=embedder,
    allow_dangerous_deserialization=True          # <0.2.x 版本仍需
)

retriever = vec_store.as_retriever(search_type="similarity", k=3)
query = "地狱潜兵2 战争债券推荐顺序"
hits  = retriever.invoke(query)

print("\n--- Top-3 相似片段 ---")
for i, d in enumerate(hits, 1):
    header = d.metadata.get("H3") or d.metadata.get("H2") \
             or d.metadata.get("H1") or "N/A"
    print(f"{i}. [{header}] {d.page_content[:70]}…")
