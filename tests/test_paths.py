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

