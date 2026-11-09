#!/usr/bin/env python3
"""一次性清理：同一 subject 只保留信息最全的一行。

规则：
  - 同一 subject id 的多行 -> 保留"信息量"最高的一行（评分 > 话数 > 封面 > 日文标题）
  - 信息量相同则保留日期最精确的一行
  - 不删除任何 subject，只删除空壳重复行
用法: python scripts/dedupe_data.py --data-dir data [--dry-run]
"""
import argparse
import glob
import os
import re
import sys

from check_data import ROW_DATE  # 复用行解析正则

SUBJ = re.compile(r"subject/(\d+)")


def info_score(line):
    cells = [c.strip() for c in line.split("|")[1:-1]]
    if len(cells) < 7:
        return 0
    date_s, cover, title, jp, eps, score, votes = cells[:7]
    s = 0
    if score not in ("-", ""):
        s += 100
    if votes not in ("0", ""):
        s += 10
    if eps not in ("未知", ""):
        s += 20
    if cover:
        s += 5
    if jp:
        s += 2
    # 日期精度权重
    s += len([p for p in date_s.split("-") if p.strip().isdigit()])
    return s


def process(path, dry):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    header, rows, tail = [], [], []
    body_started = False
    for line in lines:
        if line.startswith("| 放送日期"):
            body_started = True
            header.append(line)
            continue
        if body_started and line.startswith("| ---"):
            header.append(line)
            continue
        if body_started and line.startswith("| "):
            rows.append(line)
            continue
        (tail if body_started else header).append(line)

    best = {}
    order = []
    for line in rows:
        m = SUBJ.search(line)
        if not m:
            order.append(("noid", line))
            continue
        sid = m.group(1)
        cur = best.get(sid)
        if cur is None:
            best[sid] = line
            order.append((sid, None))
        elif info_score(line) > info_score(cur):
            best[sid] = line

    out_rows = []
    seen = set()
    for key, raw in order:
        if key == "noid":
            out_rows.append(raw)
        elif key not in seen:
            seen.add(key)
            out_rows.append(best[key])

    removed = len(rows) - len(out_rows)
    if removed and not dry:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(header + out_rows + tail)
    return len(rows), len(out_rows), removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    total_removed = 0
    for path in sorted(glob.glob(os.path.join(args.data_dir, "*.md"))):
        before, after, removed = process(path, args.dry_run)
        if removed:
            print(f"{path}: {before} -> {after} (删除 {removed} 行)")
            total_removed += removed
    print(f"{'[dry-run] ' if args.dry_run else ''}共删除重复行: {total_removed}")


if __name__ == "__main__":
    main()
