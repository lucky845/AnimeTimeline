"""health.py 的规则测试：用临时目录伪造数据，断言每类故障都能被点名。"""
import datetime as dt
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import health  # noqa: E402

HEADER = (
    "# Bangumi番剧数据报告\n\n## {y}年\n\n"
    "| 放送日期 | 封面 | 中文标题 | 日文标题 | 话数 | 评分 | 评分人数 |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n\n"
)


def row(date, score="6.0", sid="1"):
    return (f"| {date} |  | [x](https://bangumi.tv/subject/{sid}) | x | 12 | {score} | 10 |\n")


def write_year(data_dir, year, dates, score="6.0"):
    os.makedirs(data_dir, exist_ok=True)
    body = "".join(row(d, score, str(100 + i)) for i, d in enumerate(dates))
    with open(os.path.join(data_dir, f"{year}.md"), "w", encoding="utf-8") as f:
        f.write(HEADER.format(y=year) + body)


def write_calendar(data_dir, last):
    cal = os.path.join(data_dir, "calendar")
    os.makedirs(cal, exist_ok=True)
    with open(os.path.join(cal, "2026.json"), "w", encoding="utf-8") as f:
        json.dump([{"start_jst": last, "sid": "1", "title": "x", "ep": "1"}], f)


TODAY = dt.date(2026, 11, 9)


def test_healthy_data_has_no_severe(tmp_path):
    d = str(tmp_path)
    write_year(d, 2026, ["2026-10-20", "2026-11-01"])
    write_year(d, 2025, ["2025-12-30"])
    write_calendar(d, "2027-03-08 01:05")
    rep = health.analyse(d, TODAY)
    assert rep["severe"] == []
    assert rep["warn"] == []
    assert rep["years"]["2026"]["rows"] == 2
    assert rep["years"]["2026"]["scored"] == 2


def test_current_year_stale_is_severe(tmp_path):
    """复现真实事故：CI 全绿，但当年数据三个月没动。"""
    d = str(tmp_path)
    write_year(d, 2026, ["2026-08-01"])
    write_year(d, 2025, ["2025-12-30"])
    write_calendar(d, "2027-01-01 00:00")
    rep = health.analyse(d, TODAY, month_gap_days=45)
    assert any("停止更新" in s for s in rep["severe"]), rep["severe"]


def test_missing_month_is_warned(tmp_path):
    d = str(tmp_path)
    write_year(d, 2026, ["2026-09-01", "2026-11-01"])  # 缺 10 月
    write_year(d, 2025, ["2025-12-30"])
    write_calendar(d, "2027-01-01 00:00")
    rep = health.analyse(d, TODAY)
    assert any("2026-10 月没有任何番剧" in w for w in rep["warn"]), rep["warn"]


def test_calendar_coverage_too_short_is_severe(tmp_path):
    d = str(tmp_path)
    write_year(d, 2026, ["2026-11-01"])
    write_year(d, 2025, ["2025-12-30"])
    write_calendar(d, "2026-11-12 01:00")
    rep = health.analyse(d, TODAY)
    assert any("排播数据不足" in s for s in rep["severe"]), rep["severe"]


def test_missing_current_year_file_is_severe(tmp_path):
    d = str(tmp_path)
    write_year(d, 2025, ["2025-12-30"])
    write_calendar(d, "2027-03-08 01:05")
    rep = health.analyse(d, TODAY)
    assert any("缺少 2026.md" in s for s in rep["severe"]), rep["severe"]


def test_cli_exit_code(tmp_path):
    d = str(tmp_path)
    write_year(d, 2026, ["2026-11-01"])
    write_year(d, 2025, ["2025-12-30"])
    write_calendar(d, "2027-03-08 01:05")
    ok = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "health.py"),
         "--data-dir", d, "--today", "2026-11-09"],
        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr

    write_calendar(d, "2026-11-12 01:00")  # 覆盖不足 -> 严重
    bad = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "health.py"),
         "--data-dir", d, "--today", "2026-11-09"],
        capture_output=True, text=True)
    assert bad.returncode == 1, bad.stdout
