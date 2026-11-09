#!/usr/bin/env python3
"""校验生成的 ICS：结构完整、UID 唯一、行宽符合 RFC 5545。"""
import glob
import os
import re
import sys

MAX_OCTETS = 75


def check(path):
    raw = open(path, encoding="utf-8", newline="").read()
    problems = []
    if raw.count("BEGIN:VEVENT") != raw.count("END:VEVENT"):
        problems.append("VEVENT 起止不匹配")
    if raw.count("BEGIN:VCALENDAR") != 1 or raw.count("END:VCALENDAR") != 1:
        problems.append("VCALENDAR 起止异常")
    uids = re.findall(r"UID:(\S+)", raw)
    if len(uids) != len(set(uids)):
        problems.append("UID 重复")
    if raw.count("BEGIN:VEVENT") != len(uids):
        problems.append("UID 数量与 VEVENT 不一致")
    long_lines = [l for l in raw.split("\r\n") if len(l.encode("utf-8")) > MAX_OCTETS]
    return problems, len(uids), len(long_lines), long_lines[:2]


def main():
    files = sorted(glob.glob("data/calendar/*.ics"))
    if not files:
        print("没有找到 calendar 文件")
        return 1
    bad = 0
    for f in files:
        problems, n, long_n, sample = check(f)
        status = "OK" if not problems else "FAIL"
        print(f"{status} {f}: {n} 个事件, 超宽行 {long_n}")
        for p in problems:
            print(f"   ❌ {p}")
            bad += 1
        if long_n:
            print(f"   ⚠️ 需按 RFC 5545 折叠，示例: {sample[0][:60]}...")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
