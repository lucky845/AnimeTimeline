"""全库重复 subject 必须让任务失败（exit 2），而不是静默写坏数据。"""
import pytest

from animetimeline.scraper import BangumiScraper


def _row(sid, date="2026-10-11"):
    return f"| {date} |  | [x](https://bangumi.tv/subject/{sid}) | x | 12 | 7.0 | 9 |"


def test_duplicate_subject_fails(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "2026.md").write_text(
        _row("111") + "\n" + _row("111", "2026-10-12") + "\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit) as exc:
        BangumiScraper().assert_no_duplicates(str(tmp_path / "data"))
    assert exc.value.code == 2


def test_clean_data_passes(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "2026.md").write_text(
        _row("111") + "\n" + _row("222", "2026-10-12") + "\n", encoding="utf-8"
    )
    BangumiScraper().assert_no_duplicates(str(tmp_path / "data"))
