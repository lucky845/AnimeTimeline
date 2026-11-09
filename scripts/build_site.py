#!/usr/bin/env python3
"""把日历数据渲染成可直接部署到 GitHub Pages 的静态页（零依赖，单文件 HTML）。

输入 data/calendar/<year>.json，输出 docs/index.html。
视觉与 lucky845.top 同一套令牌：同一底色、同一套线框与等宽标注。
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
SOURCE = "https://github.com/lucky845/AnimeTimeline"


def load_week(days=7):
    rows = []
    for path in sorted(glob.glob("data/calendar/*.json")):
        year = os.path.basename(path).split(".")[0]
        for ev in json.load(open(path, encoding="utf-8")):
            ev["year"] = year
            rows.append(ev)
    rows.sort(key=lambda e: e["start_jst"])
    return rows


def _day_block(day, events):
    d = datetime.strptime(day, "%Y-%m-%d")
    items = "".join(
        f'<li><time>{r["start_jst"][11:]}</time>'
        f'<a href="https://bangumi.tv/subject/{r["sid"]}">{html.escape(r["title"])}</a>'
        f'<span class="ep">第{html.escape(str(r["ep"]))}话</span></li>'
        for r in events
    )
    return f'<section><h2><b>{day[5:]}</b><span>{WEEKDAYS[d.weekday()]}</span></h2><ul>{items}</ul></section>'


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

    body = "".join(_day_block(d, by_day[d]) for d in sorted(by_day)) or (
        '<p class="empty">最近一周没有排播。日历每天重建，明天再来看看。</p>'
    )
    years = sorted({r["year"] for r in rows}, reverse=True)
    links = "".join(
        f'<a class="ics" href="calendar/{y}.ics">订阅 {y} 年 .ics</a>' for y in years
    )
    built = now.strftime("%Y-%m-%d %H:%M")
    span = f"{week[0]['start_jst'][:10]} 起" if week else "暂无排播"
    works = len({r["sid"] for r in week})
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
<meta name="color-scheme" content="dark">
<style>
:root {{
  --bg:#0c1216; --panel:#121b20; --panel-2:#0f171c;
  --ink:#cedfe3; --soft:#a7bcc2; --dim:#6b8189;
  --cyan:#4ec2c6; --amber:#d89a3f;
  --line:#1f2c33; --line-soft:#18252c;
  --sans:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Source Han Sans SC",sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Mono",Menlo,Consolas,monospace;
}}
* {{ box-sizing:border-box; }}
html {{ -webkit-text-size-adjust:100%; }}
body {{
  margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.65 var(--sans);
  font-feature-settings:"tnum" 1;
}}
main {{ max-width:940px; margin:0 auto; padding:56px 24px 72px; }}
a {{ color:inherit; text-decoration:none; }}
a:hover {{ color:var(--cyan); }}
a:focus-visible {{ outline:2px solid var(--cyan); outline-offset:3px; border-radius:2px; }}

.top {{ display:flex; align-items:baseline; justify-content:space-between;
  gap:16px; padding-bottom:14px; border-bottom:1px solid var(--line);
  font:12.8px/1.4 var(--mono); color:var(--soft); }}
.top nav {{ display:flex; gap:18px; }}

.hero {{ padding:44px 0 30px; border-bottom:1px solid var(--line); }}
.caret {{ font:13px/1.4 var(--mono); color:var(--cyan); margin:0 0 18px; }}
h1 {{ font-size:clamp(34px,6vw,56px); line-height:1.12; letter-spacing:-.015em;
  font-weight:800; margin:0 0 16px; }}
h1 em {{ font-style:normal; color:var(--cyan); }}
.lede {{ margin:0; max-width:34em; color:var(--soft); font-size:17px; }}

.panel {{ display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:2px;
  margin:26px 0 0; }}
.panel div {{ background:var(--panel); padding:14px 16px; }}
.panel dt {{ font:12.8px/1.4 var(--mono); color:var(--dim); margin:0 0 6px; }}
.panel dd {{ margin:0; font-size:20px; font-weight:700; letter-spacing:-.01em; }}
.panel dd small {{ font:12.8px/1.4 var(--mono); color:var(--dim); font-weight:400; margin-left:4px; }}

.actions {{ display:flex; flex-wrap:wrap; gap:10px; margin:24px 0 0; }}
.ics {{ display:inline-block; padding:9px 16px; border-radius:2px;
  border:1px solid var(--cyan-dim,#4ec2c68c); color:var(--cyan);
  font:12.8px/1.4 var(--mono); }}
.ics:hover {{ background:#4ec2c614; color:var(--cyan); }}
.ics.plain {{ border-color:var(--line); color:var(--soft); }}
.ics.plain:hover {{ color:var(--ink); background:var(--panel); }}

.list {{ margin:8px 0 0; }}
.list > h2 {{ font:12.8px/1.4 var(--mono); color:var(--dim); font-weight:400;
  margin:34px 0 0; padding-bottom:10px; border-bottom:1px solid var(--line); }}
section {{ display:grid; grid-template-columns:88px 1fr; column-gap:20px;
  padding:16px 0; border-bottom:1px solid var(--line-soft); }}
section h2 {{ margin:0; font-size:15px; font-weight:700; line-height:1.5; }}
section h2 .wk {{ display:block; font:12.8px/1.5 var(--mono); color:var(--dim); font-weight:400; }}
ul {{ list-style:none; margin:0; padding:0; }}
li {{ display:grid; grid-template-columns:52px 1fr auto; gap:12px;
  align-items:baseline; padding:5px 0; }}
time {{ font:13px/1.4 var(--mono); color:var(--amber); }}
li a {{ color:var(--ink); }}
li a:hover {{ color:var(--cyan); }}
.ep {{ font:12.8px/1.4 var(--mono); color:var(--dim); white-space:nowrap; }}
.empty {{ color:var(--soft); border-bottom:1px solid var(--line-soft); padding:18px 0; }}

footer {{ margin-top:44px; padding-top:18px; border-top:1px solid var(--line);
  display:grid; grid-template-columns:repeat(2,1fr); gap:14px 24px;
  font:12.8px/1.7 var(--mono); color:var(--dim); }}
footer a {{ color:var(--soft); text-decoration:underline; text-underline-offset:2px; }}
footer .rev {{ grid-column:1/-1; color:var(--dim); }}

@media (max-width:640px) {{
  main {{ padding:36px 18px 56px; }}
  .panel {{ grid-template-columns:repeat(2,1fr); }}
  section {{ grid-template-columns:1fr; row-gap:8px; }}
  li {{ grid-template-columns:48px 1fr; }}
  .ep {{ grid-column:2; }}
  footer {{ grid-template-columns:1fr; }}
}}
@media (prefers-reduced-motion:no-preference) {{
  .hero {{ animation:rise .5s ease-out both; }}
  @keyframes rise {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:none; }} }}
}}
</style>
</head>
<body><main>
<div class="top">
  <a href="https://lucky845.top">lucky845</a>
  <nav><a href="https://lucky845.top">主页</a><a href="https://blog.lucky845.top">笔记</a>
  <a href="{SOURCE}">GitHub</a></nav>
</div>

<div class="hero">
  <p class="caret">$ animetimeline --week</p>
  <h1>这一周，<em>{len(week)}</em> 集番剧排在日历上。</h1>
  <p class="lede">周末要追哪部、新番几点开播，都在下面这张表里。存成 .ics 后，播出时间会自动跟随时区换算。</p>
  <dl class="panel">
    <div><dt>本周排播</dt><dd>{len(week)}<small>集</small></dd></div>
    <div><dt>涉及作品</dt><dd>{works}<small>部</small></dd></div>
    <div><dt>覆盖范围</dt><dd style="font-size:15px">{span}</dd></div>
    <div><dt>时区</dt><dd style="font-size:15px">JST<small>+09:00</small></dd></div>
  </dl>
  <div class="actions">{links}<a class="ics plain" href="{SOURCE}">查看源码</a></div>
</div>

<div class="list">{body}</div>

<footer>
  <span>数据：bangumi-data + bgm.tv</span>
  <span>重建：每日 UTC 09:00</span>
  <span class="rev">构建于 {built} · REV.{now.strftime('%Y-%m')}</span>
</footer>
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
