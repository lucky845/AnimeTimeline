#!/usr/bin/env python3
"""健康报告：把「CI 全绿但数据停了」这类静默故障变成可见信号。

与 check_data.py 的分工：
  - check_data.py 是阀门（红/绿，卡 CI）
  - 本文件是体检表（给人和 JSON 看的趋势），阈值用 --warn-* 调

用法:
    python scripts/health.py                 # 人读报告
    python scripts/health.py --json          # 机器读
    python scripts/health.py --max-month-gap 45
退出码: 有严重项 -> 1，否则 0（--no-fail 可强制 0）
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

ROW = re.compile(r"^\| (\d{4})(?:-(\d{2})(?:-(\d{2}))?)? \|.*?\| ([0-9.]+|-|) \| (\d*) \|$")
YEAR_HEADER = re.compile(r"^## (\d{4})年")
MONTH_HEADER = re.compile(r"^## (\d{4})-(\d{2})")
SUBJECT = re.compile(r"subject/(\d+)")


def scan_file(path):
    """返回 dict：rows / months / scored / zero_score / undated / subjects"""
    rows, months, scored, zero, undated, subjects = 0, {}, 0, 0, 0, set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            mh = MONTH_HEADER.match(line)
            if mh:
                months[f"{mh.group(1)}-{mh.group(2)}"] = 0
                continue
            if not ROW.match(line):
                continue
            rows += 1
            m = ROW.match(line)
            y, mo, _d, score, votes = m.groups()
            key = f"{y}-{mo}" if mo else y
            months[key] = months.get(key, 0) + 1
            if not _d:
                undated += 1
            if score not in ("-", ""):
                scored += 1
                if float(score) == 0:
                    zero += 1
            for sm in SUBJECT.finditer(line):
                subjects.add(sm.group(1))
    return {
        "rows": rows, "months": months, "scored": scored,
        "zero_score": zero, "undated": undated, "subjects": len(subjects),
    }


def month_range(first, last):
    # 只有年份的键（如 "1907"）当成一月，避免 int('') 崩
    first = first if len(first) == 7 else f"{first}-01"
    last = last if len(last) == 7 else f"{last}-01"
    y, m = int(first[:4]), int(first[5:7])
    ey, em = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def analyse(data_dir="data", today=None, month_gap_days=45, zero_ratio=0.2):
    today = today or dt.date.today()
    files = sorted(glob.glob(os.path.join(data_dir, "*.md")))
    years = {}
    severe, warn = [], []

    for path in files:
        name = os.path.basename(path)[:-3]
        if not name.isdigit():
            continue
        info = scan_file(path)
        info["file"] = name
        years[name] = info
        if info["rows"] == 0:
            severe.append(f"{name}.md 存在但没有任何数据行")
        if info["undated"] and name in (str(today.year), str(today.year - 1)):
            warn.append(f"{name}.md 有 {info['undated']} 行只有年月、没有具体日期")
        if info["scored"] and info["zero_score"] / info["scored"] > zero_ratio:
            warn.append(
                f"{name}.md 评分里 {info['zero_score']}/{info['scored']} 是 0 分"
                "（bgm.tv 上还没人评分，不是抓取坏了）")

    # 当年 & 去年：月份连续性 + 数据新鲜度
    wanted = [str(today.year), str(today.year - 1)]
    for y in wanted:
        info = years.get(y)
        if not info:
            severe.append(f"缺少 {y}.md（当年/去年数据文件不存在）")
            continue
        months = info["months"]
        if not months:
            continue
        first, last = min(months), max(months)
        for m in month_range(first, last):
            if months.get(m, 0) == 0:
                warn.append(f"{y}.md 里 {m} 月没有任何番剧（月份断档）")
        # 当年数据的最后一个月离今天多远
        if y == str(today.year):
            ly, lm = int(last[:4]), int(last[5:7])
            gap = (today - dt.date(ly, lm, 1)).days
            if gap > month_gap_days:
                severe.append(
                    f"{y}.md 最后一个月是 {last}，距今 {gap} 天 > {month_gap_days}"
                    "（数据可能已停止更新）")

    cal = sorted(glob.glob(os.path.join(data_dir, "calendar", "*.json")))
    cal_events, cal_last = 0, None
    for path in cal:
        for ev in json.load(open(path, encoding="utf-8")):
            cal_events += 1
            s = ev.get("start_jst", "")
            if s and (cal_last is None or s > cal_last):
                cal_last = s
    if not cal:
        warn.append("data/calendar 为空（节日历文件未生成）")
    elif cal_last:
        lag = (today - dt.date.fromisoformat(cal_last[:10])).days
        ahead = -lag
        # 未来事件本身不是错误（日历本来就前瞻）；只有覆盖不足或远得离谱才报警
        if ahead > 200:
            severe.append(f"日历最新事件 {cal_last}（{ahead} 天后）远超合理前瞻窗口，排期计算可能错了")
        elif ahead < 30:
            severe.append(f"日历只覆盖到 {cal_last}（{ahead} 天后），排播数据不足")
        if 0 <= lag > 90:
            warn.append(f"日历最新事件 {cal_last}，距今 {lag} 天，覆盖不足 90 天")

    return {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "years": {k: {kk: vv for kk, vv in v.items()} for k, v in years.items()},
        "calendar": {"files": len(cal), "events": cal_events, "last_event": cal_last},
        "severe": severe,
        "warn": warn,
    }


def render(rep):
    out = [f"# 数据健康报告 · {rep['generated']}", ""]
    out.append("| 年份 | 行数 | 作品数 | 有评分 | 0 分 | 仅年月 | 月份范围 |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for y in sorted(rep["years"], reverse=True)[:6]:
        i = rep["years"][y]
        rng = f"{min(i['months'])} ~ {max(i['months'])}" if i["months"] else "-"
        out.append(f"| {y} | {i['rows']} | {i['subjects']} | {i['scored']} | "
                   f"{i['zero_score']} | {i['undated']} | {rng} |")
    c = rep["calendar"]
    out += ["", f"日历：{c['files']} 个文件 / {c['events']} 个事件 / "
                f"最新 {c['last_event'] or '无'}", ""]
    if rep["severe"]:
        out.append(f"**严重 {len(rep['severe'])} 项**")
        out += [f"- {s}" for s in rep["severe"]]
    if rep["warn"]:
        out.append(f"**提醒 {len(rep['warn'])} 项**")
        out += [f"- {s}" for s in rep["warn"][:20]]
        if len(rep["warn"]) > 20:
            out.append(f"- …另有 {len(rep['warn']) - 20} 项")
    if not rep["severe"] and not rep["warn"]:
        out.append("全部正常。")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--month-gap", type=int, default=45,
                    help="当年数据最后一个月距今超过多少天算严重")
    ap.add_argument("--today", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fail", action="store_true")
    args = ap.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else None
    rep = analyse(args.data_dir, today, args.month_gap)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(render(rep))
    if rep["severe"] and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
