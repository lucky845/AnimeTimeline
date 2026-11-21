#!/usr/bin/env python3
"""数据腐化守卫：零依赖、纯 stdlib，CI 与本地都能跑。

任一规则不通过 -> exit 1，并打印违规行号。
用法: python scripts/check_data.py [--data-dir data] [--max-stale-days 45] [--min-scored-ratio 0.95]
"""
import argparse
import datetime as dt
import glob
import os
import re
import sys

ROW_DATE = re.compile(r"^\| (\d{4})(?:-(\d{2})(?:-(\d{2}))?)? \|")
SCORE_CELL = re.compile(r"\|\s*([0-9]+(?:\.[0-9]+)?|-)\s*\|\s*[0-9]+\s*\|\s*$")
HEADER_YEAR = re.compile(r"^## (\d{4})年")


def scan(path):
    """返回 [(line_no, subject_id, date_tuple, score)]"""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.startswith("| ") or line.startswith("| ---") or line.startswith("| 放送日期"):
                continue
            m = ROW_DATE.match(line)
            if not m:
                continue
            y, mo, d = m.group(1), m.group(2), m.group(3)
            date = (int(y), int(mo) if mo else 0, int(d) if d else 0)
            sid = ""
            sm = re.search(r"subject/(\d+)", line)
            if sm:
                sid = sm.group(1)
            sm2 = SCORE_CELL.search(line)
            score = sm2.group(1) if sm2 else "-"
            rows.append((i, sid, date, score))
    return rows


def check_index(path, years):
    """索引链接的年份集合必须与 data/*.md 完全一致，且链接目标真实存在。"""
    if not os.path.exists(path):
        return [f"索引文件不存在: {path}"]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    linked = set(re.findall(r"\]\(\s*(?:data/)?(\d{4})\.md\s*\)", text))
    problems = []
    missing = sorted(years - linked)
    extra = sorted(linked - years)
    if missing:
        problems.append(f"{path}: 索引漏了 {len(missing)} 年: {', '.join(missing[:10])}")
    if extra:
        problems.append(f"{path}: 索引里有 {len(extra)} 年没有数据文件: {', '.join(extra[:10])}")
    if "None年" in text or "None.md" in text:
        problems.append(f"{path}: 索引里出现 None 年（无法解析年份的脏数据）")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--max-stale-days", type=int, default=45)
    ap.add_argument("--min-scored-ratio", type=float, default=0.95,
                    help="评分行数相对基线的下限比例")
    ap.add_argument("--baseline", default=".data-baseline.json")
    ap.add_argument("--today", default=None)
    ap.add_argument("--repo-root", default=".",
                    help="仓库根，用于检查散落的年份 md；传空可跳过")
    ap.add_argument("--index", default="Bangumi_Anime.md",
                    help="年份索引 md；传空字符串可跳过索引一致性检查")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.data_dir, "*.md")))
    if not files:
        print(f"FAIL 未找到数据文件: {args.data_dir}/*.md")
        return 1

    errors = []
    total_rows = 0
    scored_rows = 0
    latest = (0, 0, 0)

    for path in files:
        fname = os.path.basename(path)
        want_year = fname[:-3] if fname[:-3].isdigit() else None
        if want_year and int(want_year) > 3000:
            errors.append(f"{path}: 非法年份文件，应删除")
        with open(path, "r", encoding="utf-8") as f:
            header_years = {int(m.group(1)) for m in
                            (HEADER_YEAR.match(l.strip()) for l in f) if m}
        if want_year and header_years and header_years != {int(want_year)}:
            errors.append(f"{path}: 标题年份 {sorted(header_years)} 与文件名 {want_year} 不符")

        rows = scan(path)
        total_rows += len(rows)
        seen = {}
        for line_no, sid, date, score in rows:
            if score != "-":
                scored_rows += 1
            if date > latest and date[0] < 3000:
                latest = date
            if sid:
                if sid in seen:
                    errors.append(
                        f"{path}:{line_no}: 重复 subject {sid}（首次出现于第 {seen[sid]} 行）")
                else:
                    seen[sid] = line_no

    # 规则 3：数据新鲜度
    today = (dt.date.fromisoformat(args.today) if args.today else dt.date.today())
    if latest[0]:
        last = dt.date(*[x if x else 1 for x in latest])
        stale = (today - last).days
        if stale > args.max_stale_days:
            errors.append(
                f"数据过期: 最新放送日 {last} 距今 {stale} 天 > {args.max_stale_days} 天")

    # 规则 5：仓库根不许出现年份 md
    # 2026-11 事故：CI 未传 --data-dir，年份文件全写进仓库根，与 data/ 打架。
    if args.repo_root:
        stray = sorted(
            n for n in os.listdir(args.repo_root)
            if re.fullmatch(r"\d{4}\.md", n) or n == "None.md"
        )
        if stray:
            errors.append(
                f"仓库根存在散落的年份文件 {stray}：年份数据只允许放在 {args.data_dir}/")

    # 规则 4：索引必须与 data/ 里的年份文件一一对应
    # 旧索引长期只剩 2024/2026/None 三年，却没人发现——索引和真实数据早就脱钩了。
    if args.index:
        errors.extend(check_index(args.index, {os.path.basename(p)[:-3] for p in files}))

    # 规则 2：评分行数不得大幅下降（相对基线）
    if os.path.exists(args.baseline):
        import json
        with open(args.baseline, encoding="utf-8") as f:
            base = json.load(f).get("scored_rows", 0)
        if base and scored_rows < base * args.min_scored_ratio:
            errors.append(
                f"评分行数骤降: {scored_rows} < 基线 {base} * {args.min_scored_ratio}")

    print(f"扫描 {len(files)} 个文件 / {total_rows} 行 / 真实评分 {scored_rows} 行 / "
          f"最新放送日 {'-'.join(str(x) for x in latest if x) or '无'}")

    if errors:
        print(f"\nFAIL {len(errors)} 项:")
        for e in errors[:50]:
            print("  - " + e)
        if len(errors) > 50:
            print(f"  ... 另有 {len(errors) - 50} 项")
        return 1
    print("PASS 全部数据校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
