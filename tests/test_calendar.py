"""日历生成的核心逻辑回归：broadcast 解析、漂移守卫、ICS 折叠。"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0] + "/scripts")

import build_calendar as bc


def test_parse_broadcast_weekly():
    dt, period = bc.parse_broadcast("R/2026-10-07T15:00:00.000Z/P7D")
    assert dt == datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    assert period == 7


def test_parse_broadcast_rejects_garbage():
    assert bc.parse_broadcast(None) == (None, None)
    assert bc.parse_broadcast("every friday") == (None, None)


def test_drift_guard_ignores_stale_airdates():
    """同名旧番的 airdate（2022 年）不能把 2026 年这季拉到过去。"""
    first = datetime(2026, 10, 7, 16, 15, tzinfo=timezone.utc)
    stale = {1: datetime(2022, 7, 25, tzinfo=timezone.utc)}
    out = bc.expand_airings(
        "t", first, 7, 12, stale,
        datetime(2027, 3, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    assert out[0][1] == first


def test_expand_respects_horizon_and_cutoff():
    first = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    out = bc.expand_airings(
        "t", first, 7, 12, {},
        datetime(2026, 11, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    assert [ep for ep, _ in out] == [1, 2, 3, 4]


def test_fold_line_keeps_utf8_intact():
    line = "SUMMARY:" + "很长很长的中文标题" * 8
    folded = bc.fold_line(line)
    assert len(folded) > 1
    for chunk in folded:
        assert len(chunk.encode("utf-8")) <= 75
        chunk.encode("utf-8").decode("utf-8")  # 不能劈开多字节字符
    # 去掉续行前导空格后应能无损还原
    rebuilt = folded[0] + "".join(c[1:] for c in folded[1:])
    assert rebuilt == line
