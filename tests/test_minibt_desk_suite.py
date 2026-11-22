"""扩展功能接入：命令表 / 前端页面 / 命令面板 / REST 入口。"""
from __future__ import annotations

import json
import pathlib

from minibt.desk.app import Desk

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding='utf-8')


def test_desk_commands_cover_suite():
    desk = Desk(offline=True)
    commands = desk.commands()
    for name in ('workbench', 'workbench_submit', 'workbench_cancel',
                 'workbench_modify', 'workbench_close_partial',
                 'workbench_limits', 'workbench_reconcile',
                 'workbench_export', 'research', 'research_start',
                 'research_cancel', 'research_report', 'datahub',
                 'datahub_quality', 'datahub_resample', 'datahub_roll',
                 'datahub_ticks', 'datahub_query', 'datahub_export',
                 'ops', 'ops_token_issue', 'ops_token_revoke',
                 'ops_task_add', 'ops_task_run', 'ops_notify_config',
                 'ops_notify_test', 'ops_version_snapshot',
                 'ops_version_rollback', 'ops_versions'):
        assert name in commands, name


def test_palette_shortcut_is_ctrl_p_not_ctrl_k():
    """命令面板 = `Ctrl/⌘ + P`；`Ctrl+K` 留给编辑器的 `Ctrl+K Ctrl+C` 注释 ✓

    两段式快捷键的第一段会被全局 keydown 截胡（编辑器里按注释弹命令面板 ✗）。
    """
    app = _read(JSLIB / 'app.ts')
    editor = _read(JSLIB / 'editor-bundle.ts')
    assert "event.key === 'p' || event.key === 'P'" in app
    assert "event.key === 'k' || event.key === 'K'" not in app
    # 编辑器注释快捷键保持 VS Code 同款 ✓
    assert "key: 'Mod-k Mod-c'" in editor
    assert "key: 'Ctrl-K Ctrl-C'" in editor
    # `Ctrl+P` 会触发浏览器打印对话框 → 必须 preventDefault ✓
    assert 'this.openPalette();' in app
    block = app.split("event.key === 'p' || event.key === 'P'", 1)[1]
    assert block.index('event.preventDefault();') < block.index('this.openPalette();')


def test_suite_pages_are_wired_into_app():
    app = _read(JSLIB / 'app.ts')
    pages = _read(JSLIB / 'suite-pages.ts')
    palette = _read(JSLIB / 'command-palette.ts')
    css = _read(JSLIB / 'desk.css')
    for name in ('WorkbenchPage', 'ResearchPage', 'DataPage', 'OpsPage'):
        assert f'export class {name}' in pages
        assert f'new {name}' in app
    for command in ('openWorkbench', 'openResearch', 'openDataHub', 'openOps',
                    'openPalette'):
        assert command in app
    assert 'Ctrl/⌘ + P' in palette or 'Ctrl/⌘ + P' in app
    for css_class in ('.desk-suite-page', '.desk-palette',
                      '.desk-suite-table'):
        assert css_class in css


def test_suite_page_patch_dispatch():
    app = _read(JSLIB / 'app.ts')
    for patch_type in ("case 'workbench'", "case 'research_result'",
                       "case 'datahub_quality'", "case 'ops_token'"):
        assert patch_type in app


def test_suite_pages_send_commands_not_dom_side_effects():
    pages = _read(JSLIB / 'suite-pages.ts')
    for command in ('workbench_submit', 'workbench_limits',
                    'workbench_reconcile', 'research_start',
                    'datahub_resample', 'datahub_query',
                    'ops_token_issue'):
        assert f"'{command}'" in pages, command
    # ★ v1.3.7-91：告警通道搬到设置页 → 这两个命令在那里发 ✓
    settings = _read(JSLIB / 'settings-page.ts')
    for command in ('ops_notify_config', 'ops_notify_test'):
        assert f"'{command}'" in settings, command
    for marker in ('metric0', 'metric1', 'metric2', 'rs-data-names',
                   'heatMetric', 'LocalDatas'):
        assert marker in pages, marker


def test_workbench_handlers_push_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv('MINIBT_DESK_AUDIT_DB', str(tmp_path / 'audit.db'))
    monkeypatch.setenv('MINIBT_DESK_WORKBENCH_CONFIG',
                       str(tmp_path / 'config.json'))
    desk = Desk(offline=True, allow_trading=False)
    desk._on_workbench({})
    desk._on_workbench_submit({'symbol': 'SHFE.ag2612', 'side': 'buy',
                               'volume': 1})
    types = []
    for script in desk._pending:
        try:
            types.append(json.loads(
                script[script.index('(') + 1:script.rindex(')')])['type'])
        except Exception:                                    # noqa: BLE001
            continue
    assert 'workbench' in types
    assert 'toast' in types


def test_research_datahub_ops_handlers_push(tmp_path, monkeypatch):
    monkeypatch.setenv('MINIBT_DESK_RESEARCH_DB', str(tmp_path / 'r.db'))
    monkeypatch.setenv('MINIBT_DESK_OPS_DIR', str(tmp_path / 'ops'))
    monkeypatch.setenv('MINIBT_DESK_DATAS', str(tmp_path / 'datas'))
    (tmp_path / 'datas').mkdir()
    desk = Desk(offline=True)
    desk._on_research({})
    desk._on_ops({})
    desk._on_datahub({})
    types = []
    for script in desk._pending:
        try:
            types.append(json.loads(
                script[script.index('(') + 1:script.rindex(')')])['type'])
        except Exception:                                    # noqa: BLE001
            continue
    assert {'research', 'ops', 'datahub'} <= set(types)


def test_web_rpc_is_token_guarded():
    source = _read(ROOT / 'minibt' / 'desk' / 'web.py')
    assert "path == '/api/rpc'" in source
    assert "path == '/ws'" in source
    assert '_api_token_ok' in source
    assert 'command not allowed' in source
    assert "path in ('/api/status', '/api/snapshot')" in source


def test_websocket_accept_matches_rfc6455():
    from minibt.desk.web import ws_accept
    assert ws_accept('dGhlIHNhbXBsZSBub25jZQ==') ==         's3pPLMBiTxaQ9kYGzzhZRbK+xOo='


def test_headless_module_exists():
    path = ROOT / 'minibt' / 'desk' / 'headless.py'
    assert path.is_file()
    source = _read(path)
    assert 'keep_alive=True' in source
    assert 'X-Desk-Token' in _read(ROOT / 'minibt' / 'desk' / 'web.py') \
        or 'X-Desk-Token' in source


def test_upgrade_guide_covers_1_3_7_and_1_3_8():
    """`13.33 升级须知` 必须在 nav 里，且两版的关键条款都在（2026-11-13）✓"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    doc = root / 'minibt_docs/docs/minibt_desk/manual/13.33_upgrade_1.3.7_1.3.8.md'
    text = doc.read_text(encoding='utf-8')
    # 版本对应 / 升级步骤 / 回执口径 三件事必须写清楚
    assert 'minibt==1.3.9' in text          # 当前版本
    assert '1.3.9' in text and '0.2.2' in text
    assert 'pylightcharts==0.2.2' in text
    assert 'minibt==1.3.9' in text
    assert '1.3.7' in text and '0.2.1' in text
    assert 'PENDING' in text and '不等于成交' in text
    assert 'need_login' in text
    assert 'confirm=true' in text
    assert 'ai_desk_order' in text
    # 指向细节页 / 变更日志的相对链接要真实存在
    nav = (root / 'minibt_docs/mkdocs.yml').read_text(encoding='utf-8')
    assert '13.33_upgrade_1.3.7_1.3.8.md' in nav
    assert (root / 'minibt_docs/docs/changelog.md').exists()
    assert (root / 'minibt_docs/docs/minibt_desk/manual/13.30_desk_command_tool_matrix.md'
            ).exists()


def test_vscode_extension_intro_doc_tracks_current_version():
    """`1.32 minibt-charts 扩展简介` 要跟上扩展当前版本（不能停在老版本）✓"""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    version = json.loads(
        (root / 'vscode-minibt/package.json').read_text(encoding='utf-8')
    )['version']
    doc = (root / 'minibt_docs/docs/minibt_basic/1.32minibt_charts_intro.md'
           ).read_text(encoding='utf-8')
    # 当前版本号必须出现在文档里（升版后忘了改文档 → 这里红 ✓）
    assert version in doc, f'文档没跟上扩展版本 {version}'
    # 0.3.12 的关键能力必须在文档里
    for token in ('Codelens', '@minibt', 'desk_vscode', 'minibt.desk.autoStart',
                  'minibt.mcp.toolSet', 'MCP 自检', 'PI 会话',
                  '在 desk 里打开这个 CSV', 'minibt.vscode.bridge',
                  '已移除'):
        assert token in doc, token
    # 依赖门槛要写清楚
    assert 'minibt ≥ 1.3.8' in doc and 'pylightcharts ≥ 0.2.1' in doc


def test_pi_manual_documents_vscode_usage():
    """13.29 手册要写清 VS Code 用法（`@minibt` 斜杠命令 + `desk_vscode`）✓"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    doc = (root / 'minibt_docs/docs/minibt_desk/manual/13.29_pi_mcp_usage.md'
           ).read_text(encoding='utf-8')
    # 用法从三种变四种，VS Code 单列一节
    assert '## 2. 四种用法' in doc
    assert '### 2.4 用法四：在 **VS Code** 里跟 PI 对话' in doc
    for token in ('@minibt', '/new', '/sessions', '/use', '/stop', '/model',
                  '/skills', '/status', '/desk'):
        assert token in doc, token
    # 反向通道：五个 action + 三个开关 + 桥文件
    assert '## 3.8 AI 操作 VS Code：`desk_vscode`' in doc
    for token in ('state', 'open', 'read', 'insert', 'run',
                  'minibt.vscode.bridge', 'minibt.vscode.allowWrite',
                  'minibt.vscode.allowRun', 'vscode_bridge.json',
                  'need_extension'):
        assert token in doc, token
    # 排错要覆盖「扩展没起」「minibt 太旧」
    assert 'minibt 太旧（需要 ≥ 1.3.8）' in doc
