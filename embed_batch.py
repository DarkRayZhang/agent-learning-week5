"""
Week 5 · 批量 embedding（支持超过 10 条自动切块）
================================================
为什么需要这个：百炼 text-embedding-v4 单次 input 最多 10 条，
超了不会帮你切，会直接报错。周末 100 篇文档入库必然踩到。

跑通：python embed_batch.py
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("EMBEDDING_API_KEY"),
    base_url=os.getenv("EMBEDDING_BASE_URL"),
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")

# 百炼 text-embedding-v4 单次上限（官方文档：Batch size = 10）
BATCH_SIZE = 10


def embed_batch(texts, batch_size=BATCH_SIZE):
    """把一批文本转成向量，超过 batch_size 自动切块。

    Args:
        texts: 文本列表，任意长度
        batch_size: 每批最多几条，默认 10（百炼 v4 上限）
    Returns:
        向量列表，**顺序与 texts 严格一致**
    """
    vectors = [None] * len(texts)
    for start in range(0, len(texts), batch_size):
        chunk = texts[start:start + batch_size]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=chunk)
        for item in resp.data:
            vectors[start + item.index] = item.embedding
    return vectors


def embed(text):
    """单条文本转向量（复用批量逻辑，避免两套代码）。"""
    return embed_batch([text])[0]


def cosine(a, b):
    """cosine 相似度：a·b / (|a|*|b|)。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


if __name__ == "__main__":
    # 12 条 > 10，用来验证确实切成了 2 批
    SENTENCES = [
        "狗是人类的好朋友",
        "宠物需要主人的关爱",
        "猫粮哪个牌子好",
        "狗狗生病了怎么办",
        "宠物医院哪家靠谱",
        "汽车是现代交通工具",
        "新能源汽车销量增长",
        "冬天汽车保养注意事项",
        "咖啡和茶的区别",
        "手冲咖啡入门教程",
        "绿茶的功效与作用",
        "周末去哪里自驾游",
    ]

    print(f"输入 {len(SENTENCES)} 条，BATCH_SIZE={BATCH_SIZE} → 应切成 2 批")
    vecs = embed_batch(SENTENCES)

    print(f"返回 {len(vecs)} 个向量，维度 {len(vecs[0])}")
    assert len(vecs) == len(SENTENCES), "数量对不上"
    assert all(v is not None for v in vecs), "有位置没被回填（index 对齐有问题）"

    # 抽查顺序：第 0 条「狗」应与第 1 条「宠物」近，与第 5 条「汽车」远
    print(f"狗 ↔ 宠物 : {cosine(vecs[0], vecs[1]):.4f}")
    print(f"狗 ↔ 汽车 : {cosine(vecs[0], vecs[5]):.4f}")
    print(f"咖啡 ↔ 绿茶 : {cosine(vecs[8], vecs[10]):.4f}")
