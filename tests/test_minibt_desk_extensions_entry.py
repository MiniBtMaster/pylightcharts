"""v1.3.7-83：四个扩展页入口开放（菜单 / 命令面板 / PI）+ 文档口径。"""
from __future__ import annotations

import json
import pathlib

import pytest

from minibt.desk import tools as desk_tools
from minibt.desk import user_prefs

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'
APP = JSLIB / 'app.ts'
DOC = ROOT / 'minibt_docs' / 'docs' / 'minibt_desk' / '13.17_extensions.md'


@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    monkeypatch.setattr(desk_tools, 'AUDIT_FILE', str(tmp_path / 'a.jsonl'))
    user_prefs.set_setting('ai_desk_allow', True)
    from minibt.desk.app import Desk
    instance = Desk(offline=True)
    instance._booted = True
    instance.pushed = []
    instance.push = instance.pushed.append
    return instance


def test_no_commented_extension_entries_left():
    text = APP.read_text(encoding='utf-8')
    assert '扩展功能入口暂时关闭' not in text
    assert '/* 扩展功能入口' not in text


def test_menu_has_four_entries():
    text = APP.read_text(encoding='utf-8')
    for label in ('交易工作台（订单票 / 风控 / 审计）',
                  '策略研究（walk-forward / 实验库）',
                  '本地数据平台（质检 / 换月 / SQL）',
                  '平台 / 运维（Token / 告警 / 版本）'):
        assert f"label: '{label}'" in text, label
    # 都要真的调 openXxx（不是留着 label 没动作）
    for opener in ('openWorkbench()', 'openResearch()', 'openDataHub()',
                   'openOps()'):
        assert f'run: () => this.{opener}' in text, opener


def test_palette_has_four_entries_and_shortcuts():
    text = APP.read_text(encoding='utf-8')
    for label in ("{ label: '交易工作台', hint: '订单票 / 风控 / 审计'",
                  "{ label: '策略研究', hint: 'walk-forward / 实验库'",
                  "{ label: '数据平台', hint: '质检 / 换月 / SQL'",
                  "{ label: '平台 / 运维', hint: 'Token / 告警 / 版本'"):
        assert label in text, label
    assert "label: '工作台：对账'" in text
    assert "label: '工作台：导出审计 CSV'" in text
    # ★ v1.3.7-88：定时任务也独立成页，命令面板里能搜到 ✓
    assert "{ label: '定时任务', hint: '每 N 秒 / 每天 HH:MM / 前置任务'" in text


def test_open_ui_supports_new_pages(desk):
    for target in ('workbench', 'datahub', 'ops', 'info'):
        out = json.loads(desk_tools.call('desk_open_ui',
                                         {'target': target}, desk))
        assert out['ok'] is True and out['opened'] == target
    assert any((patch.get('target') == 'ops')
               for patch in desk.pushed if isinstance(patch, dict))


def test_frontend_open_ui_branches():
    text = APP.read_text(encoding='utf-8')
    for target in ('workbench', 'datahub', 'ops'):
        assert f"target === '{target}'" in text, target


def test_ops_page_keeps_scheduler_v2_form():
    """运维页的定时任务 v2 表单没被入口改动弄丢 ✓"""
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    for key in ('taskName', 'taskAction', 'taskTool', 'taskSteps',
                'taskPrompt', 'taskTrigger', 'taskAfter', 'taskRetries',
                'taskNotify', 'taskCatchUp', 'taskTemplate'):
        assert f'data-op="{key}"' in text, key


def test_doc_reflects_closed_entries():
    """v1.3.7-94：四个入口又关了，文档要如实说明（定时任务仍开放）✓"""
    text = DOC.read_text(encoding='utf-8')
    assert '再次注释关闭' in text
    assert '定时任务页仍开放' in text
    assert '定时任务 v2' in text


def test_ops_page_keeps_scheduler_v2_form():
    """运维页的定时任务 v2 表单没被入口改动弄丢 ✓"""
    text = (JSLIB / 'suite-pages.ts').read_text(encoding='utf-8')
    for key in ('taskName', 'taskAction', 'taskTool', 'taskSteps',
                'taskPrompt', 'taskTrigger', 'taskAfter', 'taskRetries',
                'taskNotify', 'taskCatchUp', 'taskTemplate'):
        assert f'data-op="{key}"' in text, key


def test_doc_keeps_scheduler_v2_details():
    """文档里定时任务 v2 的细节不能丢（入口关了，能力说明还在 ✓）"""
    text = DOC.read_text(encoding='utf-8')
    assert '定时任务 v2' in text
    assert '再次注释关闭' in text
    for word in ('after', 'sequence', '模板库', 'DAG', 'notify',
                 'catch_up', 'depends_on'):
        assert word in text, word

