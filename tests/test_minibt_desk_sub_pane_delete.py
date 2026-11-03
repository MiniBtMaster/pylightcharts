"""删副图不能把**另一个副图**一起删掉（2026-10-30 用户实测）✓

本地图表（实时图表同一套 `IndicatorLayer`）：格里有 2 个副图，用工具栏「🗑」
删掉第一个 → 另一个副图跟着消失 ✗

根因（前端 `jslib/src/desk/indicator.ts`）：LWC 在「pane 里最后一条序列被删掉」
时会**自己**把空 pane 收掉（`addPane(preserveEmptyPane=false)`），后面的副图
下标整体前移；代码随后又按**旧下标** `removePane()` → 删掉的其实是前移进来的
那个副图 ✗。现在：
* `PaneHandle` 记下 LWC 的 pane 对象（`chart.panes()` 的包装是缓存的，身份稳定）；
* `_paneIndex()` 每次都按身份重算实际下标；
* `_removePane()` 删序列前后比 `chart.panes().length`：**已经自动消失就跳过**
  `removePane()`；
* 删多个副图时按实际下标**从后往前**删。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'jslib' / 'src' / 'desk' / 'indicator.ts').read_text(
    encoding='utf-8')
TEST = (ROOT / 'jslib' / 'test' / 'sub-pane-visibility.test.ts').read_text(
    encoding='utf-8')


def test_remove_pane_detects_auto_dropped_pane():
    """删序列后 LWC 已经收掉空 pane → 不能再按旧下标 removePane ✓"""
    body = SRC.split('private _removePane(', 1)[1].split('private _paneIndex(')[0]
    assert 'const before = count();' in body
    # 关键：只在 pane 数**没变**时才 removePane ✓
    assert 'if (count() >= before) {' in body
    assert '?.removePane?.(index);' in body
    # 有 pane 对象就用实际下标重算，不再手动 -1 ✓
    assert 'if (other.pane) this._paneIndex(other);' in body


def test_pane_index_uses_live_position():
    """`_paneIndex()` 按 pane 对象在 `chart.panes()` 里的实际位置算 ✓"""
    body = SRC.split('private _paneIndex(', 1)[1].split('\n    }', 1)[0]
    assert 'chart.panes?.()?.indexOf(' in body
    assert 'handle.index = at;' in body
    # 加序列 / 设高度 / 取副图下标都走它 ✓
    assert 'add(definition, options, this._paneIndex(handle))' in SRC
    assert 'addCandle(definition, options, this._paneIndex(handle))' in SRC
    assert 'chart.panes()[this._paneIndex(handle)]' in SRC


def test_pane_removal_goes_back_to_front():
    """一次删多个副图：**从后往前**删（前面的下标不会影响后面 ✓）"""
    assert SRC.count('dropped.sort((left, right) => this._paneIndex(') == 1
    assert 'const targets = [...this.panes.entries()]' in SRC
    assert '.sort((left, right) => this._paneIndex(right[1])' in SRC


def test_vitest_covers_two_sub_panes():
    """vitest 里要有「删第一个副图 / 隐藏第一个副图 → 另一个还在」的用例 ✓"""
    assert 'deleting the first pane keeps the next pane alive' in TEST
    assert 'hiding one pane also keeps the next pane' in TEST
    assert 'autoDrop:' in TEST
