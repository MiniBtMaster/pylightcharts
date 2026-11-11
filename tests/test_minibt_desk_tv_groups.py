"""「指标和策略」：用户自己的指标 / 策略分组 + 打开原文件（2026-11-02 ✓）

用户要求：
1. 从卡片进图表时，商品搜索框和本地图表一样有**内置 / 用户文件夹**的数据；
2. 指标代码存在哪（持久化 `~/.minibt/personal/indicators/<类名>.py`）；
3. 下拉框「全部分组」最后加「添加指标和策略」（选文件夹 → 分组名 = 文件夹名）
   和「删除指标和策略」（去掉分组，不动文件）；
   选分组后**递归**加载里面所有 .py（含子文件夹）+ 分页；
   用户文件展示代码时**不加** `# coding: utf-8` / `from minibt import BtIndicator`。
"""
from __future__ import annotations

import os
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK_TS = ROOT / 'jslib' / 'src' / 'desk'


def _read(path) -> str:
    return pathlib.Path(path).read_text(encoding='utf-8')


@pytest.fixture()
def tv(tmp_path, monkeypatch):
    from minibt.desk import tv_page as mod

    monkeypatch.setattr(mod, 'GROUPS_FILE', str(tmp_path / 'groups.json'))
    monkeypatch.setattr(mod, 'STATE_FILE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(mod, 'CARD_DIR', str(tmp_path / 'cards'))
    monkeypatch.setattr(mod, '_FRAME_CACHE', {'frame': None})
    return mod


@pytest.fixture()
def user_lib(tmp_path):
    root = tmp_path / '我的库'
    (root / 'sub').mkdir(parents=True)
    (root / 'Alpha.py').write_text(
        'from minibt import BtIndicator' + chr(10) * 3
        + 'class Alpha(BtIndicator):' + chr(10)
        + '    """alpha 指标"""' + chr(10)
        + '    def __init__(self):' + chr(10)
        + '        self.lines.ma = self.close.rolling(10).mean()' + chr(10),
        encoding='utf-8')
    (root / 'sub' / 'Beta.py').write_text(
        'from minibt import Strategy\n\n\nclass Beta(Strategy):\n'
        '    """beta 策略"""\n    def __init__(self):\n        pass\n',
        encoding='utf-8')
    (root / 'notes.txt').write_text('x', encoding='utf-8')
    return root


def test_add_and_remove_group(tv, user_lib):
    data = tv.add_group_payload({'path': str(user_lib)})
    assert data['ok'] is True
    assert data['name'] == '我的库'
    # 递归统计：Alpha.py + sub/Beta.py（.txt 不算 ✓）
    assert data['count'] == 2
    labels = [(row['label'], row['user'], row['key']) for row in data['groups']]
    assert labels[0][0] == 'TradingView'
    assert labels[0][1] is False and labels[0][2] == tv.BUILTIN_GROUP
    assert labels[1][:2] == ('我的库', True)
    # ★ 系统默认分组不能删 ✓
    refused = tv.remove_group_payload({'path': tv.BUILTIN_GROUP})
    assert refused['ok'] is False and '不能删除' in refused['reason']
    assert [row['label'] for row in refused['groups']][0] == 'TradingView'
    # 分组名可以自定义
    custom = tv.add_group_payload({'path': str(user_lib), 'name': '我的分组'})
    assert custom['name'] == '我的分组'
    # 删除：分组消失，文件还在 ✓
    removed = tv.remove_group_payload({'path': str(user_lib)})
    assert removed['ok'] is True
    assert [row['label'] for row in removed['groups']] == ['TradingView']
    # 用户分组删完 → 下拉框里仍有系统默认分组 ✓
    assert removed['groups'][0]['key'] == tv.BUILTIN_GROUP
    assert (user_lib / 'Alpha.py').is_file()
    # 不是文件夹 → 拒绝
    assert tv.add_group_payload({'path': str(user_lib / 'Alpha.py')})['ok'] is False


def test_list_user_group_recursive_and_paged(tv, user_lib):
    tv.add_group_payload({'path': str(user_lib)})
    path = tv.load_groups()[0]['path']
    data = tv.list_payload({'group': path})
    assert data['total'] == 2
    assert data['groupLabel'] == '我的库'
    names = {(row['name'], row['kind'], row['rel']) for row in data['items']}
    assert names == {('Alpha', 'indicator', 'Alpha.py'),
                     ('Beta', 'strategy', 'sub/Beta.py')}
    assert all(row['user'] is True and row['card'] == '' for row in data['items'])
    # 关键词过滤 ✓
    assert tv.list_payload({'group': path, 'query': 'beta'})['total'] == 1
    # 分页（size=1 → 2 页 ✓）
    first = tv.list_payload({'group': path, 'size': 1, 'page': 1})
    assert first['pages'] == 2 and len(first['items']) == 1
    # 收藏 tab 对用户文件也生效 ✓
    key = first['items'][0]['key']
    tv.star_payload({'key': key, 'on': True})
    assert tv.list_payload({'group': path, 'star': True})['total'] == 1
    # 未登记的分组 → 空（防止乱传路径 ✓）
    assert tv.list_payload({'group': str(user_lib / 'nope')})['total'] == 0


def test_all_groups_merges_builtin_and_user(tv, user_lib):
    """「全部分组」= TradingView + 用户文件夹（合并分页 ✓）"""
    tv.add_group_payload({'path': str(user_lib)})
    path = tv.load_groups()[0]['path']
    everything = tv.list_payload({'size': 100})
    assert everything['groupLabel'] == '全部分组'
    assert everything['total'] == len(tv.catalog()) + 2
    keys = {row['key'] for row in everything['items']}
    assert any(key.startswith('tv:') for key in keys)
    assert any(key.startswith('file:') for key in keys)
    # 单选 TradingView / 用户分组 ✓
    assert tv.list_payload({'group': tv.BUILTIN_GROUP,
                            'size': 100})['total'] == len(tv.catalog())
    assert tv.list_payload({'group': path})['total'] == 2
    # 收藏 tab 在「全部分组」里也生效 ✓
    assert tv.list_payload({'star': True})['total'] == 0


def test_user_file_copied_with_header_by_kind(tv, user_lib, tmp_path,
                                              monkeypatch):
    """用户文件 → 分类持久化副本 + 头部 + **只提取对应的类** ✓（需求 3 / 4）"""
    from minibt.desk import personal

    monkeypatch.setattr(personal, 'PERSONAL_ROOT',
                        str(tmp_path / 'personal'))
    monkeypatch.setattr(personal, 'CONFIG_FILE',
                        str(tmp_path / 'personal.json'))
    nl = chr(10)

    # 指标：文件里还有无关类 / __main__ / 其它 import
    src = user_lib / 'Alpha.py'
    src.write_text(nl.join([
        'import numpy as np',
        'from minibt import BtIndicator',
        '',
        '',
        'class Helper:',
        '    pass',
        '',
        '',
        'class Alpha(BtIndicator):',
        '    """alpha 指标"""',
        '    def __init__(self):',
        '        pass',
        '',
        '',
        'if __name__ == "__main__":',
        '    print("x")',
        '',
    ]), encoding='utf-8')
    data = tv.script_payload({'path': str(src)})
    assert data['ok'] is True and data['created'] is True
    assert data['kind'] == 'indicator'
    # 分类：指标 → personal/indicators ✓
    assert pathlib.Path(data['path']).parent == tmp_path / 'personal' / 'indicators'
    rows = data['text'].splitlines()
    assert rows[0] == '# coding: utf-8'
    assert rows[1] == 'from minibt import *'
    # 只留对应的类（Helper / __main__ 都不要 ✓），顶层 import 保留
    assert 'class Alpha' in data['text']
    assert 'class Helper' not in data['text']
    assert '__main__' not in data['text']
    assert 'import numpy as np' in data['text']
    import py_compile
    py_compile.compile(data['path'], doraise=True)
    # 持久化 + 可写：改完再打开还是改后的内容 ✓
    with open(data['path'], 'a', encoding='utf-8') as handle:
        handle.write('# my edit' + nl)
    again = tv.script_payload({'path': str(src)})
    assert again['created'] is False
    assert '# my edit' in again['text']

    # 策略：→ personal/strategies + `from minibt import Strategy` ✓
    beta = user_lib / 'sub' / 'Beta.py'
    strategy = tv.script_payload({'path': str(beta)})
    assert strategy['kind'] == 'strategy'
    assert pathlib.Path(strategy['path']).parent == tmp_path / 'personal' / 'strategies'
    assert strategy['text'].splitlines()[1] == 'from minibt import *'
    assert 'class Beta' in strategy['text']
    # 不存在的文件 → 报错
    assert tv.script_payload({'path': str(user_lib / 'nope.py')})['ok'] is False


def test_screenshot_overwrites_card_cover(tv, tmp_path):
    """工具栏「截图」→ 覆盖卡片封面（PNG 优先 ✓）"""
    key = tv.list_payload({'page': 1})['items'][0]['key']
    raw = bytes([137, 80, 78, 71]) + b'0' * 128
    saved = tv.save_card_png(key, raw)
    assert saved.endswith('.png') and os.path.isfile(saved)
    assert tv._existing_card(key) == saved
    assert tv.snapshot_data_url(key).startswith('data:image/png;base64,')
    # 列表里的卡片就能直接用这张图 ✓
    row = [item for item in tv.list_payload({'page': 1})['items']
           if item['key'] == key][0]
    assert row['card'] == saved
    # 「重新截图」（force）会把 png 也清掉，重新生成 SVG ✓
    tv.snapshot_payload({'key': key, 'force': True})
    assert not os.path.isfile(saved)
    assert tv._existing_card(key).endswith('.svg')


def test_star_only_in_groups_and_query(tv, user_lib):
    """收藏：跨分组显示，**只显示仍存在于分组里的**；打开页面可只读查询 ✓"""
    tv.star_payload({'key': 'tv:UT_Bot_Alerts', 'on': True})
    tv.add_group_payload({'path': str(user_lib)})
    path = tv.load_groups()[0]['path']
    user_key = tv.list_payload({'group': path})['items'][0]['key']
    tv.star_payload({'key': user_key, 'on': True})
    fav = tv.list_payload({'star': True, 'size': 100})
    assert fav['total'] == 2
    assert {row['key'] for row in fav['items']} == {'tv:UT_Bot_Alerts',
                                                    user_key}
    # 删掉分组 → 这个文件的收藏**不再显示**（需求 5 ✓）
    tv.remove_group_payload({'path': str(user_lib)})
    after = tv.list_payload({'star': True, 'size': 100})
    assert [row['key'] for row in after['items']] == ['tv:UT_Bot_Alerts']
    # 只读查询（图表页打开时同步 ⭐ 状态 ✓）
    queried = tv.star_payload({'key': 'tv:UT_Bot_Alerts', 'query': True})
    assert queried['on'] is True and tv.load_state()['stars']
    off = tv.star_payload({'key': 'tv:Nope', 'query': True})
    assert off['on'] is False


def test_page_size_is_24(tv):
    """一页 24 个卡片（最大化 3 行 × 8 ✓）"""
    assert tv.TV_PAGE_SIZE == 24
    first = tv.list_payload({'page': 1})
    assert len(first['items']) == 24
    assert first['pages'] == (first['total'] + 23) // 24


def test_card_cover_two_themes(tv):
    """截图按主题各存一套封面（浅色 / 深色 ✓）"""
    key = 'tv:UT_Bot_Alerts'
    raw = bytes([137, 80, 78, 71]) + b'0' * 64
    light = tv.save_card_png(key, raw, 'light')
    dark = tv.save_card_png(key, raw, 'dark')
    assert os.path.basename(light) == 'tv_UT_Bot_Alerts_light.png'
    assert os.path.basename(dark) == 'tv_UT_Bot_Alerts_dark.png'
    assert tv._existing_card(key, 'light') == light
    assert tv._existing_card(key, 'dark') == dark
    assert tv.snapshot_data_url(key, 'dark').startswith('data:image/png;base64,')


def test_star_button_only_on_tv_chart_pages():
    lc = _read(DESK_TS / 'local-chart-page.ts')
    # 只有 `tvKey` 的页面才把 ⭐ 按钮放进工具栏（本地图表没有 ✓ 需求 4）
    assert '...(options.tvKey ? [starButton] : []),' in lc
    assert 'setStarred(on: boolean)' in lc
    assert "'tv_star', { key, on }" in lc
    ts = _read(DESK_TS / 'app.ts')
    assert '_setTabStar(' in ts                     # 顶栏页签上的 ★ ✓
    assert "this.send('tv_star', { key, query: true });" in ts
    # 「在图表上使用」：列出所有打开的本地 / 实时图表 ✓
    assert 'const targets: Array<{' in ts
    assert '_tvApplyToPage(key, params, targetId)' in ts
    assert '（本地图表）' in ts and '（实时图表）' in ts
    page_ts = _read(DESK_TS / 'tv-page.ts')
    # 用户卡片也自动生成缩略图（不再只给 TradingView 的）✓
    assert 'for (const item of this.state.items) this._ensureCard(item.key);'         in page_ts
    assert 'data-tv-kind' in page_ts
    # 用户指标 / 策略打开时都自动加载到图表（策略走预览模式 ✓）
    assert "preview: kind === 'strategy'," in ts
    assert "'editor_add_indicator'," in ts
    css = _read(DESK_TS / 'desk.css')
    assert '.desk-tool-star' in css
    # 卡片大小保持原样（最大化时 8 列 × 3 行 = 24 ✓）
    assert 'minmax(280px, 1fr)' in css
    assert 'minmax(212px' not in css


def test_user_cards_get_thumbnail(tv, user_lib, tmp_path, monkeypatch):
    """用户自己的指标 / 策略卡片也**自动生成缩略图**（和 TradingView 一样 ✓）"""
    from minibt.desk import personal

    monkeypatch.setattr(personal, 'PERSONAL_ROOT', str(tmp_path / 'personal'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'personal.json'))
    tv.add_group_payload({'path': str(user_lib)})
    rows = tv.list_payload({'group': str(user_lib)})
    assert rows['total'] == 2
    assert all(row['card'] == '' for row in rows['items'])   # 还没生成 ✓
    for row in rows['items']:
        data = tv.snapshot_payload({'key': row['key'], 'theme': 'light'})
        assert data['ok'] is True
        assert data['dataUrl'].startswith('data:image/svg+xml;base64,')
        assert pathlib.Path(data['path']).is_file()
    # 生成后列表就带图了（不会每次重算 ✓）
    again = tv.list_payload({'group': str(user_lib)})
    assert all(row['card'] for row in again['items'])
    # 缩略图里能看出是「我的指标 / 我的策略」✓
    indicator = next(row for row in again['items'] if row['kind'] == 'indicator')
    svg = tv.thumbnail_svg(indicator['key'], 'light')
    assert '我的指标' in svg and svg.count('<line') > 50
    strategy = next(row for row in again['items'] if row['kind'] == 'strategy')
    svg2 = tv.thumbnail_svg(strategy['key'], 'light')
    assert '我的策略' in svg2


def test_user_indicator_computes_by_path(tv, user_lib):
    """用户指标按**文件路径**算线（缩略图要用 ✓）"""
    from minibt.desk import personal
    from minibt import LocalDatas

    frame = LocalDatas.test.kline.pandas_object.tail(200)
    path = str(user_lib / 'Alpha.py')
    items = personal.compute_path(frame, path)
    assert items, '算不出用户的指标线'
    assert any(row.get('kind') in ('line', 'hist') for row in items)
    # 不存在的文件 → 空列表（不抛异常 ✓）
    assert personal.compute_path(frame, str(user_lib / 'nope.py')) == []


def test_reload_regenerates_cards(tv):
    """「重载图表」：把当前页卡片的截图**重算**一遍（并写回磁盘 ✓）"""
    rows = tv.list_payload({'page': 1, 'size': 3})
    keys = [row['key'] for row in rows['items']]
    seen = []
    result = tv.reload_payload(
        {'page': 1, 'size': 3, 'theme': 'light'},
        progress=lambda key, url: seen.append((key, url)))
    assert result['ok'] is True
    assert result['total'] == 3 and result['done'] == 3
    assert result['failed'] == []
    assert [key for key, _ in seen] == keys
    assert all(url.startswith('data:image/') for _, url in seen)
    # 生成后列表里就带图 ✓
    again = tv.list_payload({'page': 1, 'size': 3})
    assert all(row['card'] for row in again['items'])


def test_user_params_count(tv, tmp_path):
    """用户指标 / 策略的参数个数 = 文件里 `params` 的元素个数 ✓（需求 1）"""
    nl = chr(10)

    def make(name: str, body: list) -> str:
        path = tmp_path / name
        path.write_text(nl.join(body) + nl, encoding='utf-8')
        return str(path)

    # ① `params = dict(...)`（tutorials/strategies/rsi.py 的写法）
    rsi = make('rsi.py', [
        'from minibt import Strategy',
        '', '',
        'class RSIStrategy(Strategy):',
        '    params = dict(RSI_PERIOD=6, OVERBOUGHT_THRESHOLD=65,',
        '                  OVERSOLD_THRESHOLD=35)',
    ])
    assert tv._params_count(rsi) == 3
    assert tv._file_kind(rsi) == 'strategy'
    # ② 字典字面量
    assert tv._params_count(make('a.py', [
        'class A:',
        '    params = {"x": 1, "y": 2}',
    ])) == 2
    # ③ 自定义类（关键字参数）
    assert tv._params_count(make('b.py', [
        'class B:',
        '    params = Params(fast=5, slow=20)',
    ])) == 2
    # ④ `self.params.X = ...`
    assert tv._params_count(make('c.py', [
        'class C:',
        '    def __init__(self):',
        '        self.params.a = 1',
        '        self.params.b = 2',
        '        self.params.a = 3',
    ])) == 2
    # ⑤ 没有 params → 0
    assert tv._params_count(make('d.py', ['class D:', '    pass'])) == 0
    # 语法错误也不炸 ✓
    assert tv._params_count(make('e.py', ['class E(', '  oops'])) == 0


def test_user_card_carries_params(tv, user_lib, tmp_path, monkeypatch):
    """列表里的用户卡片要带上参数个数 ✓"""
    from minibt.desk import personal

    monkeypatch.setattr(personal, 'PERSONAL_ROOT', str(tmp_path / 'personal'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'personal.json'))
    (user_lib / 'Alpha.py').write_text(
        'from minibt import BtIndicator' + chr(10) * 3
        + 'class Alpha(BtIndicator):' + chr(10)
        + '    params = dict(a=1, b=2, c=3)' + chr(10),
        encoding='utf-8')
    tv.add_group_payload({'path': str(user_lib)})
    rows = tv.list_payload({'group': str(user_lib)})
    alpha = [row for row in rows['items'] if row['name'] == 'Alpha'][0]
    assert alpha['params'] == 3


def test_reload_single_card_both_themes(tv):
    """卡片右键「重载图表」：单张重算，深 / 浅两套都生成 ✓"""
    key = tv.list_payload({'page': 1})['items'][0]['key']
    data = tv.reload_card_payload({'key': key})
    assert data['ok'] is True
    assert data['themes'] == ['dark', 'light']
    svg = os.path.join(tv.CARD_DIR, tv._safe_key(key) + '.svg')
    dark = os.path.join(tv.CARD_DIR, tv._safe_key(key) + '_dark.svg')
    assert os.path.isfile(svg) and os.path.isfile(dark)
    # 不存在的 key → 报错，不写盘 ✓
    assert tv.reload_card_payload({'key': ''})['ok'] is False


def test_card_context_menu_entries():
    page = _read(DESK_TS / 'tv-page.ts')
    assert "'contextmenu'" in page
    assert "'在图表上使用'" in page and "'重载图表'" in page
    assert 'submenu' in page and "showMenu(event.clientX, event.clientY" in page
    assert "onCommand('tv_card_reload'" in page
    ts = _read(DESK_TS / 'app.ts')
    assert "'tv_card_reload': self._on_tv_card_reload" in _read(
        ROOT / 'minibt' / 'desk' / 'app.py')
    assert "case 'tv_card_reload':" in ts
    # 指标和策略页的原生右键菜单也要拦 ✓（需求 3）
    assert "'.desk-tv',            // 指标和策略页" in ts


def test_reload_and_apply_menu_entries():
    app_py = _read(ROOT / 'minibt' / 'desk' / 'app.py')
    assert "'tv_reload': self._on_tv_reload" in app_py
    assert 'def _on_tv_reload(self, payload=None)' in app_py
    assert "threading.Thread(target=worker, name='tv-reload'" in app_py

    page = _read(DESK_TS / 'tv-page.ts')
    assert 'data-tv-reload' in page and '重载图表' in page
    assert "'tv_reload'" in page
    # 「在图表上使用」带上鼠标坐标 ✓
    assert 'x: event.clientX, y: event.clientY' in page
    ts = _read(DESK_TS / 'app.ts')
    assert 'showMenu(position.x, position.y, items as never);' in ts
    # 只列本地图表 / 实时图表（排除指标和策略打开的图表页 ✓）
    assert 'const isTvChart = !!((page as unknown as {' in ts
    assert 'if (isTvChart) continue;' in ts


def test_script_header_and_dependency_closure(tv, tmp_path, monkeypatch):
    """生成代码：头部 `from minibt import *` + 带上策略依赖的指标类 ✓"""
    from minibt.desk import personal

    monkeypatch.setattr(personal, 'PERSONAL_ROOT', str(tmp_path / 'personal'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'personal.json'))
    # 头部就是用户要求的两行 ✓
    assert tv.script_header().splitlines()[:2] == [
        '# coding: utf-8', 'from minibt import *']
    assert tv.script_header('strategy').splitlines()[:2] == [
        '# coding: utf-8', 'from minibt import *']

    nl = chr(10)
    source = tmp_path / 'cci.py'
    source.write_text(nl.join([
        'import os as _os',
        'import sys as _sys',
        'from minibt import *',
        'import numpy as np',
        '',
        '',
        'class CCI(BtIndicator):',
        '    params = dict(P=10)',
        '    def next(self):',
        '        return self.close.cci(self.params.P)',
        '',
        '',
        'class CCIStrategy(Strategy):',
        '    def __init__(self):',
        '        self.cci = CCI(self.get_kline(LocalDatas.test))',
        '',
    ]) + nl, encoding='utf-8')
    data = tv.script_payload({'path': str(source)})
    text = data['text']
    # ★ 依赖的指标类一起带上 ✓
    assert 'class CCIStrategy' in text and 'class CCI(' in text
    # 样板 import 去掉，真正用到的 numpy 保留 ✓
    assert 'import os as _os' not in text
    assert 'import sys as _sys' not in text
    assert 'import numpy as np' in text
    import py_compile
    py_compile.compile(data['path'], doraise=True)
    # 老模板（`from minibt import Strategy`）→ 打开时按新模板重建 ✓
    with open(data['path'], 'w', encoding='utf-8') as handle:
        handle.write(nl.join([
            '# coding: utf-8', 'from minibt import Strategy', '',
            '', 'class CCIStrategy(Strategy):', '    pass']) + nl)
    again = tv.script_payload({'path': str(source)})
    assert again['rebuilt'] is True
    assert again['text'].splitlines()[1] == 'from minibt import *'
    assert 'class CCI(' in again['text']


def test_tab_label_and_no_duplicate_open():
    ts = _read(DESK_TS / 'app.ts')
    # 标签写清「指标 / 策略」✓
    assert "const tag = kind === 'strategy' ? '策略' : '指标';" in ts
    assert 'label: `${tag} · ${label}`' in ts
    # 同一个指标已打开 → 直接跳过去，不重复开 ✓
    assert 'if (target?.options?.tvKey === key) {' in ts
    assert 'this.activate(openId);' in ts
    # 右键菜单第一项：打开指标 / 打开策略 ✓
    page = _read(DESK_TS / 'tv-page.ts')
    assert "cardKind === 'strategy' ? '打开策略' : '打开指标'" in page


def test_ensure_directories_fixes_wrong_kind(tv, tmp_path, monkeypatch):
    """默认目录登记错 kind（strategies 记成 indicator）要自动纠正 ✓

    否则 `scan('strategy')` 永远扫不到个人策略（菜单里没有、卡片也当指标）✗
    """
    from minibt.desk import personal

    monkeypatch.setattr(personal, 'PERSONAL_ROOT', str(tmp_path / 'personal'))
    config_file = tmp_path / 'personal.json'
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(config_file))
    strategies = tmp_path / 'personal' / 'strategies'
    strategies.mkdir(parents=True)
    config_file.write_text(__import__('json').dumps({'directories': [
        {'path': str(strategies), 'kind': 'indicator',
         'category': '我的策略'},
    ]}), encoding='utf-8')
    personal.ensure_directories()
    kinds = {os.path.basename(str(item['path'])): item['kind']
             for item in personal.load_config()['directories']}
    assert kinds.get('strategies') == 'strategy'
    assert kinds.get('indicators') == 'indicator'


def test_generated_script_imports_tv_helpers(tv, tmp_path, monkeypatch):
    """生成的脚本要能**独立 import**（`LineStyle` / `np` 这些名字）✓

    用户 2026-11-02 实测：`[desk-personal] 跳过 AdaptiveSupertrend.py：NameError`
    —— TradingView 指标的源码依赖 `minibt.indicators.tradingview` 命名空间里的
    `LineStyle` / `Plot` / `np` / `pd` …，生成的脚本只写了 `BtIndicator` 就
    `NameError` ✗
    """
    from minibt.desk import personal

    monkeypatch.setattr(personal, 'PERSONAL_ROOT', str(tmp_path / 'personal'))
    monkeypatch.setattr(personal, 'CONFIG_FILE', str(tmp_path / 'personal.json'))
    # 新头部用 `from minibt import *`（其中就有 np / LineStyle 这些 ✓）
    assert 'from minibt import *' in tv.script_header()
    assert 'from minibt import *' in tv.script_header('strategy')
    # 头部两行仍然是用户要求的样子（顺序不变 ✓）
    lines = tv.script_header().splitlines()
    assert lines[0] == '# coding: utf-8'
    assert lines[1] == 'from minibt import *'

    # 老文件（没有依赖导入）→ 打开时自动补一行、写回磁盘、能 import ✓
    old = tmp_path / 'Legacy.py'
    old.write_text(
        '# coding: utf-8' + chr(10) + 'from minibt import BtIndicator' + chr(10)
        + chr(10) + chr(10)
        + 'class Legacy(BtIndicator):' + chr(10)
        + '    def __init__(self):' + chr(10)
        + "        self.lines.ma = self.i(self.H.close, 10)" + chr(10),
        encoding='utf-8')
    fixed = tv._ensure_tv_import(old.read_text(encoding='utf-8'), str(old))
    # 老脚本补一行 `from minibt import *`（np / LineStyle 都在里面 ✓）
    assert 'from minibt import *' in fixed
    assert 'class Legacy' in fixed
    assert 'from minibt import *' in old.read_text(encoding='utf-8')
    # 用户自己的文件（没有我们的头部）**一个字都不改** ✓
    mine = tmp_path / 'Mine.py'
    mine.write_text('import os' + chr(10) + 'print(1)' + chr(10),
                    encoding='utf-8')
    before = mine.read_text(encoding='utf-8')
    assert tv._ensure_tv_import(before, str(mine)) == before
    assert mine.read_text(encoding='utf-8') == before


def test_backend_commands_and_frontend_entries():
    app = _read(ROOT / 'minibt' / 'desk' / 'app.py')
    for cmd in ('tv_group_add', 'tv_group_remove'):
        assert f"'{cmd}': self._on_{cmd}" in app, cmd
    assert 'def _on_tv_group_add(self, payload=None)' in app
    assert 'def _on_tv_group_remove(self, payload=None)' in app
    assert 'choose_directory' in app.split('def _on_tv_group_add', 1)[1][:800]

    page = _read(DESK_TS / 'tv-page.ts')
    assert "const GROUP_ADD = '__add__';" in page
    # TradingView 也要出现在下拉框里（系统默认分组，不能删 ✓）
    assert 'groups.filter((group) => group.key)' not in page
    assert "group.user ? '' : ' · 默认'" in page
    menu = page.split('private _removeGroupMenu', 1)[1][:400]
    assert 'group.user' in menu                # 删除菜单只列用户分组 ✓
    assert "const GROUP_REMOVE = '__remove__';" in page
    assert '＋ 添加指标和策略' in page and '－ 删除指标和策略' in page
    assert 'setGroups(' in page and '_removeGroupMenu(' in page
    assert 'is-file' in page and 'desk-tv-file-badge' in page

    ts = _read(DESK_TS / 'app.ts')
    # ★ 页签太多：滚轮横向滚动 + 新页签自动滚进可见区 ✓
    assert "this.tabStrip.addEventListener('wheel'" in ts
    assert "'_scrollTabIntoView'" not in ts and '_scrollTabIntoView(' in ts
    # ★ 指标页的「截图」把卡片 key 传下去（覆盖封面 ✓）
    assert 'tvKey: key,' in ts
    lc = _read(DESK_TS / 'local-chart-page.ts')
    assert 'tvKey?: string;' in lc
    assert "card_key: this.options.tvKey" in lc
    app_py = _read(ROOT / 'minibt' / 'desk' / 'app.py')
    assert "card_key = str(payload.get('card_key') or '')" in app_py
    assert '_tv.save_card_png(card_key, raw, theme)' in app_py
    # 进图表时同步本地数据列表（商品搜索框和本地图表一样 ✓）
    assert "this.send('local_list', {});" in ts
    # 用户文件：打开原文件 / 按文件加指标 ✓
    assert "this.send('tv_script', { page: id, path: key.slice('file:'.length) });" in ts
    assert "this.send('editor_add_indicator', {" in ts
    css = _read(DESK_TS / 'desk.css')
    assert '.desk-tv-card-img.is-file' in css


if __name__ == '__main__':      # pragma: no cover
    raise SystemExit(pytest.main([__file__, '-q']))
