"""编辑器「手动指定 minibt 路径」设置 + 「加指标」成败提示（2026-10-31）

用户提的两件事：

1. 设置 → 个性化 → 编辑器 里加一项 **手动指定 minibt 路径**（默认**不启用**）：
   编辑器（jedi）自动识别不到 `minibt` 时，用这里填的路径来给悬停 / 补全找注释；
2. 个人指标加载失败却提示「已加到本地图表」（成功提示）—— 只有**真的加上图**
   才报成功，失败要报失败。
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

from minibt.desk import lsp

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSLIB = ROOT / 'jslib' / 'src' / 'desk'


# ------------------------------------------------------- 路径归一化 / sys.path
def test_normalize_minibt_path_accepts_repo_and_package_dir(tmp_path):
    repo = tmp_path / 'owen'
    (repo / 'minibt').mkdir(parents=True)
    (repo / 'minibt' / '__init__.py').write_text('', encoding='utf-8')
    assert lsp.normalize_minibt_path(str(repo)) == str(repo)
    assert lsp.normalize_minibt_path(str(repo / 'minibt')) == str(repo)
    assert lsp.normalize_minibt_path(f'"{repo}"') == str(repo)   # 带引号也认 ✓
    assert lsp.normalize_minibt_path('') == ''
    assert lsp.normalize_minibt_path('C:/definitely/not/here') == ''
    empty = tmp_path / 'empty'
    empty.mkdir()
    assert lsp.normalize_minibt_path(str(empty)) == ''           # 里面没有 minibt


def test_override_goes_first_in_sys_path(tmp_path):
    repo = tmp_path / 'custom_repo'
    (repo / 'minibt').mkdir(parents=True)
    (repo / 'minibt' / '__init__.py').write_text('', encoding='utf-8')
    paths = lsp.editor_sys_path(str(tmp_path), override=str(repo))
    assert paths[0] == str(repo), paths[:3]
    # 没填 / 填错 → 不影响默认顺序
    plain = lsp.editor_sys_path(str(tmp_path))
    assert lsp.editor_sys_path(str(tmp_path), override='') == plain
    assert lsp.editor_sys_path(str(tmp_path), override='C:/nope') == plain


def test_engine_and_service_expose_override(tmp_path):
    repo = tmp_path / 'owen'
    (repo / 'minibt').mkdir(parents=True)
    (repo / 'minibt' / '__init__.py').write_text('', encoding='utf-8')

    engine = lsp._LanguageEngine(str(tmp_path), minibt_path=str(repo))
    assert engine.minibt_override == str(repo)
    assert engine.sys_path[0] == str(repo)
    assert str(repo) in engine.environment.get_sys_path()

    service = lsp.LspService(root=str(tmp_path), minibt_path=str(repo))
    info = service.info()
    assert info['minibt_override'] == str(repo)
    # `minibt_path` 报的是**包目录**（tooltip 里的 `minibt → .../minibt` ✓）
    assert info['minibt_path'] == os.path.join(str(repo), 'minibt')
    # 关掉 → 回到自动识别
    info = service.set_minibt_path('')
    assert info['minibt_override'] == ''
    assert engine.minibt_override == str(repo)      # 另一个实例不受影响 ✓


def test_engine_hover_uses_the_custom_path(tmp_path):
    """真的用自定义路径解析：注释来自那份仓库 ✓"""
    repo = tmp_path / 'owen'
    (repo / 'minibt').mkdir(parents=True)
    source = '\n'.join([
        '"""自定义仓库的 minibt"""',
        '',
        '',
        'class Bt:',
        '    """## 自定义路径里的 Bt"""',
        '',
    ])
    (repo / 'minibt' / '__init__.py').write_text(source, encoding='utf-8')
    target = tmp_path / 'demo.py'
    target.write_text('from minibt import Bt\n', encoding='utf-8')

    engine = lsp._LanguageEngine(str(tmp_path), minibt_path=str(repo))
    hover = engine.hover(target.read_text(encoding='utf-8'), str(target), 0, 19)
    assert hover, '自定义路径下悬停为空'
    assert '自定义路径里的 Bt' in hover['contents']['value']


# --------------------------------------------------------------- 设置落盘
def _desk(tmp_path, monkeypatch):
    from minibt.desk import app as appmod, local_data, personal, user_prefs
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    # ★ 「个人指标目录」也要指向临时文件：以前测试会写进**用户的**
    #   `~/.minibt/desk_personal.json`（污染真实配置 ✗）
    monkeypatch.setattr(personal, 'CONFIG_FILE',
                        str(tmp_path / 'personal.json'))
    monkeypatch.setattr(local_data, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(local_data, 'FOLDERS_FILE',
                        str(tmp_path / 'folders.json'))
    desk = appmod.Desk(offline=True)
    desk.sent = []
    desk.sender = desk.sent.append
    desk._booted = True
    desk.log_to_stdout = False
    desk.log_to_ui = False
    return desk


def test_setting_whitelist_accepts_the_new_keys(tmp_path, monkeypatch):
    from minibt.desk import user_prefs
    monkeypatch.setattr(user_prefs, 'PREFS_FILE', str(tmp_path / 'p.json'))
    values = user_prefs.set_setting('editor_minibt_path_enabled', True)
    assert values['editor_minibt_path_enabled'] is True
    values = user_prefs.set_setting('editor_minibt_path', 'C:/x/owen')
    assert values['editor_minibt_path'] == 'C:/x/owen'


def test_desk_only_uses_path_when_enabled(tmp_path, monkeypatch):
    desk = _desk(tmp_path, monkeypatch)
    from minibt.desk import user_prefs
    user_prefs.set_setting('editor_minibt_path', 'C:/x/owen')
    assert desk._editor_minibt_path() == ''            # 默认不启用 ✓
    user_prefs.set_setting('editor_minibt_path_enabled', True)
    assert desk._editor_minibt_path() == 'C:/x/owen'


def test_set_setting_applies_to_running_lsp(tmp_path, monkeypatch):
    desk = _desk(tmp_path, monkeypatch)
    desk._on_lsp_start({})
    assert desk._lsp is not None
    repo = tmp_path / 'owen'
    (repo / 'minibt').mkdir(parents=True)
    (repo / 'minibt' / '__init__.py').write_text('', encoding='utf-8')
    # 先开启开关，再填路径（两步都会即时生效 ✓）
    desk._on_set_setting({'key': 'editor_minibt_path_enabled', 'value': True})
    desk._on_set_setting({'key': 'editor_minibt_path', 'value': str(repo)})
    assert desk._lsp.engine.minibt_override == str(repo)
    assert desk._lsp.engine.sys_path[0] == str(repo)
    # 关掉 → 取消 override
    desk._on_set_setting({'key': 'editor_minibt_path_enabled',
                          'value': False})
    assert desk._lsp.engine.minibt_override == ''


# ------------------------------------------------- 「加指标」成败提示
def _patches(desk):
    out = []
    for script in desk.sent:
        text = str(script)
        if text.startswith('window.__desk.applyPatch('):
            out.append(json.loads(text[len('window.__desk.applyPatch('):-2]))
    return out


_BROKEN_INDICATOR = '''
from minibt import BtIndicator


class test_indicator(BtIndicator):
    lines = ('open', 'high', 'low', 'close')

    def __init__(self):
        open, high, low, close = self.ha      # ← 忘了加括号（原样的坑）
        return open, high, low, close
'''


def test_local_add_indicator_reports_failure(tmp_path, monkeypatch):
    from minibt.desk import personal
    folder = tmp_path / 'my_indicators'
    folder.mkdir()
    (folder / 'test.py').write_text(_BROKEN_INDICATOR, encoding='utf-8')

    desk = _desk(tmp_path, monkeypatch)
    personal.add_directory(str(folder), kind='indicator')
    keys = [item['key'] for item in personal.scan('indicator')
            if str(item['key']).endswith('/test_indicator')]
    assert keys, [item['key'] for item in personal.scan('indicator')]
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})
    ok = desk._on_local_add_indicator({'symbol': 'test', 'key': keys[0],
                                      'cell': 0, 'page': 'local:1'})
    assert ok is False, '脚本报错却返回成功'
    patches = _patches(desk)
    toasts = [item for item in patches if item.get('type') == 'toast']
    assert toasts, patches
    assert any(item.get('level') in ('error', 'warning') for item in toasts)
    assert any('加不上图' in str(item.get('text') or '') for item in toasts)
    assert any('self.xxx()' in str(item.get('detail') or '')
               for item in toasts), toasts
    # 报错里带**写法提示**（self.xxx 是方法，要调用 self.xxx()）
    blob = json.dumps(patches, ensure_ascii=False)
    assert 'self.xxx()' in blob
    # 失败的不该留在页面的指标列表里
    assert desk._local_items('test', 0, 'local:1') == []


def test_local_add_indicator_reports_success(tmp_path, monkeypatch):
    desk = _desk(tmp_path, monkeypatch)
    desk._on_local_cells({'page': 'local:1', 'cells': ['test']})
    desk._on_local_load({'name': 'test', 'cell': 0, 'page': 'local:1'})
    ok = desk._on_local_add_indicator({'symbol': 'test', 'key': 'MA',
                                      'cell': 0, 'page': 'local:1'})
    assert ok is True
    keys = [item['key'] for item in desk._local_items('test', 0, 'local:1')]
    assert keys == ['MA']


_HA_INIT_RETURN = '''
from minibt import BtIndicator


class ha_bad(BtIndicator):
    lines = ('open', 'high', 'low', 'close')

    def __init__(self):
        open, high, low, close = self.ha()      # unpack 是 OK 的 ✓
        return open, high, low, close           # ← 但 __init__ 不能 return 值 ✗
'''

_HA_LINES = '''
from minibt import BtIndicator


class ha_lines(BtIndicator):
    lines = ('open', 'high', 'low', 'close')

    def __init__(self):
        ha = self.ha()
        self.lines.open = ha.open
        self.lines.high = ha.high
        self.lines.low = ha.low
        self.lines.close = ha.close
'''

_HA_NEXT = '''
from minibt import BtIndicator


class ha_next(BtIndicator):
    lines = ('open', 'high', 'low', 'close')

    def next(self):
        ha = self.ha()
        return (ha.open.values, ha.high.values,
                ha.low.values, ha.close.values)
'''


def _personal_items(tmp_path, monkeypatch, source: str, name: str):
    """把一段源码登记成个人指标，走 desk 的 compute 链路 ✓"""
    from minibt.desk import personal
    from minibt import LocalDatas
    folder = tmp_path / name
    folder.mkdir()
    (folder / f'{name}.py').write_text(source, encoding='utf-8')
    monkeypatch.setattr(personal, 'CONFIG_FILE',
                        str(tmp_path / f'{name}.json'))
    personal.add_directory(str(folder), kind='indicator')
    keys = [item['key'] for item in personal.scan('indicator')
            if str(item['key']).endswith(f'/{name}')]
    assert keys, [item['key'] for item in personal.scan('indicator')]
    frame = LocalDatas.test.kline.pandas_object
    errors: dict = {}
    items = personal.compute(frame, keys[0], errors=errors)
    return items, errors.get(keys[0], '')


def test_self_ha_unpacks_but_init_cannot_return(tmp_path, monkeypatch):
    """`self.ha()` 解包**没问题**；错在 `__init__` 里 `return` ✓

    用户 2026-10-31 追问：`open,high,low,close = self.ha()` 是能解包的，为什么
    还是加不上？—— 因为 minibt 的 `BtIndicator` 只认两种“出线”方式：
    `next()` 返回元组，或 `__init__` 里 `self.lines.<名字> = ...`（**不能 return**）。
    """
    items, error = _personal_items(tmp_path, monkeypatch,
                                   _HA_INIT_RETURN, 'ha_bad')
    assert items == []
    assert 'AssertionError' in error
    assert '返回数据格式' in error
    # 提示要直接说清“怎么改” ✓
    assert 'self.lines.' in error and 'next()' in error


def test_init_assigning_lines_works(tmp_path, monkeypatch):
    items, error = _personal_items(tmp_path, monkeypatch, _HA_LINES, 'ha_lines')
    assert error == ''
    assert items and items[0].get('kind') == 'candles'


def test_next_returning_four_columns_works(tmp_path, monkeypatch):
    items, error = _personal_items(tmp_path, monkeypatch, _HA_NEXT, 'ha_next')
    assert error == ''
    assert items and items[0].get('kind') == 'candles'


def test_editor_help_documents_the_two_line_styles():
    """编辑器「帮助」里写清「指标出线」的两种写法（少踩坑 ✓）"""
    from minibt.desk.app import Desk
    help_text = Desk.EDITOR_HELP
    assert '别在 __init__ 里 return' in help_text
    assert 'next() 返回元组' in help_text
    assert 'self.lines.open = ha.open' in help_text
    assert 'self.ha()' in help_text
    assert '返回数据格式须为' in help_text


def test_editor_add_indicator_only_reports_loaded_ones():
    """「编辑器 → 加到图表」只对**真的加上**的报成功（不再假 SUCCESS ✓）"""
    app = (ROOT / 'minibt' / 'desk' / 'app.py').read_text(encoding='utf-8')
    block = app.split('    def _on_editor_add_indicator', 1)[1]
    block = block.split('    def _clear_local_page_strategies', 1)[0]
    assert 'ok = self._on_local_add_indicator(' in block
    assert 'ok = self._on_add_indicator(' in block
    assert '(loaded if ok else failed).append' in block
    # 成功提示只在有 loaded 时出现 ✓
    assert block.count("if loaded:") >= 2
    assert '都没能加到本地图表' in block
    assert '都没能加到图表（原因见上面的报错）' in block


# ------------------------------------------------------------- 前端接线
def test_frontend_settings_rows_exist():
    page = (JSLIB / 'settings-page.ts').read_text(encoding='utf-8')
    for marker in ('editor_minibt_path_enabled', 'editor_minibt_path',
                   '_pathInput', 'desk-settings-input',
                   '手动指定 minibt 路径'):
        assert marker in page, marker
    panel = (JSLIB / 'editor-panel.ts').read_text(encoding='utf-8')
    assert 'minibt → ' in panel            # LSP 徽标 tooltip 显示解析到的路径 ✓


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))
