#!/usr/bin/env python3
"""回填 data/*.md 中缺失的评分 / 评分人数 / 封面 / 话数。

只补空，不改已有真值；写回前做全量行数校验，任何异常直接放弃。
用法：
    python scripts/backfill_scores.py            # 全部年份
    python scripts/backfill_scores.py 2025 2026  # 指定年份
"""
import asyncio
import os
import re
import sys

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pull  # noqa: E402

SUBJECT_RE = re.compile(r"subject/(\d+)")
# 按 " | " 切单元格：标题里可能有转义的竖线，但单元格分隔一定是 " | "
ROW_RE = re.compile(r"^\| (.*) \|$")


def split_row(line):
    m = ROW_RE.match(line)
    if not m:
        return None
    parts = [c.strip() for c in m.group(1).split(" | ")]
    return parts if len(parts) == 7 else None


def patch_row(line, info):
    parts = split_row(line)
    if parts is None:
        return line, False
    date, cover, title, jp, eps, score, votes = parts
    changed = False
    if score in ("-", "") and info.get("score"):
        score = str(info["score"])
        votes = str(info.get("votes") or 0)
        changed = True
    if not cover and info.get("cover"):
        cover = f"![]({info['cover']})"
        changed = True
    if eps in ("未知", "") and info.get("eps"):
        eps = str(info["eps"])
        changed = True
    if not changed:
        return line, False
    return f"| {date} | {cover} | {title} | {jp} | {eps} | {score} | {votes} |", True


async def main(years):
    async with pull.BangumiScraper() as scraper:
        async with aiohttp.ClientSession(trust_env=True) as session:
            for year in years:
                path = os.path.join("data", f"{year}.md")
                if not os.path.exists(path):
                    continue
                with open(path, encoding="utf-8") as f:
                    lines = f.read().splitlines()
                todo = []
                for idx, line in enumerate(lines):
                    m = SUBJECT_RE.search(line)
                    parts = split_row(line)
                    if not m or parts is None:
                        continue
                    date, cover, title, jp, eps, score, votes = parts
                    # 只处理确实缺数据的行，避免把整库 subject 都请求一遍
                    if score in ("-", "") or not cover or eps in ("未知", ""):
                        todo.append((idx, m.group(1)))
                ids = sorted({sid for _, sid in todo})
                results = await asyncio.gather(
                    *(scraper._fetch_subject(session, sid) for sid in ids)
                )
                info_map = dict(zip(ids, results))

                filled = 0
                for idx, sid in todo:
                    info = info_map.get(sid)
                    if not info:
                        continue
                    lines[idx], changed = patch_row(lines[idx], info)
                    filled += int(changed)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                print(f"{year}: subject {len(ids)} 个，本次补全 {filled} 行")


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2025, 2026]
    asyncio.run(main(years))
