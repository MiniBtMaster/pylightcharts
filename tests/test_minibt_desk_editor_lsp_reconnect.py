"""编辑器 LSP：晚到 / 重连后要能补连（v1.3.9-26）。

用户实测 2026-11-18：编辑器状态栏一直「LSP 未启用」，补全 / 悬停 / 跳转全哑。
根因：编辑器是在后端 `lsp` 补丁到达**之前**建的 → `spec.lsp` 为空，
之后不会自己重连 ✗

同时核对**后端**：jedi 的悬停 / 补全对 minibt 的类是好用的
（`Strategy` / `BtStop` 都能列出成员），所以前端连上就能用 ✓
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK = ROOT / 'jslib' / 'src' / 'desk'


def _read(name: str) -> str:
    return (DESK / name).read_text(encoding='utf-8')


def test_frontend_can_reattach_lsp():
    editor = _read('code-editor.ts')
    assert 'get hasLsp(): boolean {' in editor
    assert 'attachLsp(lsp: { url: string; root: string }, force = false)' in editor
    panel = _read('editor-panel.ts')
    assert 'refreshLsp(force = false): void {' in panel
    # 状态栏「重启 LSP」按钮（用户要求 2026-11-18）✓
    # 圆点按钮：未启用红点闪烁可点，已启用绿点不可点 ✓
    assert "restart.className = 'desk-editor-lsp-dot';" in panel
    assert "restart.textContent = '';" in panel
    assert "restart.title = '重启 LSP 服务';" in panel
    assert 'private _syncLspRestart(): void {' in panel
    assert "dot.dataset.level = ready ? 'ok' : 'off';" in panel
    # 绿点 = 编辑器**真的连上**（不是"后端有端口"）；重试用 `length` 判空 ✓
    assert 'const ready = this.lspConnected;' in panel
    assert 'if (this.lspRetried.length) return;' in panel
    assert 'restartLsp(): void {' in panel
    assert "this.options.onCommand('lsp_start', { restart: true });" in panel
    css = _read('desk.css')
    assert '.desk-editor-lsp-dot {' in css
    assert 'animation: desk-lsp-blink 1.1s ease-in-out infinite;' in css
    assert 'private _scheduleLspRetry(): void {' in panel
    # 打开文件时如果还没连上 → 退避重试 ✓
    assert 'if (!editor.hasLsp) this._scheduleLspRetry();' in panel
    app = _read('app.ts')
    assert 'refreshLsp?: (force?: boolean) => void;' in app
    # 切到某一页（重新打开实时图表 / 本地图表）→ 该页编辑器补连 ✓
    assert 'panel?.refreshLsp?.(true);' in app
    assert 'panel.refreshLsp?.(force);' in app


def test_backend_hover_and_completion_cover_minibt_classes():
    """jedi 能解析 `Strategy` / `BtStop` 的成员（前端连上就有补全 ✓）"""
    sys.path.insert(0, str(ROOT))
    import jedi

    from minibt.desk import lsp as lsp_mod

    engine = lsp_mod._LanguageEngine(root=str(ROOT / 'personal'),
                                     minibt_path=str(ROOT))
    code = ('from minibt import Strategy, BtStop\n\n'
            'class A(Strategy):\n'
            '    def on_init(self):\n'
            '        BtStop.\n')
    items = engine.completion(code, '', 4, 15)
    labels = {item['label'] for item in items}
    assert 'FixedStop' in labels or 'TrailingStopLoss' in labels, labels

    hover = engine.hover('from minibt import Strategy\n\nStrategy\n', '',
                         2, 3)
    text = ((hover or {}).get('contents') or {}).get('value', '')
    assert 'Strategy' in text and '量化' in text, text[:200]
    assert jedi is not None


def test_realtime_chart_page_passes_lsp():
    """实时图表页也必须把 LSP 传给编辑器 ✓

    用户实测 2026-11-18：LSP 只对**第一个**编辑器（启动时的本地图表）生效，
    实时图表页的编辑器全部「LSP 未启用」——因为 `chart-page.ts` 建
    `EditorPanel` 时**漏了** `lsp` 参数（本地图表页有）✗
    """
    chart = _read('chart-page.ts')
    assert 'lsp?: () => {' in chart                  # ChartPageOptions 里有
    assert 'lsp: () => this.options.lsp?.(),' in chart  # EditorPanel 拿到
    app = _read('app.ts')
    at = app.find('new ChartPage({')
    assert at > 0
    assert 'lsp: () => this.lspInfo || undefined,' in app[at:at + 1200]
