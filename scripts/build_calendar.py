#!/usr/bin/env python3
"""按周生成番剧播出日历（ICS），数据来自 bangumi-data 的 broadcast 字段 + bgm.tv 逐话 airdate。

为什么不用 md 里的「放送日期」列：那其实是季度首播日，不是每周播出日。
broadcast 形如 R/2026-10-07T15:00:00.000Z/P7D（ISO-8601 重复），给出首播时刻 + 周期。
逐话 airdate 只在已播出的剧集上可靠，用来校正节假日停播。

用法：
    python scripts/build_calendar.py            # 当年
    python scripts/build_calendar.py 2026       # 指定年
    python scripts/build_calendar.py 2026 --weeks 12
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from animetimeline import scraper as pull  # noqa: E402

ITEMS_URL = "https://raw.githubusercontent.com/bangumi-data/bangumi-data/master/data/items/{y}/{m:02d}.json"
EPISODES_API = "https://api.bgm.tv/v0/episodes?subject_id={sid}&type=0&limit=50"
REPEAT_RE = re.compile(
    r"^R/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?Z/P(\d+)D$"
)
OUT_DIR = "data/calendar"
# 逐话 airdate 与周期推算相差超过这个天数，就判定 airdate 不可信
DRIFT_LIMIT_DAYS = 30


def parse_broadcast(raw):
    """R/2026-10-07T15:00:00.000Z/P7D -> (UTC datetime, 周期天数)。解析不了返回 (None, None)。"""
    m = REPEAT_RE.match((raw or "").strip())
    if not m:
        return None, None
    y, mo, d, hh, mm, ss, days = m.groups()
    return datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss), tzinfo=timezone.utc), int(days)


def subject_id_of(item):
    for site in item.get("sites", []) or []:
        if site.get("site") == "bangumi":
            return str(site.get("id", ""))
    return ""


def expand_airings(title, first_utc, period_days, total, airdates, horizon_end, now_cutoff):
    """展开每一话的播出时刻（UTC）。有逐话 airdate 时以它为准，否则按周期推。"""
    out = []
    for ep in range(1, total + 1):
        scheduled = first_utc + timedelta(days=period_days * (ep - 1))
        # 用 airdate 的「日期」+ broadcast 的「时刻」：
        # airdate 只有日期（解析出来是 00:00Z），直接用它会把播出时间全变成 09:00 JST。
        # 只有日期对得上周期时才采信（挡掉同名旧番的过期 airdate）。
        dt = scheduled
        air_date = airdates.get(ep)
        if air_date is not None and abs((air_date - scheduled).days) <= DRIFT_LIMIT_DAYS:
            dt = air_date.replace(
                hour=first_utc.hour, minute=first_utc.minute, second=first_utc.second
            )
        if dt < now_cutoff or dt > horizon_end:
            continue
        out.append((ep, dt))
    return out


async def fetch_json(session, url):
    async with session.get(url, headers={"User-Agent": pull.USER_AGENT}) as resp:
        if resp.status == 404:
            return None
        resp.raise_for_status()
        return await resp.json(content_type=None)


async def fetch_airdates(session, sid):
    try:
        data = await fetch_json(session, EPISODES_API.format(sid=sid))
        if not data:
            return {}
        out = {}
        for e in data.get("data", []):
            if e.get("type") != 0 or not e.get("airdate"):
                continue
            try:
                out[int(e.get("sort") or e.get("ep") or 0)] = datetime.fromisoformat(e["airdate"]).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
        # 同一日期覆盖全部话数说明是「一次性放送」，此时不适合按周展开
        if len(set(v.date() for v in out.values())) <= 1 and len(out) > 1:
            return {}
        return out
    except Exception:
        return {}


def ics_escape(text):
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_line(line, limit=72):
    """RFC 5545 要求每行不超过 75 octets，超出部分折到下一行并以单个空格开头。
    按字符累加字节数，避免把多字节汉字劈成半个 UTF-8 序列。"""
    if len(line.encode("utf-8")) <= limit:
        return [line]
    chunks, cur, cur_len = [], "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if cur_len + b > limit:
            chunks.append(cur)
            cur, cur_len = " " + ch, 1 + b
        else:
            cur += ch
            cur_len += b
    if cur:
        chunks.append(cur)
    return chunks


def build_ics(events, cal_name):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AnimeTimeline//Calendar//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(cal_name)}",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Tokyo",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0900",
        "TZOFFSETTO:+0900",
        "TZNAME:JST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
    for ev in events:
        dt_jst = ev["start"] + timedelta(hours=9)
        uid = f"{ev['sid']}-ep{ev['ep']}@animetimeline"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;TZID=Asia/Tokyo:{dt_jst.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID=Asia/Tokyo:{(dt_jst + timedelta(minutes=30)).strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{ics_escape(ev['title'])} 第{ev['ep']}话",
            f"DESCRIPTION:{ics_escape(ev['desc'])}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    folded = []
    for line in lines:
        folded.extend(fold_line(line))
    return "\r\n".join(folded) + "\r\n"


async def main(year, weeks):
    now = datetime.now(timezone.utc)
    horizon_end = now + timedelta(weeks=weeks)
    # 只发布「还没播完」的节目：往前留 14 天，方便用户回看本周已播内容
    now_cutoff = now - timedelta(days=14)
    async with aiohttp.ClientSession(trust_env=True) as session:
        items = []
        for m in (1, 4, 7, 10):
            raw = await fetch_json(session, ITEMS_URL.format(y=year, m=m))
            items.extend(raw or [])
        logging = f"bangumi-data {year} 年 {len(items)} 条"
        print(logging)

        candidates = []
        for it in items:
            first_utc, period = parse_broadcast(it.get("broadcast"))
            if not first_utc or not period:
                continue
            sid = subject_id_of(it)
            if not sid:
                continue
            end_guess = first_utc + timedelta(days=period * 12)
            if end_guess < now or first_utc > horizon_end:
                continue
            candidates.append((sid, it, first_utc, period))

        sem = asyncio.Semaphore(pull.MAX_CONCURRENT)

        async def enrich(c):
            sid, it, first_utc, period = c
            async with sem:
                info = await fetch_json(session, pull.SUBJECT_API.format(subject_id=sid)) or {}
                airdates = await fetch_airdates(session, sid)
            return sid, it, first_utc, period, info, airdates

        enriched = await asyncio.gather(*(enrich(c) for c in candidates))

    events = []
    for sid, it, first_utc, period, info, airdates in enriched:
        total = info.get("total_episodes") or info.get("eps") or 12
        titles = it.get("titleTranslate") or {}
        title = (titles.get("zh-Hans") or titles.get("zh-Hant") or [it.get("title") or ""])[0]
        url = f"https://bangumi.tv/subject/{sid}"
        for ep, dt in expand_airings(
            title, first_utc, period, int(total), airdates,
            horizon_end + timedelta(days=period), now_cutoff,
        ):
            events.append(
                {
                    "sid": sid,
                    "ep": ep,
                    "start": dt,
                    "title": title,
                    "desc": f"{it.get('title') or ''}\n{url}",
                }
            )

    events.sort(key=lambda e: e["start"])
    os.makedirs(OUT_DIR, exist_ok=True)
    ics = build_ics(events, f"AnimeTimeline {year}")
    path = os.path.join(OUT_DIR, f"{year}.ics")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(ics)

    payload = [
        {
            "sid": e["sid"],
            "ep": e["ep"],
            "title": e["title"],
            "start_jst": (e["start"] + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
        }
        for e in events
    ]
    with open(os.path.join(OUT_DIR, f"{year}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"✅ {path}: {len(events)} 个播出事件，覆盖 {len({e['sid'] for e in events})} 部番剧")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("year", nargs="?", type=int, default=datetime.now().year)
    ap.add_argument("--weeks", type=int, default=12)
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.year, a.weeks)))
