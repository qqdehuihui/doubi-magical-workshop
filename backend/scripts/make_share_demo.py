# -*- coding: utf-8 -*-
"""生成单文件静态演示页（share/AI学习助手-演示.html）。

数据来源：正在运行的后端 + 样例课程「端到端验证课」的 Mock Provider 真实输出快照。
页面为只读演示：无后端、不能上传，交互仅限页签切换与查看答案解析。
用法：backend/.venv/Scripts/python.exe scripts/make_share_demo.py
"""
import html
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000"
DOC = "2cf57a135a67428fbf62ebc18789153a"
COURSE = "端到端验证课"
TYPE_ZH = {"single": "单选", "multi": "多选", "judge": "判断", "fill": "填空",
           "short": "简答", "comprehensive": "综合", "unknown": "未标注"}
DIFF_ZH = {"basic": "基础", "medium": "中等", "hard": "较难", "challenge": "挑战"}
COG_ZH = {"remember": "记忆", "understand": "理解", "apply": "应用",
          "analyze": "分析", "evaluate": "评价", "create": "创造"}


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def main() -> None:
    cl = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
    meta = cl.get(f"/api/documents/{DOC}").json()
    kp = cl.post(f"/api/documents/{DOC}/key-points").json()
    quiz = cl.post(f"/api/documents/{DOC}/questions", json={
        "count": 6,
        "types": ["single", "multi", "judge", "fill", "short", "comprehensive"],
    }).json()
    chat_q = "机械能守恒的条件是什么？"
    chat = cl.post(f"/api/documents/{DOC}/chat", json={"question": chat_q}).json()
    css = (ROOT / "frontend" / "src" / "index.css").read_text(encoding="utf-8")

    fw = kp["course_framework"]
    hist = kp["historical_frequent"]
    legend = kp["metrics_legend"]

    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 学习助手 · 静态演示</title>
<style>{css}
.demo-banner{{background:#fff7ed;border:1px solid #fdba74;color:#9a3412;border-radius:10px;
padding:12px 16px;font-size:13px;line-height:1.7;margin-bottom:16px}}
.tab-panel{{display:none}}.tab-panel.on{{display:block}}
.snapshot-note{{font-size:12px;color:#7b8794;margin-top:24px}}
</style>
</head>
<body><div class="app">
<header class="header"><h1>AI 学习助手</h1>
<p class="subtitle">上传 PDF / PPTX / Word 课件：五层重难点分析、六题型模拟考试、基于原文来源的问答，并可导入历年试卷统计真实考频</p></header>
<div class="demo-banner"><b>这是静态演示页</b>：由本地部署版在 <b>Mock Provider</b> 下生成的真实输出快照
（示例课程《力学与能量》，{esc(meta['filename'])}，{meta['unit_count']} 个{esc(meta['unit_label'])}）。
页面不连后端：不能上传、不能提问；「模拟考试」可作答并本地对照答案，其余结果均为固定快照。
<b>标注 [MOCK 测试数据] 的内容是测试数据，不代表真实 AI 推理。</b>想在自己电脑跑完整功能，见项目 README。</div>
<div class="card">
<div class="upload-row"><button disabled>选择文件</button><input class="course-input" value="{esc(COURSE)}" disabled>
<button class="primary" disabled>上传并解析</button></div>
<div class="progress"><div class="progress-bar" style="width:100%"></div><span class="progress-text">100%</span></div>
<p class="doc-info">✅ {esc(meta['filename'])}（{esc(meta['file_type'])}）· {meta['unit_count']} 个{esc(meta['unit_label'])} ·
{meta['total_chars']} 字符 · {len(meta.get('sections') or [])} 个章节 —— 快照时刻的解析结果</p>
<p class="hint">静态演示：上传按钮不可用；真实部署支持 PDF/PPTX/DOCX 上传、旧 .ppt/.doc 会提示另存为新格式。</p>
</div>
<nav class="tabs">
<button class="tab active" data-p="p1">重难点分析</button>
<button class="tab" data-p="p2">模拟考试</button>
<button class="tab" data-p="p3">课件问答</button>
<button class="tab" data-p="p4">历年资料库</button>
</nav>""")

    # ---- ① 重难点 ----
    legend_lis = "".join(f"<li>{esc(v)}</li>" for k, v in legend.items() if k != "warning")
    parts.append(f"""<section class="tab-panel on" id="p1">
<details class="legend"><summary>四个指标的含义（不可混同）</summary><ul>{legend_lis}</ul>
<p class="legend-warning">{esc(legend.get('warning'))}</p></details>
<div class="layers">
<section class="layer"><h3>① 课程核心框架</h3><p class="stem">{esc(fw['topic'])}</p><ol class="chapters">""")
    for c in fw["chapters"]:
        parts.append(f"<li><b>{esc(c['title'])}</b><p>{esc(c['summary'])}</p>"
                     f"<span class='chip'>{esc(c['location'])}</span></li>")
    parts.append("</ol>")
    if fw["relations"]:
        parts.append('<ul class="why">' + "".join(
            f"<li>{esc(r['from'])} → {esc(r['to'])}：{esc(r['relation'])}</li>" for r in fw["relations"]) + "</ul>")
    parts.append("</section><section class=" + '"layer"><h3>② 核心知识点</h3>')
    for k in kp["core_knowledge"]:
        parts.append(
            f'<div class="item"><p class="stem">{esc(k["item"])}'
            f'<span class="badge badge-{("hi" if k["importance"]=="高" else "mid" if k["importance"]=="中" else "low")}">重要性{esc(k["importance"])}</span>'
            f'<span class="badge badge-{("hi" if k["emphasis"]=="高" else "mid" if k["emphasis"]=="中" else "low")}">课件强调{esc(k["emphasis"])}</span>'
            f'<span class="kind">{esc(k["kind"])}</span></p><p>{esc(k["content"])}</p>'
            f'<span class="chips"><span class="chip">{esc(k["location"])}</span></span></div>')
    parts.append('</section><section class="layer"><h3>③ 重难点解析</h3>')
    for d in kp["difficult_points"]:
        why = "".join(f"<li>{esc(w)}</li>" for w in d["why"])
        conf = (f'<p class="confusion">易混对比 · {esc(d["confusion"]["with"])}：{esc(d["confusion"]["difference"])}</p>'
                if d.get("confusion") else "")
        parts.append(f'<div class="item"><p class="stem">{esc(d["item"])}</p><p>{esc(d["content"])}</p>'
                     f'<ul class="why">{why}</ul>{conf}'
                     f'<span class="chips"><span class="chip">{esc(d["location"])}</span></span></div>')
    parts.append('</section><section class="layer"><h3>④ 可能考查内容（基于课件强调度的推测，非统计结论）</h3>')
    for p in kp["exam_predictions"]:
        parts.append(
            f'<div class="item"><p class="stem">{esc(p["item"])}'
            f'<span class="badge badge-{("hi" if p["priority"]=="高" else "mid" if p["priority"]=="中" else "low")}">推测考查价值{esc(p["priority"])}</span></p>'
            f'<p class="basis">依据：{esc("；".join(p["basis"]))}</p><p class="hint">{esc(p["note"])}</p>'
            f'<span class="chips"><span class="chip">{esc(p["location"])}</span></span></div>')
    parts.append('</section><section class="layer"><h3>⑤ 历年高频考点（真实统计）</h3>')
    if hist["available"]:
        parts.append(f'<p class="hint">基于已导入的 {hist["paper_count"]} 份历年资料、{hist["question_total"]} 道题统计'
                     f'（来源：{esc(hist["source"])}）</p><table class="stats-table"><tr><th>考点</th><th>出现次数</th>'
                     f'<th>年份跨度</th><th>题型分布</th><th>合计分值</th></tr>')
        for it in hist["items"]:
            types = " ".join(f'{TYPE_ZH.get(t, t)}×{n}' for t, n in it["types"].items())
            parts.append(f'<tr><td>{esc(it["point"])}</td><td>{it["count"]}</td><td>{esc(it["span"])}</td>'
                         f'<td>{esc(types)}</td><td>{esc(it["score_total"])}</td></tr>')
        parts.append("</table>")
        cov = hist.get("section_coverage") or []
        if cov:
            parts.append('<p class="hint">章节覆盖：' + " · ".join(
                f'{esc(c["section"])}（{c["matched_count"]}）' for c in cov) + "</p>")
    else:
        parts.append(f'<p class="notice-box">{esc(hist["notice"])}</p>')
    parts.append("</section></div></section>")

    # ---- ② 模拟考试（可交互）----
    parts.append(f"""<section class="tab-panel" id="p2">
<div class="quiz-controls"><label>题数 <input type="number" value="{quiz['params']['count']}" disabled></label>
<label>难度 <select disabled><option>不限</option></select></label>
<label>认知层次 <select disabled><option>不限</option></select></label>
<button class="primary" disabled>题目为快照，不可重新生成</button></div>
<p class="review-note">质量审核：检查 {quiz['review']['checked']} 题 · 通过 {quiz['review']['passed']} ·
排除 {quiz['review']['excluded']} · 重生成 {quiz['review']['regenerated']} 题（静态快照）</p>
<ol class="quiz-list">""")
    for i, q in enumerate(quiz["questions"]):
        badges = (f'<span class="badge badge-diff">{DIFF_ZH.get(q["difficulty"], esc(q["difficulty"]))}</span>'
                  f'<span class="badge badge-cog">{COG_ZH.get(q["cognitive"], esc(q["cognitive"]))}层</span>')
        block = [f'<li class="item" data-i="{i}"><p class="stem">{i + 1}. [{TYPE_ZH[q["type"]]}] '
                 f'{esc(q["stem"])}{badges}</p><p class="hint">知识点：{esc(q["knowledge_point"])}</p>']
        if q["options"]:
            for o in q["options"]:
                note = next((n["why_wrong"] for n in q["wrong_option_notes"] if n["label"] == o["label"]), "")
                mark = ("<span class='opt-note reveal' hidden>✔ 正确项</span>"
                        if o["label"] in q["answer"] else
                        f"<span class='opt-note reveal' hidden>✘ {esc(note or '干扰项')}</span>")
                input_type = "checkbox" if q["type"] == "multi" else "radio"
                block.append(f'<label class="option"><input type="{input_type}" name="q{i}" value="{esc(o["label"])}">'
                             f'{esc(o["label"])}. {esc(o["text"])}{mark}</label>')
        if q["type"] == "fill":
            block.append(f'<p class="answer-block reveal" hidden><span class="result">可接受答案：'
                         f'{esc(" / ".join(q.get("answers") or []))}</span></p>')
        if q.get("reference_answer"):
            block.append(f'<p class="answer-block reveal" hidden><span class="explain">参考答案：{esc(q["reference_answer"])}</span></p>')
        if q.get("scoring_points"):
            block.append('<ul class="why reveal">' + "".join(f"<li>{esc(s)}</li>" for s in q["scoring_points"]) + "</ul>")
        if q.get("explanation"):
            block.append(f'<p class="answer-block reveal" hidden><span class="explain">解析：{esc(q["explanation"])}</span></p>')
        block.append(f'<span class="chips"><span class="chip">{esc(q["location"])}</span></span></li>')
        parts.append("".join(block))
    parts.append(f'</ol><div class="quiz-footer"><button id="reveal">提交并显示答案解析</button></div>'
                 f'<p class="snapshot-note">provider: {esc(quiz["provider"]["name"])}/{esc(quiz["provider"]["model"])}'
                 f'（mock={quiz["provider"]["mock"]}），{esc(quiz["provider"].get("disclaimer", ""))}</p></section>')

    # ---- ③ 问答 ----
    chips = "".join(f'<span class="chip">{esc(x)}</span>' for x in chat["locations"])
    parts.append(f"""<section class="tab-panel" id="p3">
<div class="chat-log">
<div class="msg user"><span class="msg-role">我</span><div>{esc(chat_q)}</div></div>
<div class="msg assistant"><span class="msg-role">助手</span><div>{esc(chat['answer'])}</div>
<span class="chips">{chips}</span></div>
<p class="hint">检索证据 {chat['evidence_chunks']} 段；回答附原文定位标签（第N页 / 第N张幻灯片 / 章节路径 / 表格N），不同格式不混用编号。</p>
</div>
<div class="chat-input"><input placeholder="静态演示不能提问——真实部署中这里走关键词检索 + 证据不足短路（不会编造答案）" disabled>
<button class="primary" disabled>发送</button></div></section>""")

    # ---- ④ 资料库 ----
    parts.append(f"""<section class="tab-panel" id="p4">
<p class="hint">课程「{esc(COURSE)}」：已导入 {hist["paper_count"]} 份历年资料，统计完全来自真实导入数据；
年份/题型/分值无法识别时记为「未知」，不做猜测。</p>
<table class="stats-table"><tr><th>资料文件</th><th>类型</th><th>年份</th><th>题数</th></tr>""")
    for p in kp_x_papers(hist, cl):
        parts.append(f'<tr><td>{esc(p["filename"])}</td><td>{esc(p["material_type"])}</td>'
                     f'<td>{esc(p["year"])}</td><td>{p["question_count"]}</td></tr>')
    parts.append("</table>")
    by_year = "、".join(f"{esc(y)} 年 {n} 题" for y, n in (hist.get("by_year") or {}).items())
    by_type = "，".join(f"{TYPE_ZH.get(t, t)}×{n}" for t, n in (hist.get("by_type") or {}).get("types", {}).items())
    parts.append(f'<p class="hint">按年份：{by_year}；按题型：{by_type}</p></section>')

    parts.append(f"""<p class="snapshot-note">快照生成于 {time.strftime('%Y-%m-%d %H:%M')}，
课程「{esc(COURSE)}」，Provider：mock/mock-v2（测试数据）。本页由 backend/scripts/make_share_demo.py 生成，可重复运行更新。</p>
</div>
<script>
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {{
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('on'));
  t.classList.add('active');
  document.getElementById(t.dataset.p).classList.add('on');
}}));
const rv = document.getElementById('reveal');
if (rv) rv.addEventListener('click', () => {{
  const on = rv.textContent.startsWith('收起');
  document.querySelectorAll('.reveal').forEach(e => e.hidden = on);
  rv.textContent = on ? '提交并显示答案解析' : '收起答案';
}});
</script>
</body></html>""")

    out_dir = ROOT / "share"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "AI学习助手-演示.html"
    out_file.write_text("".join(parts), encoding="utf-8")
    print("written:", out_file, out_file.stat().st_size, "bytes")


def kp_x_papers(hist, cl):
    r = cl.get("/api/exams", params={"course_id": "端到端验证课"})
    return r.json().get("exams", []) if r.status_code == 200 else []


if __name__ == "__main__":
    main()
