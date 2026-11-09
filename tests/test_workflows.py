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
