"""LSP 服务要支持**多个编辑器同时连**（v1.3.9-28）。

用户实测 2026-11-18：
* 编辑器多开时，除第一个外其它编辑器状态栏都是「LSP 未启用」；
* 点「重启 LSP」后端日志显示已启动，但界面一直「启动中」，悬停/补全无效 ——
  感觉「LSP 服务不能多开」。

根因（后端 `minibt/desk/lsp.py`）：

* `self._connection` 只记**最后一条** WebSocket —— 第二个编辑器连上来就把第一个
  顶掉，回包也发到"最后那条"→ 第一个编辑器的请求永远等不到结果 ✗
* 诊断防抖定时器只按 `uri` 存 → 两条连接同开一个文件会互相取消 ✗

现在：连接用集合管理、每个连接各自收包回包，诊断定时器按 `(连接, uri)` 存。
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _open_ws(url: str) -> socket.socket:
    host, port = url.replace('ws://', '').split(':')
    sock = socket.create_connection((host, int(port)), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (f'GET / HTTP/1.1\r\nHost: {host}:{port}\r\n'
               'Upgrade: websocket\r\nConnection: Upgrade\r\n'
               f'Sec-WebSocket-Key: {key}\r\n'
               'Sec-WebSocket-Version: 13\r\n\r\n')
    sock.sendall(request.encode())
    assert b'101' in sock.recv(4096)
    return sock


def _send(sock: socket.socket, payload: dict) -> None:
    data = json.dumps(payload).encode()
    mask = os.urandom(4)
    head = bytes([0x81])
    if len(data) < 126:
        head += bytes([0x80 | len(data)])
    else:
        head += bytes([0x80 | 126]) + len(data).to_bytes(2, 'big')
    sock.sendall(head + mask + bytes(b ^ mask[i % 4]
                                     for i, b in enumerate(data)))


def _read(sock: socket.socket) -> dict:
    head = sock.recv(2)
    length = head[1] & 0x7f
    if length == 126:
        length = int.from_bytes(sock.recv(2), 'big')
    elif length == 127:
        length = int.from_bytes(sock.recv(8), 'big')
    data = b''
    while len(data) < length:
        data += sock.recv(length - len(data))
    return json.loads(data.decode('utf-8', 'replace'))


def test_two_editors_get_their_own_replies():
    sys.path.insert(0, str(ROOT))
    from minibt.desk import lsp as lsp_mod

    service = lsp_mod.LspService(root=str(ROOT / 'personal'),
                                 minibt_path=str(ROOT))
    try:
        info = service.start()
        assert info['status'] == 'ready', info
        url = info['url']
        first = _open_ws(url)
        second = _open_ws(url)
        _send(first, {'jsonrpc': '2.0', 'id': 1,
                      'method': 'initialize', 'params': {}})
        _send(second, {'jsonrpc': '2.0', 'id': 2,
                       'method': 'initialize', 'params': {}})
        assert _read(first)['id'] == 1
        assert _read(second)['id'] == 2
        # 两个编辑器都在服务里登记着（不是被顶掉 ✓）
        assert len(service._connections) == 2
    finally:
        service.stop()


def test_backend_tracks_every_connection():
    source = (ROOT / 'minibt' / 'desk' / 'lsp.py').read_text(encoding='utf-8')
    assert 'self._connections: set = set()' in source
    assert 'self._connections.add(conn)' in source
    assert 'self._connections.discard(conn)' in source
    # 诊断定时器按 (连接, 文档) 存（两条连接同开一个文件不会互相取消 ✓）
    assert 'self._diag_timers: dict[tuple, threading.Timer] = {}' in source
    assert 'key = (id(conn), uri)' in source
    # 只记最后一条连接的老写法必须消失
    assert 'self._connection = conn' not in source
