# -*- coding: utf-8 -*-
"""
Free News Club 生成器（GitHub Actions 每小时运行）
- 每源抓最新 30 条作候选 → 关键词重要性打分 → 每源配额精选 → 跨源同事件去重
- 产出：index.html（最新一期）、archive/<日期>.html（当日快照）、archive.html（存档索引）
        data/<日期>.json（当日存档）、data/latest.json
- 若本期链接集合与上一期完全相同，则不改动任何文件（避免无意义提交）
离线测试：FNC_OFFLINE_ITEMS=<items.json 路径> FNC_RAW_TOTAL=<n> python3 scripts/fetch.py
"""
import html as h
import json
import os
import re
import socket
import sys
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = ZoneInfo("Asia/Shanghai")

FEEDS = [
    ("快讯", "华尔街见闻", "https://dedicated.wallstreetcn.com/rss.xml"),
    ("财经深度", "Stratechery", "https://stratechery.com/feed/"),
    ("财经深度", "Not Boring", "https://www.notboring.co/feed"),
    ("财经深度", "A Wealth of Common Sense", "https://awealthofcommonsense.com/feed/"),
    ("AI与数据", "Lil'Log", "https://lilianweng.github.io/index.xml"),
    ("AI与数据", "Import AI", "https://importai.substack.com/feed"),
    ("AI与数据", "Latent Space", "https://www.latent.space/feed"),
    ("AI与数据", "Data Engineering Weekly", "https://www.dataengineeringweekly.com/feed"),
    ("学术", "arXiv cs.LG", "https://rss.arxiv.org/rss/cs.LG"),
    ("学术", "arXiv cs.DB", "https://rss.arxiv.org/rss/cs.DB"),
]
QUOTA = {"华尔街见闻": 6, "Stratechery": 3, "Not Boring": 3, "A Wealth of Common Sense": 3,
         "Lil'Log": 2, "Import AI": 3, "Latent Space": 3, "Data Engineering Weekly": 3,
         "arXiv cs.LG": 5, "arXiv cs.DB": 5}
THEMES = {
    "快讯":    dict(icon="⚡", c1="#d32f2f", c2="#f4511e", tag="7×24 全球市场与政策动态", anchor="news", img="sec-news.jpg", no="01"),
    "财经深度": dict(icon="📈", c1="#16324f", c2="#b8860b", tag="长文 · Newsletter · 深度分析", anchor="finance", img="sec-finance.jpg", no="02"),
    "AI与数据": dict(icon="🤖", c1="#4527a0", c2="#00838f", tag="AI 研究 · 数据工程 · 工程实践", anchor="ai", img="sec-ai.jpg", no="03"),
    "学术":    dict(icon="🎓", c1="#004d40", c2="#689f38", tag="论文 · 预印本 · 期刊", anchor="academic", img="sec-academic.jpg", no="04"),
}
SOURCE_DESC = {
    "华尔街见闻": "全球财经快讯 · 市场与政策动态",
    "Stratechery": "Ben Thompson · 科技商业战略分析",
    "Not Boring": "Packy McCormick · 科技公司与趋势长文",
    "A Wealth of Common Sense": "Ben Carlson · 个人理财与市场常识",
    "Lil'Log": "Lilian Weng · AI 研究学习笔记",
    "Import AI": "Jack Clark · AI 进展与政策周报",
    "Latent Space": "AI 工程师社区 · 产品动态与访谈",
    "Data Engineering Weekly": "数据工程周刊 · 工具、架构与实践",
    "arXiv cs.LG": "机器学习论文预印本",
    "arXiv cs.DB": "数据库方向论文预印本",
}
GROUP_ORDER = ["快讯", "财经深度", "AI与数据", "学术"]
GROUP_PRIOR = {"快讯": 8, "财经深度": 6, "AI与数据": 4, "学术": 0}
KW_FIN = ["央行", "美联储", "鲍威尔", "非农", "CPI", "PPI", "GDP", "降息", "加息", "通胀", "利率",
          "关税", "制裁", "出口管制", "财报", "营收", "利润", "暴涨", "暴跌", "大涨", "大跌",
          "IPO", "并购", "收购", "破产", "违约", "国债", "油价", "金价", "汇率", "Fed", "tariff",
          "earnings", "inflation", "rate cut", "rate hike", "merger", "acquisition", "antitrust", "垄断"]
KW_AI = ["LLM", "GPT", "agent", "reasoning", "benchmark", "transformer", "diffusion", "robot",
         "chip", "GPU", "neural", "inference", "multimodal", "open source", "open-source",
         "大模型", "智能体", "开源", "芯片", "机器人", "推理", "AI", "model", "learning"]
KW_PAPER = ["large language", "llm", "agent", "reasoning", "benchmark", "foundation", "multimodal",
            "diffusion", "transformer", "retrieval", "alignment", "robot", "database", "query",
            "index", "vector", "graph", "storage", "transaction", "efficient", "scaling"]

CSS = """
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;margin:0;color:#1c2430;background:#f4f1ea;line-height:1.65}
.masthead{background:#0d1b2e;color:#fff;padding:26px 16px 22px;text-align:center}
.masthead .hero-img{width:min(1060px,100%);border-radius:12px;display:block;margin:0 auto 18px;box-shadow:0 8px 28px rgba(0,0,0,.35)}
.masthead h1{font-family:Georgia,'Times New Roman','Songti SC',serif;font-size:42px;letter-spacing:3px;margin:0}
.masthead h1 .accent{color:#e8b64c}
.masthead .rule{width:120px;height:3px;background:#c0392b;margin:12px auto 10px}
.masthead .sub{color:#aebfd6;font-size:13px;margin:0 0 14px}
.chips{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
.chip{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.25);color:#dbe7f5;border-radius:999px;padding:3px 12px;font-size:12px}
.chip.update{background:#c62828;border-color:#ef5350;color:#fff;font-weight:700;font-size:13px;padding:4px 16px}
.chip a{color:#dbe7f5;text-decoration:none}
.nav{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);border-bottom:2px solid #0d1b2e;padding:10px 12px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
.nav button{font-family:inherit;font-size:13px;font-weight:700;border:none;cursor:pointer;border-radius:999px;padding:7px 16px;color:#fff;box-shadow:0 2px 6px rgba(20,30,50,.15)}
.nav button:hover{filter:brightness(1.13)}
.nav button:active{transform:scale(.97)}
.wrap{max-width:1060px;margin:0 auto;padding:6px 16px 40px}
section{margin-top:32px;scroll-margin-top:76px}
.hl{background:#0d1b2e;border-radius:14px;padding:18px 20px 8px;box-shadow:0 6px 18px rgba(13,27,46,.25)}
.hl h2{color:#fff;font-family:Georgia,'Songti SC',serif;margin:0 0 4px;font-size:20px;letter-spacing:1px}
.hl .hsub{color:#9db4d0;font-size:12px;margin-bottom:10px}
.hl .hitem{display:block;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-left:4px solid #e8b64c;border-radius:8px;padding:10px 14px;margin:0 0 10px;text-decoration:none}
.hl .hitem:hover{background:rgba(255,255,255,.12)}
.hl .hitem .ht{color:#fff;font-size:15px;font-weight:700}
.hl .hsum{color:#c3d3e8;font-size:13px;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.hl .hmeta{margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.hl .gtag{font-size:11px;color:#0d1b2e;background:#e8b64c;border-radius:6px;padding:1px 8px;font-weight:700}
.hl .stag{font-size:11px;color:#dbe7f5;border:1px solid rgba(255,255,255,.35);border-radius:6px;padding:1px 8px}
.hl .time{color:#8fa5c0;font-size:12px}
.shead{border-radius:14px;color:#fff;padding:14px 18px;display:flex;align-items:center;gap:14px;box-shadow:0 4px 14px rgba(20,30,50,.14)}
.shead .no{font-family:Georgia,serif;font-size:30px;font-weight:700;opacity:.55;line-height:1}
.shead img.thumb{width:62px;height:62px;object-fit:cover;border-radius:10px;border:2px solid rgba(255,255,255,.55);flex:none}
.shead h2{margin:0;font-size:21px;letter-spacing:1px}
.shead .tag{font-size:12px;opacity:.88;margin-top:2px}
.shead .cnt{margin-left:auto;font-size:12px;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);padding:3px 10px;border-radius:999px;white-space:nowrap}
.submod{margin-top:20px}
.subhead{display:flex;align-items:baseline;gap:10px;border-bottom:2px solid var(--ac);padding:0 2px 6px;flex-wrap:wrap}
.subhead .sname{font-size:17px;font-weight:800;color:#17263a;font-family:Georgia,'Songti SC',serif}
.subhead .sdesc{font-size:12px;color:#7c8798}
.subhead .scnt{margin-left:auto;font-size:12px;color:#fff;background:var(--ac);border-radius:999px;padding:1px 10px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;margin-top:12px}
.card{background:#fff;border-radius:10px;padding:13px 15px 11px;border-left:5px solid var(--ac);box-shadow:0 1px 4px rgba(20,30,50,.07);transition:transform .12s,box-shadow .12s}
.card:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(20,30,50,.13)}
.card a{color:#17263a;text-decoration:none;font-size:15px;font-weight:600;display:block}
.card a:hover{color:var(--ac)}
.sum{color:#5b6675;font-size:13px;margin:7px 0 0;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
details.abs{margin-top:7px}
details.abs summary{cursor:pointer;color:var(--ac);font-size:12px;font-weight:700}
details.abs p{color:#5b6675;font-size:13px;margin:6px 0 0}
.meta{margin-top:8px}
.time{font-size:12px;color:#8a94a3}
footer{color:#8a94a3;font-size:12px;text-align:center;padding:26px 16px 34px}
@media (max-width:560px){.masthead h1{font-size:30px}.grid{grid-template-columns:1fr}.shead img.thumb{width:48px;height:48px}}
"""
JS = "function goNav(id){var e=document.getElementById(id);if(e){e.scrollIntoView({behavior:'smooth',block:'start'});}}"


def clean_text(raw, limit=None):
    t = re.sub(r"<[^>]+>", " ", raw or "")
    t = h.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit] if limit else t


def kw_for(group, source):
    if source.startswith("arXiv"):
        return KW_PAPER
    if group == "AI与数据":
        return KW_AI
    return KW_FIN + KW_AI


def score(item, group, source, idx):
    text = (item["title"] + " " + (item.get("summary") or "")).lower()
    hits = sum(1 for kw in kw_for(group, source) if kw.lower() in text)
    s = hits * 10 + max(0, 10 - idx)
    if source.startswith("arXiv"):
        c = (item.get("comment") or "").lower()
        if any(v in c for v in ("accepted", "neurips", "icml", "iclr", "acl", "emnlp", "cvpr")):
            s += 15
    return s


def tokens(title):
    t = title.lower()
    words = set(re.findall(r"[a-z0-9]{3,}", t))
    zh = re.findall(r"[一-鿿]", t)
    grams = {"".join(zh[i:i + 2]) for i in range(len(zh) - 1)}
    return words | grams


def fetch_candidates():
    import feedparser
    socket.setdefaulttimeout(25)
    cand = {}
    raw_total = 0
    for group, source, url in FEEDS:
        items = []
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
                summ = clean_text(e.get("summary", ""))
                items.append({
                    "group": group, "source": source,
                    "title": clean_text(e.get("title", "")),
                    "link": e.get("link", ""),
                    "time": fmt_time(e),
                    "summary": summ if source.startswith("arXiv") else summ[:200],
                    "comment": e.get("arxiv_comment", "") or "",
                })
        except Exception as ex:  # 单个源失败不拖垮整站
            print(f"[warn] {source} fetch failed: {ex}", file=sys.stderr)
        cand[source] = (group, items)
        raw_total += len(items)
        print(f"{source}: {len(items)} candidates")
    return cand, raw_total


def fmt_time(e):
    tp = e.get("published_parsed") or e.get("updated_parsed")
    if tp:
        return f"{tp.tm_mon:02d}-{tp.tm_mday:02d} {tp.tm_hour:02d}:{tp.tm_min:02d}"
    return clean_text(e.get("published", ""))[:16]


def select(cand):
    picked = []
    for source, (group, items) in cand.items():
        scored = [(score(it, group, source, i), i, it) for i, it in enumerate(items)]
        scored.sort(key=lambda x: (-x[0], x[1]))
        keep = sorted(scored[:QUOTA.get(source, 3)], key=lambda x: x[1])
        for s, _, it in keep:
            it = dict(it)
            it["score"] = s
            picked.append(it)
    kept, seen = [], []
    for it in sorted(picked, key=lambda x: -x["score"]):
        tk = tokens(it["title"])
        if any(len(tk & p) / (len(tk | p) or 1) >= 0.45 for p in seen):
            continue
        seen.append(tk)
        kept.append(it)
    return kept


def highlights_of(items):
    ranked = sorted(items, key=lambda x: -(x.get("score", 0) + GROUP_PRIOR.get(x["group"], 0)))
    hl, per = [], {}
    nb = next((it for it in ranked if it["group"] == "快讯"), None)
    if nb is not None:
        hl.append(nb)
        per["快讯"] = 1
    for it in ranked:
        if len(hl) >= 5:
            break
        if it in hl or per.get(it["group"], 0) >= 2:
            continue
        hl.append(it)
        per[it["group"]] = per.get(it["group"], 0) + 1
    return hl


def card(it):
    s = f'<div class="card"><a href="{h.escape(it["link"])}" target="_blank" rel="noopener">{h.escape(it["title"])}</a>'
    summ = (it.get("summary") or "").strip()
    if summ:
        if it["source"].startswith("arXiv"):
            s += f'<details class="abs"><summary>展开摘要</summary><p>{h.escape(summ)}</p></details>'
        else:
            s += f'<p class="sum">{h.escape(summ)}</p>'
    return s + f'<div class="meta"><span class="time">{h.escape(it["time"])}</span></div></div>'


def build_html(items, raw_total, gen_time, asset_prefix="assets/"):
    groups = OrderedDict()
    for g in GROUP_ORDER:
        bs = OrderedDict()
        for it in items:
            if it["group"] == g:
                bs.setdefault(it["source"], []).append(it)
        if bs:
            groups[g] = bs
    total = len(items)
    o = ["<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">",
         "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
         f"<title>Free News Club · {gen_time}</title><style>{CSS}</style><script>{JS}</script></head><body>",
         '<div class="masthead">',
         f'<img class="hero-img" src="{asset_prefix}hero.jpg" alt="Free News Club">',
         '<h1>Free News <span class="accent">Club</span></h1><div class="rule"></div>',
         '<p class="sub">独立静态页，离线可打开</p>',
         '<div class="chips">'
         f'<span class="chip update">● 已更新 {total} 条</span>'
         f'<span class="chip">从 {raw_total} 条候选中精选</span>'
         f'<span class="chip">更新时间（北京时间）：{gen_time}</span>'
         '<span class="chip"><a href="archive.html">📚 历史存档</a></span></div></div>']
    btns = '<button onclick="goNav(\'top\')" style="background:#0d1b2e;border:1px solid #e8b64c;color:#e8b64c">⭐ 本期重点</button>'
    btns += "".join(
        f'<button onclick="goNav(\'{THEMES[n]["anchor"]}\')" style="background:linear-gradient(120deg,{THEMES[n]["c1"]},{THEMES[n]["c2"]})">{THEMES[n]["icon"]} {n}</button>'
        for n in groups)
    o.append(f'<div class="nav">{btns}</div><div class="wrap">')
    o.append('<section id="top" style="margin-top:22px"><div class="hl"><h2>⭐ 本期重点</h2>'
             '<div class="hsub">按重要性打分从全部条目中挑出的 5 条，先看这里，再决定要不要往下翻</div>')
    for it in highlights_of(items):
        summ = (it.get("summary") or "").strip()
        sh = f'<span class="hsum">{h.escape(summ)}</span>' if summ else ""
        o.append(f'<a class="hitem" href="{h.escape(it["link"])}" target="_blank" rel="noopener">'
                 f'<span class="ht">{h.escape(it["title"])}</span>{sh}'
                 f'<span class="hmeta"><span class="gtag">{it["group"]}</span>'
                 f'<span class="stag">{h.escape(it["source"])}</span>'
                 f'<span class="time">{h.escape(it["time"])}</span></span></a>')
    o.append("</div></section>")
    for name, by_source in groups.items():
        t = THEMES[name]
        gcount = sum(len(v) for v in by_source.values())
        o.append(f'<section id="{t["anchor"]}" style="--ac:{t["c1"]}">')
        o.append(f'<div class="shead" style="background:linear-gradient(120deg,{t["c1"]},{t["c2"]})">'
                 f'<div class="no">{t["no"]}</div><img class="thumb" src="{asset_prefix}{t["img"]}" alt="">'
                 f'<div><h2>{t["icon"]} {name}</h2><div class="tag">{t["tag"]}</div></div>'
                 f'<div class="cnt">精选 {gcount} 条 · {len(by_source)} 个子模块</div></div>')
        for source, its in by_source.items():
            o.append('<div class="submod"><div class="subhead">'
                     f'<span class="sname">{h.escape(source)}</span>'
                     f'<span class="sdesc">{h.escape(SOURCE_DESC.get(source, ""))}</span>'
                     f'<span class="scnt">精选 {len(its)} 条</span></div>')
            o.append('<div class="grid">' + "".join(card(it) for it in its) + "</div></div>")
        o.append("</section>")
    o.append("</div><footer>Free News Club · 每期按关键词重要性精选并跨源去重，摘要来自各源 RSS，标题链接指向原文，内容以原文为准 · <a href=\"archive.html\">历史存档</a></footer>")
    o.append("</body></html>")
    return "".join(o)


def build_archive_index(dates):
    rows = "".join(
        f'<li><a href="archive/{d}.html">{d}</a> · <a href="data/{d}.json">数据 JSON</a></li>'
        for d in sorted(dates, reverse=True))
    return ("<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Free News Club · 历史存档</title>"
            "<style>body{font-family:-apple-system,'PingFang SC',sans-serif;max-width:760px;margin:40px auto;padding:0 16px;line-height:1.9;color:#1c2430;background:#f4f1ea}"
            "h1{font-family:Georgia,serif}li{margin:6px 0}a{color:#1565c0}</style></head><body>"
            "<h1>Free News Club · 历史存档</h1><p>每天抓取到的资讯按日期存档，最新一期在<a href=\"index.html\">首页</a>。</p>"
            f"<ul>{rows}</ul></body></html>")


def main():
    now = datetime.now(TZ)
    gen_time = now.strftime("%Y-%m-%d %H:%M")
    day = now.strftime("%Y-%m-%d")
    offline = os.environ.get("FNC_OFFLINE_ITEMS")
    if offline:
        items = json.load(open(offline, encoding="utf-8"))
        raw_total = int(os.environ.get("FNC_RAW_TOTAL", len(items)))
        for it in items:
            it.setdefault("comment", "")
    else:
        cand, raw_total = fetch_candidates()
        items = select(cand)
    if not items:
        print("no items selected; abort without changes", file=sys.stderr)
        return 1
    latest_path = os.path.join(ROOT, "data", "latest.json")
    new_links = sorted(it["link"] for it in items)
    if os.path.exists(latest_path) and not offline:
        try:
            prev = json.load(open(latest_path, encoding="utf-8"))
            if sorted(it["link"] for it in prev.get("items", [])) == new_links:
                print("no change in selected links; skip write")
                return 0
        except Exception:
            pass
    payload = {"generated_at": gen_time, "raw_total": raw_total, "items": items}
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "archive"), exist_ok=True)
    with open(os.path.join(ROOT, "data", f"{day}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    page = build_html(items, raw_total, gen_time)
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(ROOT, "archive", f"{day}.html"), "w", encoding="utf-8") as f:
        f.write(build_html(items, raw_total, gen_time, asset_prefix="../assets/"))
    dates = [fn[:-5] for fn in os.listdir(os.path.join(ROOT, "data"))
             if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", fn)]
    with open(os.path.join(ROOT, "archive.html"), "w", encoding="utf-8") as f:
        f.write(build_archive_index(dates))
    print(f"done: {len(items)} items from {raw_total} candidates, day={day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
