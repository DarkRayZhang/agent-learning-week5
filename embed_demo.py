"""
Week 5 Embedding 演示（脚手架）
===============================
跑通：python embed_demo.py
展示：3 个句子 → embedding 向量（打印维度）→ 两两 cosine 相似度
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
# Embedding 走第三方 OpenAI 兼容端点（DeepSeek 官方 API 无 embedding，2026-08 实测 /embeddings 返回 404）
# 配置见 .env：EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL
client = OpenAI(
    api_key=os.getenv("EMBEDDING_API_KEY"),
    base_url=os.getenv("EMBEDDING_BASE_URL"),
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")

SENTENCES = [
    "狗是人类的好朋友",
    "宠物需要主人的关爱",
    "汽车是现代交通工具",
]


def embed(text: str):
    """把文本转成 embedding 向量。"""
    resp = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text],
    )
    return resp.data[0].embedding


def cosine(a, b):
    """cosine 相似度：a·b / (|a|*|b|)。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


if __name__ == "__main__":
    vecs = [embed(s) for s in SENTENCES]
    print(f"向量维度: {len(vecs[0])}")
    for i in range(len(SENTENCES)):
        for j in range(i + 1, len(SENTENCES)):
            print(f"cosine({SENTENCES[i][:8]}..., {SENTENCES[j][:8]}...) = {cosine(vecs[i], vecs[j]):.4f}")
