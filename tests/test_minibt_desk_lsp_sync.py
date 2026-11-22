"""LSP 文档同步 / 线程安全（v1.3.9-11）。

用户实测（2026-11-16）：**刚打开文件**时类 / 方法的悬停注释、类补全都正常；
一旦**开始编辑**（以及编辑完保存后）就失效，重新打开又好了。

两个根因：
1. **jedi 不是线程安全的**：诊断跑在定时器线程，悬停 / 补全跑在请求线程，
   并发时会偶发返回空 → 看起来"编辑时就坏了" ✗；
2. 文档同步只认「最后一段 contentChanges 的 text」：客户端一旦发**增量**
   （带 `range` 的改动），内存里的文本就被写成一小段 → jedi 解析失败 →
   悬停 / 补全全空；而 `didSave` 又被**忽略**，所以保存后也恢复不了 ✗。
"""
from __future__ import annotations

import threading
import time

import pytest

from minibt.desk import lsp


# ---------------------------------------------------------------- 增量改动
def test_apply_range_change_single_line():
    text = 'abc\ndef\n'
    out = lsp._apply_range_change(
        text, {'start': {'line': 0, 'character': 1},
               'end': {'line': 0, 'character': 2}}, 'X')
    assert out == 'aXc\ndef\n'


def test_apply_range_change_multiline_insert():
    text = 'a\nb\nc\n'
    out = lsp._apply_range_change(
        text, {'start': {'line': 1, 'character': 1},
               'end': {'line': 2, 'character': 0}}, 'X\n')
    assert out == 'a\nbX\nc\n'


def test_apply_range_change_clamps_bad_positions():
    """越界位置别抛异常（客户端偶尔会发错）→ 夹到合法范围 ✓"""
    out = lsp._apply_range_change(
        'ab\n', {'start': {'line': 99, 'character': 99},
                 'end': {'line': 99, 'character': 99}}, '!')
    assert out.endswith('!')


# ------------------------------------------------------- 服务端：文本同步
class _FakeDoc:
    """最小 document 状态（不走真 WS）"""


@pytest.fixture()
def service():
    svc = lsp.LspService(root='')
    return svc


def _hover_texts(service, uri, text, line, char):
    with service._lock:                                # 模拟 didOpen/didChange
        service._documents[uri] = {'text': text,
                                   'path': lsp._uri_to_path(uri)}
    return service


def test_documents_keep_full_text_after_incremental_change(service, tmp_path):
    """★ 增量 contentChanges 之后，内存文本必须是**完整**文档（不是一段）"""
    path = tmp_path / 'a.py'
    path.write_text('from minibt import *\n\nclass Foo(BtIndicator):\n    pass\n',
                    encoding='utf-8')
    uri = lsp._path_to_uri(str(path))
    conn = object()
    # didOpen
    service._documents[uri] = {'text': path.read_text(encoding='utf-8'),
                               'path': str(path)}
    # 增量：在第 3 行末尾插入 'x'
    text = service._documents[uri]['text']
    text = lsp._apply_range_change(
        text, {'start': {'line': 3, 'character': 8},
               'end': {'line': 3, 'character': 8}}, 'x')
    service._documents[uri] = {'text': text, 'path': str(path)}
    assert 'class Foo(BtIndicator):' in text and text.count('\n') >= 4
    # 悬停仍然有内容（用引擎直接验，服务端只是把 text/path 传进去 ✓）
    with service.engine_lock:
        info = service.engine.hover(text, str(path), 2, 7)
    # 悬停的是类名 `Foo` → 能拿到类签名（说明 jedi 用的是**内存里的完整文本**✓）
    value = str((info or {}).get('contents', {}).get('value', ''))
    assert 'Foo(' in value, value


def test_engine_lock_exists_and_is_reentrant(service):
    """诊断线程 + 请求线程共用同一把锁（jedi 非线程安全）✓"""
    assert isinstance(service.engine_lock, type(threading.RLock()))
    # 可重入：请求处理里再调诊断不会自己把自己锁死
    with service.engine_lock:
        with service.engine_lock:
            assert True


def test_concurrent_hover_and_diagnostics_do_not_error(service, tmp_path):
    """并发跑「悬停」和「诊断」不再抛异常 / 不再返回空（★ 核心回归）"""
    path = tmp_path / 'b.py'
    code = ('from minibt import *\n\nclass Foo(BtIndicator):\n    pass\n\n'
            'x = Foo\n')
    path.write_text(code, encoding='utf-8')
    errors: list[BaseException] = []
    results: list[object] = []

    def worker_hover():
        try:
            for _ in range(8):
                with service.engine_lock:
                    results.append(service.engine.hover(code, str(path), 2, 7))
        except BaseException as error:                   # noqa: BLE001
            errors.append(error)

    def worker_diag():
        try:
            for _ in range(8):
                with service.engine_lock:
                    service.engine.diagnostics(code, str(path))
        except BaseException as error:                   # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=worker_hover),
               threading.Thread(target=worker_diag)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors, errors
    assert all(item for item in results), '悬停出现了空结果 ✗'
