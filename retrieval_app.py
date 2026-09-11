"""
Week 5 语义检索小程序（脚手架）
===============================
跑通：先 make_docs.py 生成文档 → python retrieval_app.py
功能：把 docs/ 下 100 篇文档切块 → embedding 入库（Chroma 持久化）→ 输入 query 返回 Top-3。
"""
import os, glob
from dotenv import load_dotenv
from openai import OpenAI
import chromadb

load_dotenv()
# Embedding 走第三方 OpenAI 兼容端点（DeepSeek 官方 API 无 embedding，2026-08 实测 404），配置见 .env
client = OpenAI(
    api_key=os.getenv("EMBEDDING_API_KEY"),
    base_url=os.getenv("EMBEDDING_BASE_URL"),
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")

COLLECTION = "week5_docs"
PERSIST_DIR = "./chroma_db"


def embed(text: str):
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return resp.data[0].embedding


def chunk_docs():
    """读取 docs/*.md，按段落切块，返回 [(chunk_text, metadata)]。"""
    chunks = []
    for path in glob.glob("docs/*.md"):
        text = open(path, encoding="utf-8").read()
        for para in text.split("\n\n"):
            if para.strip():
                chunks.append((para.strip(), {"source": os.path.basename(path)}))
    return chunks


def build_index():
    chroma = chromadb.PersistentClient(path=PERSIST_DIR)
    # ⚠️ 必须显式声明 cosine：Chroma 默认是 l2（实测 col.configuration =
    #    {'hnsw': {'space': 'l2', ...}}），与本周「用余弦」的结论矛盾。
    #    space 在 collection 创建时就绑死（属 collection 元数据），事后改不了。
    col = chroma.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    if col.count() > 0:
        return col
    chunks = chunk_docs()
    ids, docs, metas, vecs = [], [], [], []
    for i, (text, meta) in enumerate(chunks):
        ids.append(f"c{i}")
        docs.append(text)
        metas.append(meta)
        vecs.append(embed(text))
    col.add(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)
    print(f"已入库 {len(chunks)} 个切块")
    return col


def search(query: str, top_k: int = 3):
    col = build_index()
    q = embed(query)
    res = col.query(query_embeddings=[q], n_results=top_k)
    return res["documents"][0], res["metadatas"][0]


def main():
    print("语义检索小程序已启动，输入 exit 退出")
    while True:
        q = input("查> ").strip()
        if q.lower() in {"exit", "q"}:
            break
        docs, metas = search(q)
        for d, m in zip(docs, metas):
            print(f"  [{m.get('source','?')}] {d[:60]}...")


if __name__ == "__main__":
    main()
