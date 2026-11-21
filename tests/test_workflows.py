"""CI 配置守卫：防止「守卫步骤被删掉」或「包改造后 CI 仍调用旧入口」。"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")


def read(name):
    with open(os.path.join(WF, name), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("name", ["update-anime.yml", "pr-check.yml", "pages.yml", "publish.yml"])
def test_yaml_parses_as_expected_shape(name):
    """零依赖：只做结构断言，避免为 CI 引入 yaml 依赖。"""
    text = read(name)
    assert text.startswith("name:"), f"{name} 缺少 name"
    assert re.search(r"^on:", text, re.M), f"{name} 缺少 on 触发"
    assert re.search(r"^jobs:", text, re.M), f"{name} 缺少 jobs"


def test_update_workflow_keeps_guards():
    text = read("update-anime.yml")
    assert "scripts/check_data.py" in text, "数据腐化守卫被删了"
    assert "scripts/health.py" in text, "健康报告步骤被删了"
    assert "python -m animetimeline auto" in text, "仍在调用已删除的 pull.py 入口"
    assert os.path.exists(os.path.join(ROOT, "animetimeline", "__main__.py")), \
        "python -m animetimeline 需要 animetimeline/__main__.py"
    assert "pull.py" not in text


def test_pr_check_covers_package_and_scripts():
    text = read("pr-check.yml")
    assert "animetimeline" in text
    assert "pytest" in text
    assert "scripts/check_data.py" in text


def test_publish_only_on_tags():
    text = read("publish.yml")
    assert 'tags: ["v*"]' in text
    assert "refs/tags/v" in text, "手动触发时 publish job 必须被 if 挡掉"
    assert "data/" in text, "sdist 含 data/ 的守卫被删了"


def test_pages_workflow_triggers_on_calendar_data():
    text = read("pages.yml")
    assert "data/calendar/**" in text, "数据更新后不会重新部署页面"


def test_no_reference_to_removed_dependencies():
    """bs4/lxml/pandas/requests 早已不 import，任何 workflow 再装回来都是回退。"""
    for name in os.listdir(WF):
        if not name.endswith(".yml"):
            continue
        text = read(name)
        for dep in ("lxml", "pandas", "beautifulsoup4", "bs4"):
            assert dep not in text, f"{name} 又引入未使用的依赖 {dep}"

def test_sync_workflow_pins_data_dir_and_index():
    """年份文件必须写到 data/，索引单独落仓库根。

    回归事故：不传 --data-dir 时默认值漂到仓库根，年份文件写进根目录，
    与 data/ 里的历史形成两条互不相让的历史，自动合并 PR 必然冲突。
    """
    text = read("update-anime.yml")
    assert "--data-dir data" in text, "缺少 --data-dir，年份文件会写回仓库根"
    assert "--index-file" in text, "索引落点必须显式声明"


def test_sync_workflow_uses_stable_branch():
    """每天新建一个分支 -> 旧 PR 必然 CONFLICTING -> auto-merge 永远等不到。"""
    text = read("update-anime.yml")
    m = re.search(r"^\s*branch:\s*(.+)$", text, re.M)
    assert m, "未找到 branch 配置"
    assert m.group(1).strip() == "auto-update", f"分支名必须固定为 auto-update，当前 {m.group(1)!r}"


def test_sync_workflow_limits_committed_paths():
    """运行态缓存与根目录杂项绝不能进 PR：它们每天都在制造无关冲突。"""
    text = read("update-anime.yml")
    assert "add-paths:" in text, "必须限定提交范围"
    assert ".subject_cache.json" not in text.split("add-paths:")[1].split("\n\n")[0], \
        "缓存文件不得进入提交清单"


def test_sync_workflow_serialises_runs():
    """两条同步流水线并行 = 两个互相冲突的数据分支。"""
    text = read("update-anime.yml")
    assert "concurrency:" in text, "缺少并发约束"
    assert "anime-data-sync" in text

def test_index_links_match_stored_years(tmp_path):
    """索引与 data/ 必须一一对应：旧索引长期只剩 3 年还挂着 None 年，守卫却全绿。"""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import check_data

    idx = tmp_path / "Bangumi_Anime.md"
    idx.write_text("- [2026年](data/2026.md)\n- [None年](None.md)\n", encoding="utf-8")
    problems = check_data.check_index(str(idx), {"2026", "2025"})
    assert any("漏了" in p for p in problems), problems
    assert any("None" in p for p in problems), problems

    idx.write_text("- [2026年](data/2026.md)\n- [2025年](data/2025.md)\n", encoding="utf-8")
    assert check_data.check_index(str(idx), {"2026", "2025"}) == []


def test_pages_workflow_does_not_nest_calendar_copy():
    """cp -r data/calendar docs/calendar 会拷成 docs/calendar/calendar，链接全 404。"""
    text = read("pages.yml")
    assert "cp -r data/calendar docs/calendar" not in text, "日历又会被套一层目录"
    assert "cp -a data/calendar/. docs/calendar/" in text
