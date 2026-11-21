"""数据目录必须可注入：从任意 cwd 运行都只写 --data-dir 指定的位置。"""
import os

import pytest

from animetimeline import scraper


def test_resolve_data_dir_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMETIMELINE_DATA_DIR", str(tmp_path / "env"))
    assert scraper.resolve_data_dir() == str(tmp_path / "env")
    assert scraper.resolve_data_dir(str(tmp_path / "arg")) == str(tmp_path / "arg")


def test_scraper_writes_only_inside_data_dir(tmp_path):
    data = tmp_path / "store"
    s = scraper.BangumiScraper(str(data))
    s.cache = {"1": {"score": "7"}}
    s.cache_dirty = True
    s._save_cache()
    assert (data / ".subject_cache.json").exists()
    assert not os.path.exists(tmp_path / ".." / "data" / ".subject_cache.json")


def test_run_from_foreign_cwd_uses_data_dir(tmp_path, monkeypatch):
    """在无关目录执行 auto，只读 --data-dir，不污染 cwd。"""
    work = tmp_path / "elsewhere"
    work.mkdir()
    data = tmp_path / "store"
    data.mkdir()
    monkeypatch.chdir(work)
    pytest.importorskip("aiohttp")
    monkeypatch.setattr(scraper.BangumiScraper, "scrape_time_range", _empty, raising=True)
    assert scraper.run(["auto", "--year", "2026", "--data-dir", str(data)]) == 0
    assert sorted(p.name for p in work.iterdir()) == []


async def _empty(self, *a, **k):
    return []


def test_default_data_dir_is_data_subdir(tmp_path, monkeypatch):
    """默认值不许是 cwd 本身：cwd 是仓库根，年份文件写进去就是 2026-11 那场事故。"""
    monkeypatch.delenv("ANIMETIMELINE_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert scraper.resolve_data_dir() == str(tmp_path / "data")


def test_index_lives_at_repo_root_for_data_dir(tmp_path):
    data = tmp_path / "data"
    assert scraper.default_index_path(str(data)) == str(tmp_path / "Bangumi_Anime.md")
    # 非 data 名字的数据目录：索引就地生成，别往上一级乱写
    other = tmp_path / "store"
    assert scraper.default_index_path(str(other)) == str(other / "Bangumi_Anime.md")


def test_index_links_match_index_location(tmp_path):
    """索引在仓库根 -> 链接 data/YYYY.md；索引在数据目录内 -> 直接 YYYY.md。"""
    data = tmp_path / "data"
    data.mkdir()
    (data / "2026.md").write_text(
        "# 报告\n\n## 2026年\n\n"
        "| 放送日期 | 封面 | 中文标题 | 日文标题 | 话数 | 评分 | 评分人数 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 2026-01-01 |  | [A](https://bangumi.tv/subject/1) | A | 12 | 6.0 | 3 |\n",
        encoding="utf-8",
    )
    s = scraper.BangumiScraper(str(data))
    s.generate_markdown([], str(tmp_path / "Bangumi_Anime.md"))
    assert "(data/2026.md)" in (tmp_path / "Bangumi_Anime.md").read_text(encoding="utf-8")

    s.generate_markdown([], str(data / "Bangumi_Anime.md"))
    assert "(2026.md)" in (data / "Bangumi_Anime.md").read_text(encoding="utf-8")


def test_unknown_year_never_creates_none_file(tmp_path):
    """year 为 None 的条目不许落盘成 None.md（旧索引里那个 None 年就是这么来的）。"""
    data = tmp_path / "data"
    data.mkdir()
    s = scraper.BangumiScraper(str(data))
    s.generate_markdown(
        [{"year": None, "month": 0, "day": 0, "title": "x", "url": "https://bangumi.tv/subject/9"}],
        str(tmp_path / "Bangumi_Anime.md"),
    )
    assert not (data / "None.md").exists()
    assert "None年" not in (tmp_path / "Bangumi_Anime.md").read_text(encoding="utf-8")
