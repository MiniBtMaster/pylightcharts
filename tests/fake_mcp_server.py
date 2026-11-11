# coding: utf-8
"""测试用的最小 MCP server（stdio JSON-RPC 2.0）。

只实现三个方法，够验证 desk 的 MCP 客户端：

* `initialize` → 协议版本 + serverInfo
* `tools/list` → 一个 `echo` 工具
* `tools/call` → 返回 `echo:<text>`

被 `tests/test_minibt_desk_mcp.py` 用 `python tests/fake_mcp_server.py` 拉起。
"""
import json
import sys

TOOLS = [{'name': 'echo', 'description': '回声',
          'inputSchema': {'type': 'object',
                          'properties': {'text': {'type': 'string'}}}}]


def main() -> int:
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except ValueError:
            continue
        if not isinstance(message, dict) or 'id' not in message:
            continue                                   # 通知 → 不回包 ✓
        method = str(message.get('method') or '')
        if method == 'initialize':
            result = {'protocolVersion': '2024-11-05',
                      'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'fake', 'version': '0'}}
        elif method == 'tools/list':
            result = {'tools': TOOLS}
        elif method == 'tools/call':
            params = message.get('params') or {}
            args = params.get('arguments') or {}
            result = {'content': [{'type': 'text',
                                   'text': f"echo:{args.get('text') or ''}"}],
                      'isError': False}
        else:
            print(json.dumps({'jsonrpc': '2.0', 'id': message['id'],
                              'error': {'code': -32601,
                                        'message': 'nope'}}), flush=True)
            continue
        print(json.dumps({'jsonrpc': '2.0', 'id': message['id'],
                          'result': result}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
