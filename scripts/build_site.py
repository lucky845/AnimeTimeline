#!/usr/bin/env python3
"""把日历数据渲染成可直接部署到 GitHub Pages 的静态页（零依赖，单文件 HTML）。

输入 data/calendar/<year>.json，输出 docs/index.html。
部署到 https://animetimeline.lucky845.top（docs/CNAME 指定自定义域）。
"""
import glob
import html
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

OUT_DIR = "docs"
# 部署域名：构建时可用 SITE_URL 覆盖，默认走自定义子域
SITE = os.environ.get("SITE_URL", "https://animetimeline.lucky845.top").rstrip("/")
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def load_week(days=7):
    rows = []
    for path in sorted(glob.glob("data/calendar/*.json")):
        year = os.path.basename(path).split(".")[0]
        for ev in json.load(open(path, encoding="utf-8")):
            ev["year"] = year
            rows.append(ev)
    rows.sort(key=lambda e: e["start_jst"])
    return rows


def render(rows):
    now = datetime.now()
    start = now - timedelta(days=1)
    end = now + timedelta(days=7)
    week = [
        r for r in rows
        if start <= datetime.strptime(r["start_jst"], "%Y-%m-%d %H:%M") <= end
    ]
    by_day = defaultdict(list)
    for r in week:
        by_day[r["start_jst"][:10]].append(r)

    cards = []
    for day in sorted(by_day):
        d = datetime.strptime(day, "%Y-%m-%d")
        items = "".join(
            f'<li><time>{r["start_jst"][11:]}</time>'
            f'<a href="https://bangumi.tv/subject/{r["sid"]}">{html.escape(r["title"])}</a>'
            f'<span class="ep">第{r["ep"]}话</span></li>'
            for r in by_day[day]
        )
        cards.append(
            f'<section><h2>{day[5:]} <small>{WEEKDAYS[d.weekday()]}</small></h2>'
            f"<ul>{items}</ul></section>"
        )

    years = sorted({r["year"] for r in rows}, reverse=True)
    links = "".join(
        f'<a class="ics" href="calendar/{y}.ics">订阅 {y} 年日历 (.ics)</a>' for y in years
    )
    body = "".join(cards) or '<p class="empty">最近一周没有排播</p>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AnimeTimeline · 番剧播出日历</title>
<!-- ICS 用绝对地址：部分日历客户端不接受相对路径订阅 -->
<link rel="alternate" type="text/calendar" title="AnimeTimeline 订阅" href="{SITE}/calendar/2026.ics">
<meta property="og:title" content="AnimeTimeline · 番剧播出日历">
<meta property="og:description" content="每周番剧排播，支持 .ics 订阅">
<meta property="og:url" content="{SITE}/">
<style>
:root {{ color-scheme: light dark; --fg:#1a1a1a; --bg:#fafafa; --muted:#777; --accent:#2f6fed; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fg:#e6e6e6; --bg:#15171a; --muted:#9aa0a6; --accent:#7aa2ff; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2rem 1rem; background:var(--bg); color:var(--fg);
  font:16px/1.6 system-ui,-apple-system,"Noto Sans CJK SC",sans-serif; }}
main {{ max-width:720px; margin:0 auto; }}
h1 {{ font-size:1.5rem; margin:0 0 .25rem; }}
.sub {{ color:var(--muted); margin:0 0 1.5rem; font-size:.9rem; }}
.ics {{ display:inline-block; padding:.5rem .9rem; margin:0 .5rem .5rem 0; border-radius:8px;
  background:var(--accent); color:#fff; text-decoration:none; font-size:.9rem; }}
section {{ border-top:1px solid #8883; padding:.75rem 0; }}
h2 {{ font-size:1rem; margin:0 0 .5rem; }}
h2 small {{ color:var(--muted); font-weight:400; margin-left:.4rem; }}
ul {{ list-style:none; margin:0; padding:0; }}
li {{ display:flex; gap:.75rem; align-items:baseline; padding:.2rem 0; }}
time {{ color:var(--muted); font-variant-numeric:tabular-nums; min-width:3.2rem; }}
a {{ color:var(--fg); text-decoration:none; }}
a:hover {{ color:var(--accent); text-decoration:underline; }}
.ep {{ color:var(--muted); font-size:.85rem; }}
.empty {{ color:var(--muted); }}
</style>
</head>
<body><main>
<h1>番剧播出日历</h1>
<p class="sub">数据来源 bangumi-data + bgm.tv，按 JST 显示，每日自动更新。</p>
{links}
{body}
</main></body></html>
"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = load_week()
    path = os.path.join(OUT_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(rows))
    print(f"✅ {path}: 共 {len(rows)} 条排播记录")


if __name__ == "__main__":
    main()
