# -*- coding: utf-8 -*-
"""
Week 5 · 导出检索样例 → docs/sample_retrieval.json
==================================================
跑通（在 week5/ 目录下）：
    python export_samples.py

【这个文件是给谁用的】
W7 要把 W5 的检索能力并入主线「备忘录检索」。Java 版（Spring AI VectorStore）必须能复现
Python 版的同一批结果 —— 所以需要一个**冻结的基准**：同样的 query → 同样的 Top-3
（source / chunk_index / 相似度 / 原文块）。它同时是 W6「拼上下文」的输入样例：
`hits[].text` 就是可以直接拼进 prompt 的原文块，`context_chars` 是拼完的字符量级。

【本文件与「普通测试集」的区别：判定 ≠ 内容】
判定（命中/拒答）只看 similarity，但**相似度高的块未必讲了你要的东西**。
本次实测当场抓到一条：问「怎么防止重复扣款」返回 similarity 0.5506 的
「通勤路线 / 机场值机」块 —— 判定是「命中」，内容却完全不相干。
所以每条用例除 `expect`（期望判定）外还有 `expect_sections`（期望命中的小节），
并单独输出 `section_ok` / `top1_section_count`：
    section_ok          判定对了，内容也对不对
    top1_section_count  Top-1 块混了几个小节（1 = 纯，≥3 = 混杂）
**命中率满分 + section 命中率不满分**，才是这个语料库的真实水平。

【原则：不写第二套】
用例 → 检索 → 判定 全部复用 retrieval_app 的 load_index / retrieve / decide / section_of。
本文件只做「跑一遍 + 落盘 JSON」，不含任何独立的检索或阈值逻辑 ——
否则 W6 标定阈值时会出现两个真相（同 09-16 修掉的「判据写了两遍」是同一类坑）。

【为什么放 docs/ 且是 .json】
build_index.py 只扫 `docs/*.md`（glob "*.md"），所以这个 JSON 不会被切块入库、
不会污染语料。放 docs/ 是因为它的语义是「检索样例」，与语料同属测试资产。
"""
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import retrieval_app as ra            # noqa: E402  —— 必须在 sys.path 插入之后

OUT_PATH = os.path.join(BASE_DIR, "docs", "sample_retrieval.json")
BUILD_REPORT = os.path.join(BASE_DIR, "index_build_report.txt")

TOP_K = 3

# 「发布值班」主题的 6 个小节（与 retrieval_app.PUBLISH_SECTIONS 同源，不另写一套）
PUBLISH_SECTIONS = ["发版窗口", "灰度策略", "回滚预案", "变更评审", "监控告警", "事故复盘"]

# ── 用例集 ──────────────────────────────────────────────────────────────
# (group, expect, query, expect_sections)
#   group          见 GROUP_LEGEND
#   expect         期望判定（"命中" / "拒答"）
#   expect_sections 期望 Top-1 块命中的小节；None = 不判内容（拒答类没有正确答案）
CASES = [
    # ── hit_main：6 个语料主题各 1 条，刻意用「绕弯问法」（不照抄小节标题）
    #    → 检验**语义泛化**：用户不会用你写文档时的词来提问
    ("hit_main", "命中", "我什么时候得交周报", ["交周报"]),
    ("hit_main", "命中", "怎么防止重复扣款", ["接口幂等"]),          # ← 实测内容跑偏（见文件头说明）
    ("hit_main", "命中", "晚上老醒睡不踏实怎么办", ["睡眠"]),
    ("hit_main", "命中", "出差坐飞机有什么要注意的", ["机场值机", "行李清单"]),
    ("hit_main", "命中", "空调需要定期清理吗", ["家电维护"]),
    ("hit_main", "命中", "线上出故障了怎么快速止损", ["回滚预案", "事故复盘"]),

    # ── hit_variants：同一主题（发布值班）换 5 种说法
    #    → 检验**稳定性**：Top-1 该始终落在同一主题（=验收 2，与 notes.md 同源）
    ("hit_variants", "命中", "发版前必须确认什么", PUBLISH_SECTIONS),
    ("hit_variants", "命中", "上线之前要做哪些检查", PUBLISH_SECTIONS),
    ("hit_variants", "命中", "回滚方案要满足什么条件", PUBLISH_SECTIONS),
    ("hit_variants", "命中", "怎么保证发布不出事故", PUBLISH_SECTIONS),
    ("hit_variants", "命中", "发布当天要注意些什么", PUBLISH_SECTIONS),

    # ── reject：语料故意未写的话题（见 make_docs.py 第 15 行）
    #    → 期望拒答。这是 W6 幻觉防线的前置基线
    ("reject", "拒答", "量子计算的量子比特怎么实现", None),
    ("reject", "拒答", "宠物猫得了猫瘟怎么治", None),
    ("reject", "拒答", "股票开户需要什么条件", None),
    ("reject", "拒答", "多肉植物怎么养才不会烂根", None),
    ("reject", "拒答", "零基础学吉他要先练什么", None),

    # ── boundary：沾边但库内无答案（语料提过「显示器垫到视线平齐」，但没讲「买多大」）
    #    → **观察项，不计通过率**：实测 0.4403 距阈值 0.45 仅 0.01，证明灰区确实贴着阈值
    ("boundary", "拒答", "显示器该买多大的", None),
]

GROUP_LEGEND = {
    "hit_main": "跨 6 个语料主题各 1 条，绕弯问法（不照抄小节标题）→ 期望命中",
    "hit_variants": "同一主题（发布值班）换 5 种说法 → 期望 Top-1 稳定落在同一主题",
    "reject": "语料故意未写的话题（make_docs.py 第 15 行）→ 期望拒答，不拿训练知识硬答",
    "boundary": "沾边但库内无答案 → 观察阈值灰区行为，不计通过率",
}


def read_build_report():
    """读 index_build_report.txt → dict。

    索引指纹直接引用构建时的报告，而不是在这里重写一遍常量 ——
    常量写两遍就会漂移（改了 build_index.py 的 CHUNK_SIZE，这里不会跟着变）。
    """
    info = {}
    if not os.path.isfile(BUILD_REPORT):
        return info
    with open(BUILD_REPORT, encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.strip()] = v.strip()
    return info


def build_case(col, cid, group, expect, query, expect_sections, top_k=TOP_K):
    """跑一次完整检索 → 一条可 JSON 化的记录。"""
    hits = ra.retrieve(col, query, top_k=top_k)
    verdict = ra.decide(hits)                     # 唯一判据，与 CLI / --selftest 共用

    top1_sections = ra.section_of(hits[0][0]).split(" / ") if hits else []
    has_title = not (len(top1_sections) == 1 and top1_sections[0] == ra.section_of(""))
    # expect_sections 为 None 时不判内容（拒答类没有"正确答案"）
    section_ok = None
    if expect_sections is not None and hits:
        section_ok = any(s in expect_sections for s in top1_sections)

    return {
        "id": cid,
        "group": group,
        "expect": expect,
        "query": query,
        "verdict": verdict,
        "matched": verdict == expect,
        "top1_similarity": round(hits[0][2], 4) if hits else None,
        "context_chars": sum(len(d) for d, _, _ in hits),   # Top-K 原文总字符数

        # ── 内容维度（与判定分开）────────────────────────────────────
        "expect_sections": expect_sections,
        "top1_sections": top1_sections,
        "top1_has_title": has_title,
        "top1_section_count": len(top1_sections),
        "section_ok": section_ok,

        "hits": [
            {
                "rank": i,
                "similarity": round(sim, 4),
                "source": meta.get("source"),
                "chunk_index": meta.get("chunk_index"),
                "n_chars": meta.get("n_chars"),
                "sections": ra.section_of(doc).split(" / "),  # 命中的 markdown 小节
                "text": doc,                                  # 完整原文块（拼 prompt 用）
            }
            for i, (doc, meta, sim) in enumerate(hits, 1)
        ],
    }


def main():
    col = ra.load_index()
    report = read_build_report()
    print(f"语义检索样例导出 ｜ collection「{ra.COLLECTION}」{col.count()} 块 ｜ "
          f"模型 {ra.EMBEDDING_MODEL} ｜ 用例 {len(CASES)} 条 / top_k={TOP_K}")
    print("=" * 78)

    cases, sims = [], {}
    for n, (group, expect, query, expect_sections) in enumerate(CASES, 1):
        cid = f"{group}-{n:02d}"
        case = build_case(col, cid, group, expect, query, expect_sections)
        cases.append(case)
        sims.setdefault(group, []).append(case["top1_similarity"])

        if not case["matched"]:
            flag = "👁 " if group == "boundary" else "❌"
        elif case["section_ok"] is False:
            flag = "🧩"          # 判定对了，内容跑偏
        else:
            flag = "✅"
        top1 = case["hits"][0]["source"] if case["hits"] else "-"
        secs = " / ".join(case["top1_sections"]) or "-"
        mix = f"[{case['top1_section_count']}]" if case["top1_section_count"] >= 3 else ""
        print(f"  {flag} {query:<16s} {case['verdict']}  "
              f"top1={case['top1_similarity']}  {top1}  {secs} {mix}")

    # ── 汇总：判定维度 + 内容维度分开算 ────────────────────────────────
    by_group = {}
    for group in GROUP_LEGEND:
        sub = [c for c in cases if c["group"] == group]
        if not sub:
            continue
        by_group[group] = {
            "n": len(sub),
            "matched": sum(c["matched"] for c in sub),
            "pass_rate": round(sum(c["matched"] for c in sub) / len(sub), 3),
            "top1_similarity_avg": round(sum(sims[group]) / len(sims[group]), 4),
        }
    scored = [c for c in cases if c["group"] != "boundary"]
    matched = sum(c["matched"] for c in scored)
    sec_scored = [c for c in cases if c["section_ok"] is not None]
    sec_ok = sum(bool(c["section_ok"]) for c in sec_scored)
    messy = [c["id"] for c in cases if c["top1_section_count"] >= 3]
    notitle = [c["id"] for c in cases if c["hits"] and not c["top1_has_title"]]
    ok_sims = [c["top1_similarity"] for c in sec_scored if c["section_ok"]]
    bad_sims = [c["top1_similarity"] for c in sec_scored if not c["section_ok"]]

    if ok_sims and bad_sims:
        sim_limit = (
            f"**相似度无法区分「内容对不对」**：section_ok=true 的 {len(ok_sims)} 条相似度 "
            f"{min(ok_sims):.4f}~{max(ok_sims):.4f}，false 的 {len(bad_sims)} 条 "
            f"{min(bad_sims):.4f}~{max(bad_sims):.4f} —— 两段区间重叠（本次 "
            f"{max(bad_sims):.4f} 判错、{min(ok_sims):.4f} 判对）→ "
            "单靠调阈值解决不了，必须改善切块 / 上 rerank。"
        )
    else:
        sim_limit = ("**相似度无法区分「内容对不对」**：本次无误命中样本，"
                     "该结论待 W6 30 条用例验证。")

    print("=" * 78)
    for g, s in by_group.items():
        print(f"  {g:<12s} 判定 {s['matched']}/{s['n']}  "
              f"top1 相似度均值 {s['top1_similarity_avg']}")
    print(f"  判定维度（不含 boundary）：{matched}/{len(scored)}")
    print(f"  内容维度（section_ok）：  {sec_ok}/{len(sec_scored)}"
          f"   ← 这才是「检索真的答对了吗」")
    print(f"  ⚠️ Top-1 混杂块（≥3 小节）：{len(messy)}/{len(cases)}  {messy}")
    print(f"  ⚠️ Top-1 无小节标题（续块）：{len(notitle)}/{len(cases)}  {notitle}")
    print("=" * 78)

    doc = {
        "schema_version": 2,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generator": "export_samples.py",
        "purpose": (
            "W7 并入主线「备忘录检索」的跨实现对照基准：Python 版检索结果，"
            "Java 版（Spring AI VectorStore）应能复现同一批 Top-3。"
            "同时是 W6「拼上下文」的输入样例（hits[].text = 可直接拼进 prompt 的原文块）。"
        ),
        "index": {
            "collection": ra.COLLECTION,
            "count": col.count(),
            "hnsw_space": report.get("hnsw_space", "cosine"),
            "docs": int(report.get("docs", 0)) or None,
            "chunk_size": int(report.get("chunk_size", 0)) or None,
            "chunk_overlap": int(report.get("chunk_overlap", 0)) or None,
            "embedding_model": report.get("embedding_model", ra.EMBEDDING_MODEL),
            "embedding_dim": int(report.get("embedding_dim", 0)) or None,
            "built_at": report.get("built_at"),
        },
        "retrieval": {
            "top_k": TOP_K,
            "similarity_floor": round(ra.SIM_FLOOR, 4),
            "reject_distance": ra.REJECT_DISTANCE,
            "verdict_rule": ("hits 为空 → 无匹配；"
                             "hits[0].similarity < similarity_floor → 拒答；否则命中"),
            "distance_note": (
                "Chroma 的 distances 是**距离**（cosine space 下 = 1 - similarity，越小越像）。"
                "本文件只暴露 similarity（已由 retrieval_app.retrieve() 统一换算）；"
                "Java 版若直接读 distances，拒答判据的方向会正好相反。"
            ),
            "threshold_status": "经验起点，**未标定**；W6 用 30 条用例的误拒/漏放分布标定",
        },
        "group_legend": GROUP_LEGEND,
        "summary": {
            "total": len(cases),
            "judge_dimension": {
                "scored": len(scored),
                "matched": matched,
                "pass_rate": round(matched / len(scored), 3),
            },
            "content_dimension": {
                "scored": len(sec_scored),
                "section_ok": sec_ok,
                "section_pass_rate": round(sec_ok / len(sec_scored), 3),
                "note": ("section_ok = Top-1 块命中了期望小节；false 即「判定对但内容跑偏」，"
                         "逐条见 cases[].section_ok / cases[].top1_sections"),
            },
            "by_group": by_group,
        },
        "known_limits": [
            "**判定 ≠ 内容**：similarity ≥ floor 即判「命中」，但块内容可能与问题无关。"
            f"本次 {sec_ok}/{len(sec_scored)} 条命中在小节层面也对得上，其余为误命中样本。",
            f"**块边界不对齐语义**：Top-1 块混 ≥3 个小节的有 {len(messy)}/{len(cases)} 条"
            "（固定长度 500/50 切块的固有形状），这是 W7「按标题/语义切块」的靶子。",
            f"**续块无标题**：{len(notitle)}/{len(cases)} 条的 Top-1 没有 markdown 标题"
            "（块开头是上一块尾部），此时 section_ok=false 不代表内容跑题，需人眼复核。",
            sim_limit,
            "**阈值未标定**：boundary 用例相似度距阈值仅 0.01 量级，灰区贴着阈值 → W6 必须"
            "用 30 条用例的误拒/漏放分布重标，不能沿用 0.45。",
            "**本机网络**：生成时若接口超时会中断，重跑即可（确定性语料 + 固定 seed，"
            "结果可复现）。",
        ],
        "cases": cases,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"已落盘：{os.path.relpath(OUT_PATH, BASE_DIR)}  （{size_kb:.1f} KB）")


if __name__ == "__main__":
    main()
