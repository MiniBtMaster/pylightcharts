"""编辑器：**任何打开过的文件都能保存**（用户 2026-10-31 实测）✓

截图里从仓库其它目录（`tradingview` 那一堆 `@tobtind` 源码）打开文件后点保存，
弹的是「保存失败：只能保存个人目录 / 当前资源管理器根目录内的文件」✗ ——
`personal.write_file()` 只放行「个人目录 / 已登记目录 / 资源管理器根目录」，
从别处打开的文件一律被拒。

现在：**只要在编辑器里打开过（`read_file` 成功）就能保存**（用户要求 ✓）；
写盘仍是「先打开、后保存」两步，HTTP / 命令不能凭空写任意路径 ✓。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


@pytest.fixture()
def outside(tmp_path):
    """模拟「仓库里某个目录下的源码文件」（不在个人目录 / 资源管理器根里）"""
    target = tmp_path / 'repo' / 'indicators' / 'tradingview_sample.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('x = 1\n', encoding='utf-8')
    return target


def test_save_any_opened_file(outside, tmp_path):
    from minibt.desk import personal as pi

    root = str(tmp_path / 'elsewhere')          # 完全不相干的资源管理器根 ✓
    # ① 没打开过 → 仍然拒绝（安全兜底 ✓）
    before = pi.write_file(str(outside), 'x = 2\n', root=root)
    assert not before.get('ok')
    assert '只能保存' in str(before.get('error'))

    # ② 打开（`read_file` 成功）→ 允许保存到**任意目录** ✓
    opened = pi.read_file(str(outside))
    assert opened.get('ok'), opened
    assert pi.is_opened(str(outside))
    after = pi.write_file(str(outside), 'x = 3\n', root=root)
    assert after.get('ok'), after
    assert outside.read_text(encoding='utf-8').strip() == 'x = 3'
    assert str(outside.resolve()) in [str(pathlib.Path(p).resolve())
                                      for p in pi.opened_files()]


def test_opened_list_is_lru_and_capped(tmp_path):
    from minibt.desk import personal as pi
    saved = list(pi._OPENED)
    try:
        pi._OPENED.clear()
        for index in range(pi._OPENED_MAX + 5):
            target = tmp_path / f'f{index}.py'
            target.write_text('x = 1\n', encoding='utf-8')
            pi.remember_opened(str(target))
        opened = pi.opened_files()
        assert len(opened) == pi._OPENED_MAX                 # 有上限 ✓
        assert str(tmp_path / 'f0.py') not in [
            str(pathlib.Path(item)) for item in opened]      # 最早的被淘汰 ✓
    finally:
        pi._OPENED.clear()
        for path in saved:
            pi._OPENED[path] = None


def test_save_uses_opened_whitelist():
    """源码护栏：`write_file` 先看「打开过」，再看 root ✓"""
    source = _read('minibt/desk/personal.py')
    assert 'def remember_opened(' in source
    assert 'def is_opened(' in source
    assert "remember_opened(real)                    # 打开过 → 允许保存 ✓" in source
    block = source.split('def write_file(', 1)[1].split('def delete_file(', 1)[0]
    assert 'if is_opened(real):' in block
    assert 'allowed = True' in block
    assert '只能保存个人目录 / 打开过的文件 /' in block
    # 编辑器保存不再说「个人源码」（现在能保存任何打开过的文件 ✓）
    app = _read('minibt/desk/app.py')
    assert "self.push_log(f'已保存：{result[\"path\"]}', 'success')" in app
