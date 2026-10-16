"""VS Code 扩展（``vscode-minibt/``）的一致性测试。

这里**不需要**装 VS Code：只检查「清单 / 扩展代码 / Python 运行器」三方一致
（命令、设置项、打包白名单），并在有 Node 的时候顺手校验 JS 语法和进度解析。

0.3.4 起只保留「在编辑器页运行策略图表」：静态快照导出 + MiniQT 结果面板
已删除；并且**不再占用「运行 ▾」（``editor/title/run``）**，免得把 VS Code
原生的运行按钮顶掉/报错。

0.3.5 把它做成编辑器标题栏的**快速按钮**：专属 K 线图标（深浅色 SVG）、
不再限制 ``editorLangId == python``，和 Pi Agent Studio 一样常驻在原生
「运行 ▾」按钮右边的同一行。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parents[1] / 'vscode-minibt'
MANIFEST = EXT / 'package.json'
EXTENSION_JS = EXT / 'extension.js'
RUNNER = EXT / 'runner' / 'vscode_runner.py'


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


# ------------------------------------------------------------------ 清单/代码
def test_only_run_in_editor_is_kept():
    """0.3.4 只保留「在编辑器页运行策略图表」；另两个功能已删除 ✓。"""
    manifest = _manifest()
    commands = {item['command']: item for item in
                manifest['contributes']['commands']}
    assert 'minibt.runInEditor' in commands
    assert '在编辑器页运行策略图表' in commands['minibt.runInEditor']['title']
    # 删掉的 3 个命令：静态快照导出 ×2 + MiniQT 结果面板
    for gone in ('minibt.exportHtmlInEditor', 'minibt.saveHtmlAs',
                 'minibt.backtestInMiniQT'):
        assert gone not in commands, f'{gone} 应该已删除'
    # 代码里也不能再注册它们
    source = EXTENSION_JS.read_text(encoding='utf-8')
    for gone in ('exportHtmlInEditor', 'saveHtmlAs', 'backtestInMiniQT',
                 'hostRpc', 'callHost', 'exportTo'):
        assert gone not in source, f'{gone} 应该已从 extension.js 删除'


def test_editor_run_button_is_a_quick_button():
    """不能占 ``editor/title/run``（会把 VS Code 原生运行按钮顶掉/报错 ✗）。

    0.3.5 改成编辑器标题栏的**快速按钮**：专属 K 线图标、常驻显示
    （不限制语言），和 Pi Agent Studio 一样排在原生「运行 ▾」右边的同一行。
    """
    menus = _manifest()['contributes']['menus']
    assert 'editor/title/run' not in menus
    title_commands = [item['command'] for item in menus['editor/title']]
    assert 'minibt.runInEditor' in title_commands
    entry = next(item for item in menus['editor/title']
                 if item['command'] == 'minibt.runInEditor')
    # 常驻快速按钮：不能再被语言 ``when`` 挡住（挡住就找不到了）
    assert not entry.get('when')
    # 图标是 MiniBT 专属的 K 线 SVG（深浅色两版），不是通用 codicon
    command = next(item for item in _manifest()['contributes']['commands']
                   if item['command'] == 'minibt.runInEditor')
    icon = command['icon']
    assert set(icon) == {'light', 'dark'}
    for key in ('light', 'dark'):
        assert (EXT / icon[key]).exists(), f'缺少图标 {icon[key]}'


def test_extension_folder_is_complete():
    for path in (MANIFEST, EXTENSION_JS, RUNNER, EXT / 'README.md',
                 EXT / 'PUBLISHING.md', EXT / 'LICENSE',
                 EXT / 'media' / 'icon.png',
                 EXT / 'media' / 'run-light.svg',
                 EXT / 'media' / 'run-dark.svg'):
        assert path.exists(), f'缺少 {path.relative_to(EXT)}'


def test_every_declared_command_is_registered():
    declared = {item['command'] for item in _manifest()['contributes']['commands']}
    registered = set(re.findall(r"registerCommand\('([\w.]+)'",
                                EXTENSION_JS.read_text(encoding='utf-8')))
    assert declared == registered


def test_every_setting_is_declared_and_used():
    keys = set(_manifest()['contributes']['configuration']['properties'])
    js = EXTENSION_JS.read_text(encoding='utf-8')
    # 只看 ``minibt`` 命名空间：``config`` 就是 ``getConfiguration('minibt')``，
    # 另有一处直接 ``getConfiguration('minibt').get(...)``。不能一把抓所有
    # ``get('...')`` —— 代码里还会读 ``getConfiguration('python')
    # .get('defaultInterpreterPath')``（那是 Python 扩展的设置、不是本扩展的）✗
    used = {'minibt.' + name for name in re.findall(r"config\.get\('(\w+)'", js)}
    used |= {'minibt.' + name for name in re.findall(
        r"getConfiguration\('minibt'\)\s*\.get\('(\w+)'", js)}
    assert used <= keys, f'代码里读了没声明的设置：{sorted(used - keys)}'
    assert keys <= used, f'声明了代码没用到的设置：{sorted(keys - used)}'


def test_chart_panel_enables_scripts():
    """图表页签必须 `enableScripts: true`。

    VS Code webview 的 sandbox 标志会被**子 iframe 继承**：关掉脚本后，iframe
    里的图表 JS（顶栏、K 线、bokeh 页面全是 JS 画的）全被拦掉，页面只剩黑色
    背景 —— 就是那个"能打开但一片漆黑"的 bug。这里守住它。
    """
    js = EXTENSION_JS.read_text(encoding='utf-8')
    assert 'enableScripts: true' in js
    assert 'enableScripts: false' not in js


def test_packaging_keeps_the_python_runner():
    """`.vscodeignore` 不能把 runner/ 排除掉（进了包扩展才能跑）。"""
    ignored = (EXT / '.vscodeignore').read_text(encoding='utf-8')
    lines = {line.strip() for line in ignored.splitlines()
             if line.strip() and not line.startswith('#')}
    assert 'runner' not in lines and 'runner/**' not in lines
    assert '**/runner/**' not in lines


def test_runner_compiles():
    import py_compile

    py_compile.compile(str(RUNNER), doraise=True)


def test_runner_declares_the_documented_cli():
    text = RUNNER.read_text(encoding='utf-8')
    for flag in ('--engine', '--port', '--cwd', '--open', '--theme'):
        assert f"'{flag}'" in text, f'运行器少了 {flag}'
    # 静态导出模式已删除（0.3.4 ✓）
    assert '--export-html' not in text
    assert "'auto'" in text and '_resolve_btplot_gui' in text
    for marker in ('MINIBT_URL=', 'MINIBT_HTML='):
        assert marker in text


# ----------------------------------------------------------------------- Node
def _node_available() -> bool:
    return shutil.which('node') is not None


@pytest.mark.skipif(not _node_available(), reason='没有 node')
def test_extension_syntax():
    result = subprocess.run(['node', '--check', str(EXTENSION_JS)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _extract_function(source: str, name: str) -> str:
    """按大括号配对，从 `extension.js` 里抠出一个函数（用于单独测逻辑）。"""
    start = source.index(f'function {name}(')
    index = source.index('{', start)
    depth = 0
    for position in range(index, len(source)):
        if source[position] == '{':
            depth += 1
        elif source[position] == '}':
            depth -= 1
            if depth == 0:
                return source[start:position + 1]
    raise AssertionError(f'找不到 {name} 的结尾')


@pytest.mark.skipif(not _node_available(), reason='没有 node')
def test_activate_registers_every_command(tmp_path):
    """用假的 `vscode` 模块跑一遍 activate，确认命令都注册上、不抛异常。"""
    manifest = _manifest()
    declared = sorted(item['command'] for item in manifest['contributes']['commands'])
    mock_dir = tmp_path / 'node_modules' / 'vscode'
    mock_dir.mkdir(parents=True)
    (mock_dir / 'index.js').write_text(MOCK_VSCODE, encoding='utf-8')
    (mock_dir / 'package.json').write_text(
        json.dumps({'name': 'vscode', 'version': '0.0.0', 'main': 'index.js'}),
        encoding='utf-8')
    shutil.copyfile(EXTENSION_JS, tmp_path / 'extension.js')
    shutil.copyfile(MANIFEST, tmp_path / 'package.json')   # 扩展会读它取版本号
    (tmp_path / 'run.js').write_text(
        chr(10).join([
            "const ext = require('./extension.js');",
            'const context = { subscriptions: [], extensionPath: __dirname };',
            'ext.activate(context);',
            'const registered = global.__registered__ || [];',
            'console.log(JSON.stringify(registered));',
            "if (context.subscriptions.length !== registered.length) {",
            "  console.error('订阅数对不上'); process.exit(1);",
            '}',
            'ext.deactivate();',
        ]), encoding='utf-8')
    result = subprocess.run(['node', str(tmp_path / 'run.js')],
                            capture_output=True, text=True, cwd=str(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    registered = json.loads(result.stdout.strip().splitlines()[-1])
    assert sorted(registered) == declared


MOCK_VSCODE = '''
const registered = [];
global.__registered__ = registered;
const disposable = () => ({ dispose() {} });
const webview = () => ({
  html: '',
  postMessage: async () => true,
  onDidReceiveMessage: () => disposable(),
  asWebviewUri: (uri) => uri,
  cspSource: 'vscode-webview://test',
});
module.exports = {
  commands: {
    registerCommand: (id) => { registered.push(id); return disposable(); },
    executeCommand: async () => undefined,
  },
  window: {
    activeTextEditor: undefined,
    createOutputChannel: () => Object.assign(disposable(), {
      append() {}, appendLine() {}, clear() {}, show() {},
    }),
    createWebviewPanel: () => Object.assign(disposable(), {
      webview: webview(), title: '', iconPath: null,
      reveal() {}, onDidDispose: () => disposable(),
    }),
    showOpenDialog: async () => undefined,
    showSaveDialog: async () => undefined,
    showInformationMessage() {}, showWarningMessage() {}, showErrorMessage() {},
  },
  workspace: {
    workspaceFolders: [{ uri: { fsPath: process.cwd() } }],
    getConfiguration: () => ({ get: (key, fallback) => fallback }),
  },
  ViewColumn: { Active: 1, Beside: -2 },
  ThemeIcon: class { constructor(id) { this.id = id; } },
  Uri: { file: (p) => ({ fsPath: p }), parse: (u) => ({ fsPath: u }) },
  env: { openExternal: async () => true },
};
'''


@pytest.mark.skipif(not _node_available(), reason='没有 node')
def test_progress_parser_reads_minibt_output(tmp_path):
    """进度解析要认得 bokeh 的「进度 x/y」、tqdm 的百分比、[i/n]。"""
    source = EXTENSION_JS.read_text(encoding='utf-8')
    cases = [
        ('  进度 3/10  ', 30.0, None),
        (' 37%|███ | 37/100 [00:01<00:02]', 37.0, None),
        ('[2/4] 回测中', 50.0, None),
        ('DCE.v2601 tick', None, None),
    ]
    lines = [_extract_function(source, 'parseProgress'), 'const cases = [']
    for text, percent, _ in cases:
        wanted = 'null' if percent is None else repr(percent)
        lines.append('  [%s, %s],' % (json.dumps(text), wanted))
    lines += [
        '];',
        "for (const [text, want] of cases) {",
        '  const got = parseProgress(text);',
        '  const value = got ? Math.round(got.percent * 100) / 100 : null;',
        "  if (value !== want) { console.error('失败:', text, value, want);"
        ' process.exit(1); }',
        '}',
        "console.log('ok');",
    ]
    script = tmp_path / 'progress.js'
    script.write_text(chr(10).join(lines), encoding='utf-8')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_engine_setting_defaults_to_auto():
    """默认 `auto`：跟随策略里写的 gui。"""
    props = _manifest()['contributes']['configuration']['properties']
    engine = props['minibt.engine']
    assert engine['default'] == 'auto'
    assert set(engine['enum']) == {'auto', 'pylightcharts', 'bokeh'}


def _runner_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location('vscode_runner_probe', RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gui_mapping_follows_the_strategy():
    """auto：`Gui.Bokeh` → bokeh；原生 / 网页版 / 没写 → pylightcharts 网页版。"""
    map_gui = _runner_module()._map_gui
    assert map_gui('bokeh', 'auto') == 'bokeh'
    assert map_gui('pylightcharts', 'auto') == 'pylightcharts_web'
    assert map_gui('pylightcharts_web', 'auto') == 'pylightcharts_web'
    assert map_gui(None, 'auto') == 'pylightcharts_web'
    # 显式指定引擎时覆盖策略里的写法
    assert map_gui('bokeh', 'pylightcharts') == 'pylightcharts_web'
    assert map_gui('pylightcharts', 'bokeh') == 'bokeh'

    class FakeGui:                      # 模拟 Gui.Bokeh（枚举）
        value = 'bokeh'

    assert map_gui(FakeGui, 'auto') == 'bokeh'


def test_btplot_gui_is_remapped_too(tmp_path):
    """btplot 的 gui 走同一条映射（子进程里跑，不污染本进程的 minibt）。"""
    pytest.importorskip('minibt')
    root = str(Path(__file__).resolve().parents[1])
    lines = [
        'import importlib.util, sys, threading',
        'spec = importlib.util.spec_from_file_location("vr", %r)' % str(RUNNER),
        'vr = importlib.util.module_from_spec(spec)',
        'spec.loader.exec_module(vr)',
        'sys.path.insert(0, %r)' % root,
        'vr._patch_minibt("auto", 0, "", {"done": threading.Event()})',
        'module = sys.modules["minibt.btplot"]',
        'print(module._resolve_btplot_gui("bokeh"),',
        '      module._resolve_btplot_gui("pylightcharts"),',
        '      module._resolve_btplot_gui(None))',
    ]
    script = tmp_path / 'probe.py'
    script.write_text(chr(10).join(lines), encoding='utf-8')
    env = dict(os.environ, PYTHONPATH=root)
    result = subprocess.run([sys.executable, str(script)], capture_output=True,
                            text=True, encoding='utf-8', errors='replace',
                            env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.split()[-3:] == ['bokeh', 'pylightcharts_web',
                                          'pylightcharts_web']


def test_library_theme_defaults_to_light():
    """非扩展：theme 没设置 → 浅色；显式指定则按用户的来（点 3）。"""
    pytest.importorskip('minibt')
    from minibt.utils import resolve_theme, theme_is_dark

    assert resolve_theme(None) == 'light'
    assert theme_is_dark(None) is False
    assert resolve_theme('dark') == 'dark'


def test_extension_theme_follows_vscode_when_unset():
    """扩展：theme=None 用 VS Code 主题；显式指定则原样（点 4）。"""
    pytest.importorskip('minibt')
    import minibt.utils as mu

    module = _runner_module()
    original = mu.resolve_theme
    try:
        module._patch_theme('dark')
        assert mu.resolve_theme(None) == 'dark'
        assert mu.resolve_theme('light') == 'light'
        assert mu.resolve_theme('dark') == 'dark'
        assert mu.resolve_theme(None, black_style=False) == 'light'
        assert mu.resolve_theme(None, black_style=True) == 'dark'
    finally:
        mu.resolve_theme = original           # 别污染其它测试


def test_bokeh_watcher_ignores_stale_temp_files(tmp_path):
    """上一次运行留下的 `minibt_bokeh_*.html` 不能被当成本次结果。"""
    import os
    import time

    module = _runner_module()
    old = tmp_path / 'minibt_bokeh_9999.html'
    old.write_text('x' * 9000, encoding='utf-8')
    new = tmp_path / 'minibt_bokeh_1234.html'
    new.write_text('y' * 9000, encoding='utf-8')
    then = time.time() - 5000
    os.utime(old, (then, then))
    os.utime(new, (time.time(), time.time()))
    module._RUN_SINCE = time.time() - 60
    assert module._find_bokeh_html(str(tmp_path)) == str(new)

