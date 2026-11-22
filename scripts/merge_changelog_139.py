"""把 `minibt_docs/docs/changelog.md` 顶部（旧 v1.3.10 + v1.3.9 + 散条）合并成**一个 v1.3.9** ✓

用法：

    py -3.12 scripts/merge_changelog_139.py            # 只看统计
    py -3.12 scripts/merge_changelog_139.py --write    # 写回 changelog.md

为什么需要它：1.3.10 的改动本来就是 1.3.9 的一部分（同一次发布周期），
发布 1.3.9 时要把两段合成一节、按主题分类，并把散落在最上面的补丁条目
（"最近打开""文档"等）归到对应分类里。
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / 'minibt_docs' / 'docs' / 'changelog.md'
NL = chr(10)

#: 分类（顺序 = 输出顺序）
CATEGORIES = [
    ('Python 3.13 / 3.14 支持与多版本打包',
     ['zigzag/core', 'cython_functions', 'signal_profit', 'pyproject',
      'requirements.txt', 'iteration-utilities', 'PEP 667', 'exec',
      '3.13', '3.14', 'check_dep_matrix', '轮子', '验收标准', '还没做',
      '实测结果', '已完成（P0']),
    ('指标库与指标',
     ['Rust', 'ferro', 'tulip', 'vta', 'vector', 'wickra', 'kand', 'pta_rs',
      'Alpha', '因子', 'ZigZag', 'MachineLearningRSI', '指标串线',
      '指标参数', '指标选择器', '主副图', '指标', '通道类']),
    ('交易系统（tradingsymtem）',
     ['交易系统', 'tradingsymtem', 'ts_', 'long_signal']),
    ('通达信本地数据接入',
     ['通达信']),
    ('desk 实时图表：同合约多页隔离',
     ['同合约多页', 'open_tab', '行情节拍器', 'kline', 'cell', 'pageId',
      '实时图表', '页签', '格 1', '多布局', '补丁']),
    ('desk 首页：自选分组 / 事件日历 / 最近打开',
     ['首页', '自选分组', '事件日历', '最近打开', 'openChart', '分组管理',
      'home_calendar', '自选']),
    ('desk 编辑器：LSP / 源码 / 临时文件另存',
     ['编辑器', 'LSP', '源码', '另存', '临时文件', '打开文件',
      '保存', '格式化']),
    ('desk 交易与账户（模拟 / 实盘 / 切账户）',
     ['账户', '实盘', '模拟账户', '持仓', '平仓', '挂单', '下单', '委托',
      '手数', '风控']),
    ('desk 回放 / 布局 / 信号 / 成交量分布',
     ['回放', '布局', '信号', '成交量分布', 'VP', '图例', '画线',
      '样式', '主题', '最大化', '悬停']),
    ('文档',
     ['文档', '13.', '升级须知', 'API', '教程', '索引', '锚点', '手册',
      '更新日志', 'README', 'notebook', '中文注释']),
    ('测试与工程',
     ['测试', 'pytest', 'vitest', '偏好文件', 'lint', 'CI', '脚本']),
]

BLOCK_RE = re.compile(r'^(#{3,4})\s+(.*)$')


#: 这些是"条目的内部小标题"，不是独立条目 → 并进上一条 ✓
SUB_HEADINGS = ('根因', '修法', '测试', '实测', '先说检测到的', '策略写法建议',
                '三个出图通道', '背景', '问题', '结论', '验证')


def _is_sub_heading(title: str) -> bool:
    text = re.sub(r'^[^0-9A-Za-z`一-鿿]+', '', title).strip()
    if any(text.startswith(word) for word in SUB_HEADINGS):
        return True
    # 很短、没有数字 / 反引号 / 冒号的 → 当作小标题 ✓
    return (len(text) <= 8 and not re.search(r'[0-9`：:]', text))


def parse_blocks(lines: list[str]) -> list[dict]:
    """按 `###` / `####` 切块（标题 + 正文）✓"""
    blocks: list[dict] = []
    current: dict | None = None
    for line in lines:
        match = BLOCK_RE.match(line)
        if match and current is not None and match.group(1) == '####'                 and _is_sub_heading(match.group(2)):
            # 小标题：把它变成上一节正文里的**加粗行** ✓
            current['body'].append('')
            current['body'].append(f"**{match.group(2).strip()}**")
            continue
        if match:
            if current:
                blocks.append(current)
            current = {'level': len(match.group(1)), 'title': match.group(2),
                       'body': []}
            continue
        if current is None:
            continue
        current['body'].append(line)
    if current:
        blocks.append(current)
    return blocks


DOC_CATEGORY = next(i for i, (name, _w) in enumerate(CATEGORIES)
                     if name == '文档')


def classify(block: dict) -> int:
    """按关键词打分归类（分最高者胜；同分取靠前的分类 ✓）"""
    clean = clean_title(block['title'])
    if clean.startswith('文档'):
        return DOC_CATEGORY
    if '交易系统' in clean:
        return 2                                  # 三、交易系统
    if '参数优化' in clean:
        return 6                                  # 七、desk 编辑器 / 策略
    if any(word in clean for word in ('逐点文本', 'bandstyle', '选择器')):
        return 1                                  # 二、指标库与指标
    if 'PtaRs' in clean:
        return 1                                  # 二、指标库与指标
    if '偏好文件' in clean:
        return 10                                 # 十一、测试与工程
    if '加到图表' in clean:
        return 4                                  # 五、desk 实时图表
    title = block['title']
    text = title + NL + NL.join(block['body'][:40])
    scores = []
    for index, (_name, words) in enumerate(CATEGORIES):
        score = 0
        for word in words:
            hit = 1 if word in text else 0     # ★ 每个关键词**只算一次**
            if hit and word in title:
                score += 3
            elif hit:
                score += 1
        scores.append((score, -index))
    best = max(scores)
    if best[0] <= 0:
        return len(CATEGORIES) - 1          # 兜底 → 测试与工程
    return -best[1]


#: 允许出现在标题开头的字符（数字 / 字母 / 中文 / 常见括号与反引号 ✓）
TITLE_HEAD = re.compile(r'[0-9A-Za-z_`一-鿿「『【（(\[]')


def clean_title(title: str) -> str:
    """去掉标题里的 emoji 前缀与结尾日期（分类里已经有日期了 ✓）"""
    match = TITLE_HEAD.search(title)
    text = title[match.start():] if match else title
    text = text.strip()
    text = re.sub(r'（[^）]*(20\d\d-\d\d-\d\d|同日第[^）]*|v1\.3\.\d[^）]*)）$', '',
                  text).strip()
    text = re.sub(r'\s*[（(]\s*20\d\d-\d\d-\d\d[^）)]*[）)]\s*$', '', text).strip()
    # 旧条目里的「八、追加：」「四、」这类序号 → 分类里已经有序号了 ✓
    text = re.sub(r'^[一二三四五六七八九十]+、\s*(追加：)?\s*', '', text).strip()
    return text or title.strip()


def main(argv: list[str]) -> int:
    write = '--write' in argv
    raw = DOC.read_text(encoding='utf-8')
    lines = raw.splitlines()

    # 分段：0) 前言 1) 待合并（到 `## [v1.3.8]` 之前）2) 其余保持原样
    start = next(i for i, line in enumerate(lines)
                 if line.startswith('### ') or line.startswith('## ['))
    tail_at = next(i for i, line in enumerate(lines)
                   if line.startswith('## [v1.3.8]'))
    preamble = lines[:start]
    merged = [line for line in lines[start:tail_at]
              if not line.startswith('## [v1.3.')]     # 去掉旧版本标题
    tail = lines[tail_at:]

    blocks = parse_blocks(merged)
    buckets: dict[int, list[dict]] = {}
    for block in blocks:
        buckets.setdefault(classify(block), []).append(block)

    out = list(preamble)
    out += ['## [v1.3.9] - 2026-11-22', '']
    out += [
        '> 本版是 **1.3.9 的大版本**：把原计划拆成 1.3.9 / 1.3.10 的两批改动',
        '> **合并成一次发布**（Python 3.12 / 3.13 / 3.14 三版本支持 + 指标库大扩充',
        '> + 交易系统 + 通达信本地数据 + desk 终端的一整轮修复）。',
        '> **Python 公共 API 零破坏**；配套前端 `pylightcharts 0.2.3`。',
        '',
        '| 主题 | 一句话 |',
        '| --- | --- |',
    ]
    summary = {
        'Python 3.13 / 3.14 支持与多版本打包':
            '3.13 / 3.14 各出一份 wheel；没编 Cython 也能跑（纯 Python 兜底，逐值一致）',
        '指标库与指标':
            '6 个 Rust 库（225+88+209+427+59+27）+ Alpha101/191 共 292 因子、PtaRs 27 个、ZigZag 等',
        '交易系统（tradingsymtem）':
            '只出信号不画线的「交易系统」体系：10 分类 / 31 系统 + desk 分组',
        '通达信本地数据接入':
            '策略与 desk 本地图表都能直接读 `.day` / `.lc5` / `.lc1`',
        'desk 实时图表：同合约多页隔离':
            '同合约多开互不继承策略 / 布局；补丁按页 + 按格精准路由（10 轮收尾）',
        'desk 首页：自选分组 / 事件日历 / 最近打开':
            '分组管理页、事件日历改资讯中心数据、最近打开按来源分流',
        'desk 编辑器：LSP / 源码 / 临时文件另存':
            'LSP 全页可用、工具栏「源码」按钮、临时文件 + 微信式另存',
        'desk 交易与账户（模拟 / 实盘 / 切账户）':
            '切账户 / 持仓 / 挂单 / 平仓全链路修好；本地账户右键市价成交',
        'desk 回放 / 布局 / 信号 / 成交量分布':
            '回放平仓、信号去重、布局悬停卡片、VP 图例与价格轴修复',
        '文档':
            '6 个 Rust 指标库 API 参考、更新日志改简单版为入口、升级须知',
        '测试与工程':
            '新增测试文件 + 全量回归基线（详见各条目）',
    }
    for index, (name, _words) in enumerate(CATEGORIES):
        out.append(f'| {name} | {summary.get(name, "")} |')
    out.append('')

    numbers = ('一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
               '十一', '十二')
    for index, (name, _words) in enumerate(CATEGORIES):
        items = buckets.get(index) or []
        if not items:
            continue
        out.append(f'### {numbers[index]}、{name}')
        out.append('')
        for block in items:
            title = clean_title(block['title'])
            # 旧版的分组标题（"一、已完成（P0）""二、兼容性问题"…）→ 分类里
            # 已经有一级分组了，这里不再重复一层 ✓
            if block['level'] == 3 and any(
                    word in title for word in ('已完成（P0', '兼容性问题',
                                                '实测结果')):
                # 旧 v1.3.10 文档里的**分组标题**（不是条目）→ 去掉标题、
                # 正文留下；其它「七、追加：…」都是真实条目，必须保留 ✓
                # 旧的分组标题：丢掉标题本身，但**正文要留下**
                # （否则"依赖轮子就绪度实测"的整张表就没了 ✗）
                body = [line for line in block['body']]
                while body and not body[0].strip():
                    body.pop(0)
                while body and not body[-1].strip():
                    body.pop()
                out.extend(body)
                out.append('')
                continue
            out.append(f'#### {title}')
            body = [line for line in block['body']]
            while body and not body[0].strip():
                body.pop(0)
            while body and not body[-1].strip():
                body.pop()
            out.extend(body)
            out.append('')
        out.append('')

    out += ['', *tail]
    text = NL.join(out).rstrip() + NL

    if write:
        DOC.write_text(text, encoding='utf-8')
        print(f'wrote {DOC}（{len(text.splitlines())} 行）')
    else:
        for index, (name, _words) in enumerate(CATEGORIES):
            print(f'{numbers[index]}、{name}: {len(buckets.get(index) or [])} 节')
        print('（--write 才会写回文件）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
