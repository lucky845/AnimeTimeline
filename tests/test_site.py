"""静态页必须包含可订阅的绝对 ICS 地址与构建时间戳。"""
from datetime import datetime, timedelta

import build_site


def _rows():
    t = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    return [{"year": "2026", "start_jst": t, "sid": "1", "title": "t", "ep": "1"}]


def test_render_has_absolute_ics_and_timestamp():
    html = build_site.render(_rows())
    assert f'href="{build_site.SITE}/calendar/2026.ics"' in html
    assert "构建于" in html
    assert html.count('<section>') == 1
