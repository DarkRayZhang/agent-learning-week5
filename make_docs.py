"""
Week 5 生成 100 篇模拟文档（脚手架）
===================================
跑通：python make_docs.py  → 在 docs/ 下生成 100 篇 .md 文档
内容：围绕几个主题（购物/编程/日程/健康/旅行）造数据，方便切块向量化检索。
"""
import os, random

TOPICS = {
    "shopping": ["牛奶", "鸡蛋", "面包", "水果", "咖啡", "纸巾", "洗发水", "大米", "酱油", "零食"],
    "coding": ["git", "python", "java", "docker", "api", "数据库", "缓存", "测试", "部署", "日志"],
    "schedule": ["交周报", "开会", "健身", "复习", "买菜", "体检", "看电影", "聚餐", "出差", "考试"],
    "health": ["跑步", "早睡", "喝水", "蔬菜", "散步", "瑜伽", "体检", "疫苗", "睡眠", "早餐"],
    "travel": ["机票", "酒店", "景点", "护照", "行李", "地铁", "美食", "天气", "纪念品", "攻略"],
}


def main():
    os.makedirs("docs", exist_ok=True)
    for i in range(1, 101):
        topic, items = random.choice(list(TOPICS.items()))
        picked = random.sample(items, random.randint(2, 4))
        content = f"# 文档 {i}\n\n主题：{topic}\n\n"
        content += "我今天的安排：\n- " + "\n- ".join(picked) + "\n"
        with open(f"docs/doc_{i:03d}.md", "w", encoding="utf-8") as f:
            f.write(content)
    print(f"已生成 100 篇文档到 docs/")


if __name__ == "__main__":
    main()
