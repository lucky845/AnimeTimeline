"""P0 回归：空值不得覆盖已有值；同一 subject 只出现一次。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from pull import BangumiScraper


@pytest.fixture
def scraper():
    s = BangumiScraper()
    return s


def test_missing_info_does_not_clear_score(scraper):
    """API 返回 None（网络失败）时，md 里已有的评分必须保留。"""
    old = {"score": "5.9", "votes": "64", "cover": "https://x/1.jpg",
           "episodes": "12", "url": "https://bangumi.tv/subject/664389"}
    new = {"score": "-", "votes": "0", "cover": "", "episodes": None,
           "url": "https://bangumi.tv/subject/664389", "unresolved": True}
    assert scraper._merge_old_into_new(new, old) is True
    assert new["score"] == "5.9"
    assert new["votes"] == "64"
    assert new["cover"] == "https://x/1.jpg"
    assert new["episodes"] == "12"


def test_new_value_wins_when_present(scraper):
    """有真实新值时，新值优先。"""
    old = {"score": "5.9", "url": "u"}
    new = {"score": "6.4", "url": "u"}
    scraper._merge_old_into_new(new, old)
    assert new["score"] == "6.4"


def test_no_old_row_is_never_clobbered(scraper):
    assert scraper._merge_old_into_new({"score": "-"}, None) is False


def test_ident_is_subject_id(scraper, tmp_path, monkeypatch):
    """同一 subject 的'未知'与'12'两行必须合并成一行。"""
    data = tmp_path / "data"
    data.mkdir()
    md = data / "2026.md"
    md.write_text(
        "# 报告\n\n## 2026年\n\n"
        "| 放送日期 | 封面 | 中文标题 | 日文标题 | 话数 | 评分 | 评分人数 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2026-10-11 |  | [A](https://bangumi.tv/subject/664389) | A | 未知 | - | 0 |\n"
        "| 2026-10-11 |  | [A](https://bangumi.tv/subject/664389) | A | 12 | 5.9 | 64 |\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    # generate_markdown 只在索引文件存在时才回读 data/*.md，先补上这个前置条件
    index = tmp_path / "Bangumi_Anime.md"
    index.write_text("", encoding="utf-8")
    scraper.generate_markdown([], str(index))
    out = md.read_text(encoding="utf-8")
    assert out.count("subject/664389") == 1, out
    assert "| 5.9 |" in out
