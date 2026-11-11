/**
 * EditorPanel —— 「代码」页签（资源管理器 + CodeMirror ✓）
 *
 * 结构（`tradingview/vscode资源管理器.png`）：
 *
 *   ┌ 工具栏：打开目录 / 新建▾ / 保存 / 语法检查 / 格式化 / 加到图表 / 删除 /
 *   │        刷新 / 刷新指标策略  … 打开的标签页                    ┐
 *   ├─────────────┬─────────────────────────────────────────────────┤
 *   │ 资源管理器   │ CodeMirror（Python 高亮，右键菜单 ✓）            │
 *   │ ▾ my_root    │                                                 │
 *   │   ▸ sub      │                                                 │
 *   │    a.py      │                                                 │
 *   └─────────────┴─────────────────────────────────────────────────┘
 *
 * 文件树是**真的文件系统**（`explorer_list`），不是「个人指标 / 策略」两栏；
 * 根目录可以用「打开目录」换，并存在 `settings.explorer_root` ✓
 */
import { CodeEditor } from './code-editor';
import { showMenuBelow, type MenuItem } from './menu';
import { SNIPPETS, indentSnippet } from './editor-snippets';
import { PiPanel, type PiSessionRow } from './pi-panel';
import { PiChat } from './pi-chat';
import { PiModelsDialog } from './pi-models';
import { PiSkillsDialog } from './pi-skills';
import { PiWelcome } from './pi-welcome';
import { shortPath as piShortPath } from './pi-util';
/** 反斜杠（`Ctrl + \` 分屏开关）；用 charCode 写，避免转义坑 ✓ */
const BACKSLASH = String.fromCharCode(92);

/** 没装 pi 时的统一提示（按钮 tooltip / toast 共用 ✓） */
const PI_INSTALL_HINT = '此功能需要安装 pi'
    + '（npm install -g @earendil-works/pi-coding-agent）';
import {
    ICON_COPY, ICON_ERASER, ICON_PENCIL, ICON_REFRESH, ICON_TRASH,
} from './icons';

export interface ExplorerItem {
    name: string;
    path: string;
    dir: boolean;
    py?: boolean;
    /** 文本类文件（md / txt / json…）：也能在编辑器里打开 ✓ */
    text?: boolean;
    size?: number;
    mtime?: number;
    editable?: boolean;
}

export interface ExplorerData {
    ok: boolean;
    root: string;
    path: string;
    parent?: string;
    items: ExplorerItem[];
    error?: string;
}

export interface EditorCheckResult {
    ok: boolean;
    line?: number;
    col?: number;
    error?: string;
    defines?: Array<{ kind: string; name: string }>;
}

export interface EditorPanelOptions {
    theme: 'light' | 'dark';
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string, actions?: unknown[],
               detail?: string, placement?: 'bottom' | 'top') => void;
    /** 本地图表：加到图表走 `local_add_indicator`（不带实时合约 ✓） */
    local?: boolean;
    /** 本地图表的 CSV 名（`local` 时用 ✓） */
    symbol?: () => string;
    /** 本地图表当前格号（多布局；`local` 时用 ✓） */
    cell?: () => number;
    /** 是否显示「策略实盘 / 停止实盘」（**实时图表**才有；本地图表隐藏 ✓） */
    allowLive?: boolean;
    /** `desk vX` / `pi vY`：初始化页右上角版本号（用户 2026-11-08 ✓） */
    version?: string;
    piVersion?: string;
    /** 策略回测 / 参数优化入口（只在本地图表提供 ✓） */
    onBacktest?: (path: string) => void;
    onOptimize?: (path: string) => void;
    /** LSP 服务地址（后端起好后 app 传进来；undefined = 还没起来 ✓） */
    lsp?: () => {
        url: string; root: string;
        minibtPath?: string; sysPathCount?: number;
    } | undefined;
    /** 初始值：保存时自动格式化（设置 → 编辑器 ✓） */
    formatOnSave?: boolean;
    /**
     * `desk`（默认）= 图表里的编辑器；`pi` = **PI 独立界面**
     * （同一套编辑器代码，只隐藏「加到图表 / 策略 / 帮助」等桌面专属功能 ✓）
     */
    variant?: 'desk' | 'pi';
    /** PI 独立界面：目录和资源管理器分开（`pi_root`）✓ */
    piRoot?: boolean;
    /** 初始目录（PI 页用上次记住的 `pi_root` ✓） */
    rootHint?: string;
}

/** 极简 Markdown → HTML（标题 / 粗斜体 / 行内码 / 代码块 / 列表 / 链接 / 分隔线 ✓） */
function renderMarkdown(source: string): string {
    const lines = String(source || '').replace(/\r\n?/g, '\n').split('\n');
    const out: string[] = [];
    let inCode = false;
    let listType = '';
    let inTable = false;
    let skipLines = 0;
    let cursor = 0;
    const inline = (text: string) => esc(text)
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
        .replace(/(^|[^*])\*([^*]+)\*/g, '$1<i>$2</i>')
        .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g,
                 '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    const closeList = () => {
        if (listType) {
            out.push(listType === 'ol' ? '</ol>' : '</ul>');
            listType = '';
        }
    };
    for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index];
        cursor = index;
        if (skipLines > 0) {           // 表格已整块输出 → 跳过后续行 ✓
            skipLines -= 1;
            continue;
        }
        if (line.trim().startsWith('```')) {
            if (inCode) {
                out.push('</code></pre>');
                inCode = false;
            } else {
                closeList();
                out.push('<pre><code>');
                inCode = true;
            }
            continue;
        }
        if (inCode) {
            out.push(`${esc(line)}\n`);
            continue;
        }
        const heading = /^(#{1,6})\s+(.*)$/.exec(line);
        if (heading) {
            closeList();
            const level = heading[1].length;
            out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
            continue;
        }
        if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
            closeList();
            out.push('<hr/>');
            continue;
        }
        const ordered = /^\s*\d+\.\s+(.*)$/.exec(line);
        const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
        if (ordered || bullet) {
            const want = ordered ? 'ol' : 'ul';
            if (listType !== want) {
                closeList();
                out.push(want === 'ol' ? '<ol>' : '<ul>');
                listType = want;
            }
            const text = (ordered || bullet || ['', ''])[1];
            out.push(`<li>${inline(text)}</li>`);
            continue;
        }
        if (!line.trim()) {
            closeList();
            out.push('');
            continue;
        }
        // ★ 表格（GFM）：`| a | b |` + `|---|---|` → `<table>`（用户实测
        //   md 预览里表格被当成普通段落 ✗）
        if (/^\s*\|.*\|\s*$/.test(line) && !inTable) {
            const rows: string[] = [];
            let index = lines.indexOf(line, cursor);
            const start = index < 0 ? 0 : index;
            for (let k = start; k < lines.length; k += 1) {
                if (!/^\s*\|.*\|\s*$/.test(lines[k])) break;
                rows.push(lines[k]);
            }
            const parsed = rows.map((row) => row.trim()
                .replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim()));
            const isDivider = (cells: string[]) => cells.every(
                (cell) => /^:?-{2,}:?$/.test(cell));
            if (parsed.length >= 2 && isDivider(parsed[1])) {
                closeList();
                const head = parsed[0].map((cell) => `<th>${inline(cell)}</th>`);
                const body = parsed.slice(2)
                    .filter((cells) => !isDivider(cells))
                    .map((cells) => '<tr>'
                        + cells.map((cell) => `<td>${inline(cell)}</td>`).join('')
                        + '</tr>');
                out.push('<table><thead><tr>' + head.join('') + '</tr></thead>'
                    + '<tbody>' + body.join('') + '</tbody></table>');
                skipLines = rows.length - 1;
                continue;
            }
        }
        out.push(`<p>${inline(line)}</p>`);
    }
    closeList();
    if (inCode) out.push('</code></pre>');
    return out.join('\n');
}

function esc(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch] || ch));
}

const STYLE_ID = 'desk-editor-style';

const CSS = `
/* ★ 2026-11-08：窗口缩放时整页不能横向溢出（以前 flex 项的 min-width:auto
   把编辑器顶到 1179px，右侧工具栏 / 对话导航 / 发送按钮全被挤到屏幕外）
   → 每一层都允许收缩（min-width: 0），内部各自滚动 */
.desk-editor { flex: 1 1 auto; display: flex; min-height: 0; min-width: 0;
    width: 100%; height: 100%; }
.desk-editor-side { flex: 0 0 220px; display: flex; flex-direction: column;
    min-height: 0; min-width: 0; overflow: hidden;
    border-right: 1px solid var(--desk-border); }
.desk-editor-sidehead { flex: 0 0 auto; display: flex; align-items: center;
    gap: 4px; padding: 4px 6px; font-size: 10.5px; letter-spacing: .4px;
    color: var(--desk-muted); border-bottom: 1px solid var(--desk-border); }
.desk-editor-sidehead .grow { flex: 1 1 auto; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; }
.desk-editor-tree { flex: 1 1 auto; overflow: auto; padding: 2px 0 8px; }
.desk-editor-node { display: flex; align-items: center; gap: 4px;
    padding: 3px 6px; font-size: 12px; cursor: pointer; user-select: none;
    white-space: nowrap; }
.desk-editor-node:hover { background: var(--desk-hover); }
.desk-editor-node.on { background: var(--desk-active);
    color: var(--desk-accent); }
/* 切换标签时在资源管理器里"定位"到该文件（短暂高亮 ✓） */
.desk-editor-node.reveal {
    background: var(--desk-active);
    box-shadow: inset 2px 0 0 var(--desk-accent);
}
.desk-editor-node .twist { width: 12px; flex: 0 0 auto; opacity: .7;
    font-size: 10px; }
.desk-editor-node .name { flex: 1 1 auto; overflow: hidden;
    text-overflow: ellipsis; }
.desk-editor-node .dirty { color: var(--desk-up); }
.desk-editor-node .ico { flex: 0 0 auto; opacity: .8; }
.desk-editor-main { flex: 1 1 auto; display: flex; flex-direction: column;
    min-width: 0; min-height: 0; }
.desk-editor-toolbar { flex: 0 0 auto; display: flex; align-items: center;
    gap: 4px; padding: 4px 8px; border-bottom: 1px solid var(--desk-border);
    background: var(--desk-panel); overflow-x: auto; min-width: 0;
    /* ★ 窄窗口下**自动换行**：右对齐的按钮（预览 / 分屏 / 片段…）不会被切掉 ✓ */
    flex-wrap: wrap; row-gap: 3px; }
.desk-editor-tabs { display: flex; align-items: center; gap: 2px;
    overflow-x: auto; flex: 1 1 auto; min-width: 0;
    /* ★ 文件多了不显示滚动条，但**鼠标滚轮**能横向翻（用户要求 ✓） */
    scrollbar-width: none; -ms-overflow-style: none; }
.desk-editor-tabs::-webkit-scrollbar { height: 0; width: 0; }
.desk-editor-tab { display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 12px;
    /* 未选中：灰底、无描边 ✓ */
    background: var(--desk-hover); color: var(--desk-muted);
    border: 1px solid transparent; white-space: nowrap; }
/* 选中：**主题色描边**（和未保存时「保存」按钮同款 ✓） */
.desk-editor-tab.on {
    background: var(--desk-active); color: var(--desk-accent);
    border-color: var(--desk-accent);
}
.desk-editor-tab .x { opacity: .6; }
.desk-editor-tab .x:hover { opacity: 1; }
.desk-editor-host { flex: 1 1 auto; min-height: 0; overflow: hidden;
    display: flex; }
.desk-editor-host > div { flex: 1 1 auto; min-height: 0; min-width: 0;
    display: flex; }
.desk-editor-host .cm-editor { height: 100%; flex: 1 1 auto; min-height: 0; }
/* 代码长了要能滚动（以前 overflow:hidden 把后面的代码剪掉了 ✗） */
.desk-editor-host .cm-scroller { overflow: auto; }

/* ------------------------------------------------------------------ 悬停提示
   对齐 VS Code：限定宽度 / 高度，**内容可滚动**（以前文档一长就超出
   底部面板被裁掉、还滚不动 ✗），等宽字体 + 更紧凑的标题。 */
.desk-editor-host .cm-tooltip {
    max-width: min(680px, 62vw);
    padding: 0;
    border: 1px solid var(--desk-border);
    border-radius: 6px;
    background: var(--desk-panel);
    box-shadow: 0 10px 28px rgba(0, 0, 0, .30);
    overflow: hidden;
    pointer-events: auto;
    z-index: 40;
}
.desk-editor-host .cm-tooltip-hover {
    max-height: min(420px, 52vh);
    overflow-y: auto;                 /* ★ 可以滚轮翻看完整文档 ✓ */
    overscroll-behavior: contain;
}
.desk-editor-host .cm-tooltip-hover::-webkit-scrollbar { width: 8px; }
.desk-editor-host .cm-tooltip-hover::-webkit-scrollbar-thumb {
    background: var(--desk-border); border-radius: 4px;
}
.desk-editor-host .cm-tooltip .documentation {
    padding: 8px 11px;
    max-width: 100%;
    color: var(--desk-text);
    font-family: Consolas, "Cascadia Mono", Menlo, monospace;
    font-size: 11.5px;
    line-height: 1.6;
    word-break: break-word;
}
.desk-editor-host .cm-tooltip .documentation p { margin: 4px 0; }
.desk-editor-host .cm-tooltip .documentation h1,
.desk-editor-host .cm-tooltip .documentation h2,
.desk-editor-host .cm-tooltip .documentation h3,
.desk-editor-host .cm-tooltip .documentation h4 {
    margin: 8px 0 4px; font-size: 12px; font-weight: 700;
}
.desk-editor-host .cm-tooltip .documentation ul,
.desk-editor-host .cm-tooltip .documentation ol {
    margin: 4px 0 4px 18px; padding: 0;
}
.desk-editor-host .cm-tooltip .documentation li { margin: 1px 0; }
.desk-editor-host .cm-tooltip .documentation pre {
    margin: 6px 0; padding: 7px 9px; border-radius: 5px;
    background: var(--desk-bg); border: 1px solid var(--desk-border);
    overflow-x: auto; font-size: 11px; line-height: 1.5;
}
.desk-editor-host .cm-tooltip .documentation code {
    padding: 0 3px; border-radius: 3px; background: var(--desk-hover);
    font-family: inherit; font-size: 11px;
}
.desk-editor-host .cm-tooltip .documentation pre code {
    background: transparent; padding: 0;
}
.desk-editor-host .cm-tooltip .documentation a { color: var(--desk-accent); }
.desk-editor-host .cm-tooltip .documentation hr {
    border: 0; border-top: 1px solid var(--desk-border); margin: 8px 0;
}
.desk-editor-host .cm-tooltip .documentation table {
    border-collapse: collapse; font-size: 11px;
}
.desk-editor-host .cm-tooltip .documentation th,
.desk-editor-host .cm-tooltip .documentation td {
    border: 1px solid var(--desk-border); padding: 2px 6px;
}
.desk-editor-status { flex: 0 0 auto; padding: 2px 8px; font-size: 11px;
    color: var(--desk-muted); border-top: 1px solid var(--desk-border);
    display: flex; gap: 12px; align-items: center; min-width: 0;
    /* ★ 窄窗口：状态栏文字自己省略，不把整页顶宽 ✓ */
    overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.desk-editor-status .err { color: var(--desk-up); }
/* 窄窗口：文字自己省略，右侧元信息 / LSP 徽标永远看得见 */
.desk-editor-status-text { flex: 0 1 auto; min-width: 0; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; }
.desk-editor-status .ok { color: var(--desk-down); }
.desk-editor-empty { color: var(--desk-muted); font-size: 11.5px;
    padding: 10px 12px; }
.desk-editor-btn { height: 22px; padding: 0 8px; border-radius: 4px;
    border: 1px solid var(--desk-border); background: transparent;
    color: var(--desk-text); font-size: 11.5px; cursor: pointer;
    display: inline-flex; align-items: center; gap: 3px; white-space: nowrap; }
.desk-editor-btn:hover { background: var(--desk-hover); }
.desk-editor-btn.on { border-color: var(--desk-accent); color: var(--desk-accent); }
.desk-editor-btn:disabled { opacity: .4; cursor: default; }
`;

interface OpenTab {
    path: string;
    name: string;
    kind: 'indicator' | 'strategy' | 'file';
    text: string;
    saved: string;
    editor: CodeEditor;
    button: HTMLButtonElement;
}

/** 找到 `params = dict(` 的**配对右括号**（支持嵌套 dict / tuple / 字符串）

以前用 `/params\s*=\s*dict\s*\([^)]*\)/`，遇到
`params = dict(fast=(5, 20), nested={'a': (1, 2)})` 会在第一个 `)` 截断，
把文件写坏 ✗。这里做括号配对 + 字符串/注释跳过。
*/
function replaceParamsDict(text: string, replacement: string): string | null {
    const match = /params\s*=\s*dict\s*\(/m.exec(text);
    if (!match) return null;
    let index = match.index + match[0].length;
    let depth = 1;
    let quote = '';
    let escaped = false;
    for (; index < text.length; index += 1) {
        const ch = text[index];
        if (quote) {
            if (escaped) { escaped = false; continue; }
            if (ch === '\\') { escaped = true; continue; }
            if (ch === quote) quote = '';
            continue;
        }
        if (ch === "'" || ch === '"') { quote = ch; continue; }
        if (ch === '#') {
            while (index < text.length && text[index] !== '\n') index += 1;
            continue;
        }
        if (ch === '(') depth += 1;
        else if (ch === ')') {
            depth -= 1;
            if (depth === 0) {
                return text.slice(0, match.index) + replacement
                    + text.slice(index + 1);
            }
        }
    }
    return null;
}

export class EditorPanel {
    readonly element: HTMLDivElement;
    private readonly sideHead: HTMLDivElement;
    private readonly tree: HTMLDivElement;
    private readonly tabs: HTMLDivElement;
    private readonly host: HTMLDivElement;
    private readonly status: HTMLDivElement;
    private readonly saveButton: HTMLButtonElement;
    private readonly checkButton: HTMLButtonElement;
    private readonly formatButton: HTMLButtonElement;
    private readonly addButton: HTMLButtonElement;
    private readonly overlayButton: HTMLButtonElement;
    private readonly manageButton: HTMLButtonElement;
    private readonly backtestButton: HTMLButtonElement;
    private readonly optimizeButton: HTMLButtonElement;
    private readonly refreshPersonalButton: HTMLButtonElement;
    private readonly options: EditorPanelOptions;
    private readonly open = new Map<string, OpenTab>();
    /** `path → 子项`（展开过的目录缓存 ✓） */
    private readonly children = new Map<string, ExplorerItem[]>();
    private readonly expanded = new Set<string>();
    /** 待「在资源管理器里定位」的文件（目录懒加载回来后再滚 ✓） */
    private pendingReveal = '';
    /** 大纲（文档符号）容器 ✓ */
    private readonly outline: HTMLDivElement;
    private readonly outlineHead: HTMLDivElement;
    /** Markdown 预览（只有 .md 才显示 ✓） */
    private previewPane: HTMLDivElement | null = null;
    private previewButton: HTMLButtonElement | null = null;
    private previewOn = false;
    /** 保存时自动格式化（设置里可开关 ✓） */
    private formatOnSave = false;
    /** 工作区符号搜索（跨文件 ✓） */
    private symbolButton: HTMLButtonElement | null = null;
    private symbolBox: HTMLDivElement | null = null;
    private symbolTimer: number | undefined;
    private previewTimer: number | undefined;
    /** 等待后端体检的「回测 / 参数优化」请求（id → 动作 ✓） */
    private readonly pendingStrategy = new Map<string,
        { path: string; mode: 'backtest' | 'optimize' }>();
    private liveButton: HTMLButtonElement | null = null;
    private stopLiveButton: HTMLButtonElement | null = null;
    private root = '';
    private activePath = '';
    private activeDir = '';
    private mounted = false;
    /** 「刷新指标策略」是否可用（当前目录 = 我的脚本 / 我的策略 ✓） */
    private personalKind: 'indicator' | 'strategy' | '' = '';

    // ---------------------------------------------------- v1.3.7 编辑器增强
    /** 分屏（左右两栏，各自一个文件 ✓） */
    private splitButton: HTMLButtonElement | null = null;
    private paneB: HTMLDivElement | null = null;
    private splitOn = false;
    private activePane = 0;
    private readonly panePath: [string, string] = ['', ''];
    /** 每个 pane 当前显示的**会话** id（和 panePath 互斥 ✓） */
    private readonly paneSession: [string, string] = ['', ''];
    /** 代码片段按钮 */
    private snippetButton: HTMLButtonElement | null = null;
    /** 右侧 dock（调试 / AI） */
    private dock: HTMLDivElement | null = null;
    private dockBody: HTMLDivElement | null = null;
    /** 断点：`路径 → [行号(0 基)]` */
    private readonly breakpoints = new Map<string, number[]>();
    /** 调试状态（后端 `debug_state` 补丁 ✓） */
    private debugState: Record<string, unknown> | null = null;
    /** 调试输出（启动 / print / 报错，最多留 500 行 ✓） */
    private debugOutput: string[] = [];
    /** 控制台面板（终端 / REPL 两个页签 ✓） */
    private consoleOn = false;
    private consoleRows: Record<string, HTMLDivElement> | null = null;
    private consoleTabs: Record<string, HTMLButtonElement> | null = null;
    /** 终端是否跟随最新输出（用户往上翻时暂停 ✓） */
    private terminalPinned = true;
    /** 终端 / REPL 历史（↑↓ 翻，对齐 shell ✓） */
    private readonly terminalHistory: string[] = [];
    private terminalHistoryAt = -1;
    private readonly replHistory: string[] = [];
    private replHistoryAt = -1;
    private consoleTab: 'terminal' | 'repl' = 'terminal';
    /** 控制台高度（拖动上沿可改，用户 2026-11-08 要求 ✓） */
    private consoleHeight = 220;
    /** 「发给 AI → 新建会话」时暂存的待插入文本（等 `pi_session` 回来 ✓） */
    private pendingAi = '';
    /** 文件没打开时：先让后端读（`editor_file` 回来再发 ✓） */
    private pendingAiRead: { target: string; path: string } | null = null;
    /** 终端当前目录（`cd` 后提示符跟着变 → 不会再搞不清在哪 ✓） */
    private terminalCwd = '';
    private terminalPromptEl: HTMLSpanElement | null = null;
    private consolePane: HTMLDivElement | null = null;
    private terminalOutput: HTMLDivElement | null = null;
    private terminalInput: HTMLInputElement | null = null;
    private replOutput: HTMLDivElement | null = null;
    private replInput: HTMLInputElement | null = null;
    /** 编辑器字号（跟 desk 缩放联动 ✓） */
    private fontPx = 12.5;
    /** `beforeunload` 只绑一次 ✓ */
    private unloadBound = false;
    /** 上次上报给后端的「未保存文件名」（变了才发，避免刷屏 ✓） */
    private reportedDirty = '';
    // -------------------------------------------------- v1.3.7-9：PI 助手
    /** 左栏是否切到「PI 会话」（再点一次回资源管理器 ✓） */
    private piOpen = false;
    private piButton: HTMLButtonElement | null = null;
    private piPanel: PiPanel | null = null;
    private piModels: PiModelsDialog | null = null;
    private piSkills: PiSkillsDialog | null = null;
    /** 打开的 PI 会话标签：`id → {name, button, chat, messages}` */
    private readonly piTabs = new Map<string, {
        id: string;
        name: string;
        button: HTMLButtonElement;
        chat: PiChat;
    }>();
    private activePi = '';
    private piRows: PiSessionRow[] = [];
    /** 最近一次 `pi_models` / `pi_skills` 补丁（对话框后开也能立刻显示 ✓） */
    private piModelsPatch: Record<string, unknown> | null = null;
    private piSkillsPatch: Record<string, unknown> | null = null;
    private piStatusPatch: Record<string, unknown> | null = null;
    /** `pi` 装了没（`null` = 还不知道 → 先按可用处理 ✓） */
    private piInstalled: boolean | null = null;
    /** 后端没响应 PI 命令（1.5s 超时）✓ */
    private piOffline = false;
    /** 是不是「PI 独立界面」（同一个编辑器，隐藏桌面版专属功能 ✓） */
    private readonly piOnly: boolean;
    /** 初始化页（独立界面的首页；不是页签 ✓） */
    private welcome: PiWelcome | null = null;
    /** 初始化页发送后、等新会话建好再发这句话 ✓ */
    private pendingPiSend = '';
    private side: HTMLDivElement | null = null;

    constructor(options: EditorPanelOptions) {
        this.options = options;
        this.piOnly = options.variant === 'pi';
        this.formatOnSave = !!options.formatOnSave;
        this._ensureStyle();
        this.element = document.createElement('div');
        this.element.className = 'desk-editor';
        this.element.style.position = 'relative';

        // ---- 左侧资源管理器 ---------------------------------------------
        const side = document.createElement('div');
        this.side = side;
        side.className = 'desk-editor-side';
        // PI 会话面板（懒创建，和文件树互换显示 ✓）
        this.sideHead = document.createElement('div');
        this.sideHead.className = 'desk-editor-sidehead';
        this.tree = document.createElement('div');
        this.tree.className = 'desk-editor-tree';
        // ★ 大纲（文档符号）：只有 .py 才有（jedi 的 documentSymbol ✓）
        this.outlineHead = document.createElement('div');
        this.outlineHead.className = 'desk-editor-sidehead desk-editor-outline-head';
        this.outlineHead.textContent = '大纲';
        this.outline = document.createElement('div');
        this.outline.className = 'desk-editor-outline';
        // 大纲点击 → 跳到对应行 ✓
        this.symbolBox?.addEventListener('click', (event) => {
            const item = (event.target as HTMLElement).closest<HTMLElement>(
                '[data-symbol-path]');
            if (!item) return;
            const target = String(item.dataset.symbolPath || '');
            const line = Number(item.dataset.symbolLine || 0);
            if (this.symbolBox) this.symbolBox.style.display = 'none';
            this.options.onCommand('editor_open', { path: target });
            // 等文件打开 + 编辑器挂载后再跳行 ✓
            window.setTimeout(() => {
                const tab = this.open.get(target);
                const handle = tab?.editor.handle as unknown as {
                    jumpToLine?: (value: number) => void;
                } | null;
                handle?.jumpToLine?.(line);
            }, 900);
        });
        this.outline.addEventListener('click', (event) => {
            const item = (event.target as HTMLElement).closest<HTMLElement>(
                '[data-outline-line]');
            if (!item) return;
            const current = this.open.get(this.activePath);
            const handle = current?.editor.handle as unknown as {
                jumpToLine?: (line: number) => void;
            } | null;
            handle?.jumpToLine?.(Number(item.dataset.outlineLine || 0));
        });
        side.append(this.sideHead, this.tree, this.outlineHead, this.outline);

        // ---- 右侧编辑区 -------------------------------------------------
        const main = document.createElement('div');
        main.className = 'desk-editor-main';
        const toolbar = document.createElement('div');
        toolbar.className = 'desk-editor-toolbar';
        // ① 「系统目录 ▾」放最左边：系统个人指标 / 系统个人策略（用户要求 ✓）
        const folderButton = this._button('系统目录 ▾', (button) => {
            showMenuBelow(button, [
                // ★ 第一项：整个 personal 根目录（indicators + strategies 都在里面 ✓）
                { label: '系统指标和策略（personal）',
                  run: () => this.options.onCommand(
                      'explorer_system_dir', { kind: 'all' }) },
                { label: '系统个人指标（personal/indicators）',
                  run: () => this.options.onCommand(
                      'explorer_system_dir', { kind: 'indicator' }) },
                { label: '系统个人策略（personal/strategies）',
                  run: () => this.options.onCommand(
                      'explorer_system_dir', { kind: 'strategy' }) },
                { label: '', separator: true },
                { label: '其它目录…', run: () => this.options.onCommand(
                    'explorer_pick', this._piFlag()) },
            ]);
        });
        const newButton = this._button('新建 ▾', (button) => {
            showMenuBelow(button, [
                { label: '新建文件…', run: () => this._newEntry('new_file') },
                { label: '新建文件夹…', run: () => this._newEntry('new_folder') },
                { label: '指标模板（BtIndicator）', separator: true,
                  run: () => this._newPersonal('indicator') },
                { label: '策略模板（Strategy）',
                  run: () => this._newPersonal('strategy') },
            ]);
        });
        this.saveButton = this._button('保存', () => this._save());
        this.saveButton.innerHTML = `${ICON_PENCIL}<span>保存</span>`;
        this.checkButton = this._button('语法检查', () => this._check());
        this.formatButton = this._button('格式化', () => this._format());
        this.addButton = this._button('加到图表', () => this._addToChart());
        // ★ 只读叠加：策略只画线、不跑 next / 不交易（本地图表可叠多个 ✓）
        this.overlayButton = this._button('只读叠加', () => this._addToChart(
            undefined, true));
        this.overlayButton.title =
            '把当前策略以**只读**方式叠加到图上（只算指标线，不交易）';
        // ★ 「策略管理」紧跟在「加到图表」后面（用户要求 ✓）——
        //   和看盘窗口工具栏「指标 → 策略管理…」是**同一个弹窗**：
        //   列出所有图表（含多布局每格）已加载的策略，可改自动运行 / 实盘 ✓
        this.manageButton = this._button('策略管理', () => {
            this.options.onCommand('strategy_manage', {});
        });
        this.manageButton.title =
            '管理所有图表已加载的策略（同 指标 → 策略管理…）';
        this.backtestButton = this._button('策略回测', () => this._strategyAction('backtest'));
        this.optimizeButton = this._button('参数优化', () => this._strategyAction('optimize'));
        this.backtestButton.title = '用当前策略文件跑回测（独立策略 Tab）';
        this.optimizeButton.title = '用当前策略文件跑参数优化（独立策略 Tab）';
        if (!this.options.onBacktest && !this.options.onOptimize) {
            this.backtestButton.style.display = 'none';
            this.optimizeButton.style.display = 'none';
        }
        // ★ 「策略实盘 / 模拟盘」：把当前策略文件**常驻运行**
        //   （`Bt(live=True)` + 快期模拟账号 → 真下单 ✓）
        //   「加到图表」只是图上回放（跑完就停），要连续交易点这里 ✓
        this.liveButton = this._button('策略实盘', () => {
            const path = this.activePath;
            if (!path) {
                this._toastTop('warning', '先打开一个策略文件');
                return;
            }
            // ★ 策略实盘会**真下单**（模拟号也会）；启动前必须人工确认 ✓
            const ok = window.confirm(
                '策略实盘会把当前文件常驻运行，并按账户页当前选择'
                + '（快期模拟 / 实盘）真实下单。\n\n'
                + '可以同时运行多个策略（一个文件一个子进程）；'
                + '「停止实盘」会全部停止。\n\n确认启动？');
            if (!ok) return;
            this.options.onCommand('strategy_live_start',
                                   { file: path, confirm: true });
        });
        this.liveButton.title = '把当前策略常驻运行（天勤模拟号 / 实盘会真的下单）';
        this.liveButton.classList.add('desk-editor-live');
        this.stopLiveButton = this._button('停止实盘', () => {
            // 不带 file = 停止并删除**所有**后台运行的策略实盘 ✓
            this.options.onCommand('strategy_live_stop', {});
        });
        this.stopLiveButton.title = '停止全部策略实盘（结束子进程，不平仓）';
        // ★ 本地图表是离线 CSV → 策略实盘 / 停止都隐藏；
        //   实时图表 → 两个按钮都显示（停止在未运行时禁用）✓
        const allowLive = this.options.allowLive !== false;
        this.liveButton.style.display = allowLive ? '' : 'none';
        this.stopLiveButton.style.display = allowLive ? '' : 'none';
        this.stopLiveButton.disabled = true;
        const removeButton = this._button('', () => this._removeFile());
        removeButton.innerHTML = ICON_TRASH;
        removeButton.title = '删除当前文件';
        const refreshButton = this._button('', () => this._refreshAll());
        refreshButton.innerHTML = ICON_REFRESH;
        refreshButton.title = '刷新资源管理器';
        // 「刷新指标策略」按用户要求删掉：
        // 个人指标 / 策略在打开「更多指标和策略」时才按目录扫描 ✓
        this.refreshPersonalButton = this._button('', () => undefined);
        this.refreshPersonalButton.style.display = 'none';
        const shotButton = this._button('', () => this._copyAll());
        shotButton.innerHTML = ICON_COPY;          // 复制图标（以前是相机 ✗）
        shotButton.title = '复制全部代码到剪贴板';
        // 「帮助」放**最右边**（和 MiniQT 编辑器的帮助按钮一致 ✓）
        const helpButton = this._button('帮助', () => {
            this.options.onCommand('editor_help', {});
        });
        helpButton.title = '帮助（环境配置指引）';
        helpButton.classList.add('desk-editor-help');
        this.tabs = document.createElement('div');
        this.tabs.className = 'desk-editor-tabs';
        // ★ 鼠标滚轮 → **横向翻页**（竖向滚轮也认；文件多了不用拖滚动条 ✓）
        this.tabs.addEventListener('wheel', (event) => {
            const host = this.tabs as HTMLDivElement;
            if (host.scrollWidth <= host.clientWidth) return;
            const delta = event.deltaY || event.deltaX;
            if (!delta) return;
            event.preventDefault();
            host.scrollLeft += delta;
        }, { passive: false });
        // ★ PI 独立界面：这些桌面专属按钮**隐藏**（不是删代码 ✓）
        if (this.piOnly) {
            for (const button of [this.addButton, this.overlayButton,
                                  this.manageButton, this.backtestButton,
                                  this.optimizeButton, this.liveButton,
                                  this.stopLiveButton, helpButton]) {
                button.style.display = 'none';
            }
        }
        toolbar.append(folderButton, newButton, this.saveButton,
                       this.checkButton, this.formatButton, this.addButton,
                       this.overlayButton, this.manageButton,
                       this.backtestButton, this.optimizeButton,
                       this.liveButton, this.stopLiveButton,
                       removeButton, refreshButton, shotButton, this.tabs,
                       helpButton);

        // ★ 用户 2026-11-08：按钮名「符号」→「预览」（功能不变：跨文件符号预览）
        this.symbolButton = this._button('预览', () => this._toggleSymbols());
        this.symbolButton.title = '预览 / 搜索工作区符号（跨文件 class / def，Ctrl+T）';
        this.symbolButton.style.display = 'none';
        toolbar.appendChild(this.symbolButton);
        this.symbolBox = document.createElement('div');
        this.symbolBox.className = 'desk-editor-symbols';
        this.symbolBox.style.display = 'none';
        // ---- v1.3.7：分屏 / 片段 / 调试 / AI / REPL ----
        this.splitButton = this._button('分屏', () => this._toggleSplit());
        this.splitButton.title = '左右分屏（各看一个文件，Ctrl+\ 切换）';
        toolbar.appendChild(this.splitButton);
        this.snippetButton = this._button('片段 ▾', (button) => {
            showMenuBelow(button, SNIPPETS.map((item) => ({
                label: item.label,
                run: () => this._insertSnippet(item.key),
            })));
        });
        this.snippetButton.title = '代码片段库（策略 / 指标 / 下单 / 风控 / 优化…）';
        toolbar.appendChild(this.snippetButton);
        const debugButton = this._button('调试', () => this._startDebug());
        debugButton.title = '断点调试当前文件（点行号左侧打红点）';
        toolbar.appendChild(debugButton);
        // ★ 终端 + REPL 合成**一个**按钮：点了打开「上次用的页签」
        //   （没有就用终端）；右键可以直接选另一个页签 ✓
        const consoleButton = this._button('终端', () => {
            this.openConsole(this.consoleTab);
        });
        consoleButton.title = '终端 / REPL（打开上次用的页签；右键选页签）';
        consoleButton.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            showMenuBelow(consoleButton, [
                { label: '终端', run: () => this.openConsole('terminal') },
                { label: 'REPL', run: () => this.openConsole('repl') },
            ]);
        });
        toolbar.appendChild(consoleButton);
        const aiButton = this._button('发给 AI ▾', (button) => {
            const box = button.getBoundingClientRect();
            this._sendToAiMenu(box.left, box.bottom);
        });
        aiButton.title = '把选中代码 / 整个文件 / 文件地址发到 PI 会话输入框';
        toolbar.appendChild(aiButton);
        this.previewButton = this._button('预览', () => {
            this.previewOn = !this.previewOn;
            this._syncPreview();
        });
        this.previewButton.title = 'Markdown 预览（Ctrl+Shift+V）';
        this.previewButton.style.display = 'none';
        toolbar.appendChild(this.previewButton);
        this.previewPane = document.createElement('div');
        this.previewPane.className = 'desk-editor-preview';
        this.previewPane.style.display = 'none';
        this.host = document.createElement('div');
        this.host.className = 'desk-editor-host';
        this.status = document.createElement('div');
        this.status.className = 'desk-editor-status';
        this._writeStatus('选择左侧文件开始编辑（Ctrl+S 保存）');
        const body = document.createElement('div');
        body.className = 'desk-editor-body';
        // ★ 分屏：左右两个宿主，各自挂一个 tab 的编辑器（v1.3.7 ✓）
        const paneWrap = document.createElement('div');
        paneWrap.className = 'desk-editor-panes';
        this.paneB = document.createElement('div');
        this.paneB.className = 'desk-editor-host desk-editor-pane-b';
        this.paneB.style.display = 'none';
        paneWrap.append(this.host, this.paneB);
        body.append(paneWrap);
        // ★ PI 独立界面的初始化页（不是页签；没有会话时显示 ✓）
        if (this.piOnly) {
            this.welcome = new PiWelcome({
                theme: this.options.theme === 'light' ? 'light' : 'dark',
                model: '',
                version: String(this.options.version || ''),
                piVersion: String(this.options.piVersion || ''),
                onModels: () => this._openPiModels(),
                onSend: (text) => this._sendFromWelcome(text),
                onOpenSession: (id) => this.openPiSession(id),
                onToast: (level, text) => this.options.onToast?.(
                    level, text),
                suggestions: [
                    '读一下当前项目，告诉我可以改进什么',
                    '帮我写一个 MACD 金叉的指标',
                    '这个文件里的 bug 在哪？',
                ],
            });
            this.welcome.element.style.display = 'none';
            body.appendChild(this.welcome.element);
        }
        if (this.previewPane) body.appendChild(this.previewPane);
        // 右侧 dock（调试 / AI，默认收起 ✓）
        this.dock = document.createElement('div');
        this.dock.className = 'desk-editor-dock';
        this.dock.style.display = 'none';
        const dockHead = document.createElement('div');
        dockHead.className = 'desk-editor-dock-head';
        const debugTab = this._button('调试', () => this._openDock());
        const dockClose = this._button('×', () => {
            if (this.dock) this.dock.style.display = 'none';
        });
        dockClose.classList.add('desk-editor-dock-close');
        dockHead.append(debugTab, dockClose);
        this.dockBody = document.createElement('div');
        this.dockBody.className = 'desk-editor-dock-body';
        this.dock.append(dockHead, this.dockBody);
        body.appendChild(this.dock);
        // 底部控制台（终端 / REPL 两个页签，默认收起 ✓）
        this.consolePane = document.createElement('div');
        this.consolePane.className = 'desk-editor-repl desk-editor-console';
        this.consolePane.style.display = 'none';
        const consoleHead = document.createElement('div');
        consoleHead.className = 'desk-editor-console-head';
        const makeTab = (label: string, key: 'terminal' | 'repl') => {
            const button = this._button(label, () => this.openConsole(key));
            button.classList.toggle('on', this.consoleTab === key);
            return button;
        };
        const terminalTab = makeTab('终端', 'terminal');
        const replTab = makeTab('REPL', 'repl');
        const consoleClose = this._button('×', () => {
            if (this.consolePane) this.consolePane.style.display = 'none';
            this.consoleOn = false;
            this.consoleTab = this.consoleTab || 'terminal';
        });
        consoleClose.classList.add('desk-editor-dock-close');
        consoleClose.classList.add('desk-editor-console-close');
        consoleClose.title = '关闭终端 / REPL';
        consoleHead.append(terminalTab, replTab);
        this.terminalOutput = document.createElement('div');
        this.terminalOutput.className = 'desk-editor-repl-out';
        this.replOutput = document.createElement('div');
        this.replOutput.className = 'desk-editor-repl-out';
        this.replOutput.style.display = 'none';
        const terminalRow = document.createElement('div');
        terminalRow.className = 'desk-editor-repl-row';
        const terminalPrompt = document.createElement('span');
        terminalPrompt.className = 'desk-editor-repl-prompt';
        terminalPrompt.textContent = '$';
        this.terminalInput = document.createElement('input');
        this.terminalInput.className = 'desk-editor-repl-input';
        this.terminalInput.placeholder =
            '输入命令（回车发送；如 pi / python -m pytest / git status）';
        this.terminalOutput.addEventListener('scroll', () => {
            const node = this.terminalOutput;
            if (!node) return;
            this.terminalPinned = node.scrollHeight - node.scrollTop
                - node.clientHeight < 24;
        });
        this.terminalInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                this._sendTerminal(this.terminalInput?.value || '');
            } else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                event.preventDefault();
                this._historyStep(this.terminalInput, this.terminalHistory,
                                  event.key === 'ArrowUp', 'terminal');
            }
        });
        this.terminalPromptEl = terminalPrompt;
        terminalRow.append(terminalPrompt, this.terminalInput);
        const replRow = document.createElement('div');
        replRow.className = 'desk-editor-repl-row';
        replRow.style.display = 'none';
        const prompt = document.createElement('span');
        prompt.className = 'desk-editor-repl-prompt';
        prompt.textContent = '>>>';
        this.replInput = document.createElement('input');
        this.replInput.className = 'desk-editor-repl-input';
        this.replInput.placeholder =
            '输入 Python 回车执行（已自动 import minibt；↑↓ 历史）';
        this.replInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                this._sendRepl(this.replInput?.value || '');
            } else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                event.preventDefault();
                this._historyStep(this.replInput, this.replHistory,
                                  event.key === 'ArrowUp', 'repl');
            }
        });
        replRow.append(prompt, this.replInput);
        const consoleActions = document.createElement('div');
        consoleActions.className = 'desk-editor-console-actions';
        const addAction = (label: string, run: () => void) => {
            const button = this._button(label, run);
            button.style.height = '20px';
            button.style.fontSize = '11px';
            consoleActions.appendChild(button);
        };
        addAction('清屏', () => {
            if (this.terminalOutput) this.terminalOutput.textContent = '';
            if (this.replOutput) this.replOutput.textContent = '';
        });
        addAction('切换 Shell', () => {
            const anchor = this.consolePane as HTMLElement | null;
            if (!anchor) return;
            const box = anchor.getBoundingClientRect();
            showMenuBelow(this._anchor(box.right - 120, box.bottom - 30), [
                { label: '系统默认', run: () => this._reopenTerminal('') },
                { label: 'cmd.exe', run: () => this._reopenTerminal('cmd.exe /Q /K') },
                { label: 'PowerShell', run: () => this._reopenTerminal(
                    'powershell.exe -NoLogo -NoExit') },
                { label: 'bash（Git Bash / WSL）', run: () => this._reopenTerminal('bash -l') },
            ]);
        });
        addAction('中断', () => {
            this.options.onCommand('terminal_signal', { signal: 'ctrl-c' });
        });
        addAction('重开', () => {
            this.options.onCommand('terminal_restart', {});
        });
        addAction('系统终端', () => {
            this.options.onCommand('terminal_system', {});
        });
        consoleHead.append(consoleActions, consoleClose);
        // ★ 拖动上沿改高度（默认 220px；限制 120px ~ 视口 75% ✓）
        const resize = document.createElement('div');
        resize.className = 'desk-editor-console-resize';
        resize.title = '拖动调整终端 / REPL 高度';
        resize.addEventListener('mousedown', (event) => {
            event.preventDefault();
            const pane = this.consolePane;
            if (!pane) return;
            const startY = event.clientY;
            const startHeight = pane.getBoundingClientRect().height
                || this.consoleHeight;
            const move = (moveEvent: MouseEvent) => {
                const next = Math.max(120, Math.min(
                    window.innerHeight * 0.75,
                    startHeight + (startY - moveEvent.clientY)));
                this.consoleHeight = next;
                pane.style.height = `${next}px`;
            };
            const up = () => {
                document.removeEventListener('mousemove', move);
                document.removeEventListener('mouseup', up);
                document.body.classList.remove('desk-resizing-v');
            };
            document.addEventListener('mousemove', move);
            document.addEventListener('mouseup', up);
            document.body.classList.add('desk-resizing-v');
        });
        this.consolePane.style.height = `${this.consoleHeight}px`;
        this.consolePane.append(resize, consoleHead, this.terminalOutput,
                                this.replOutput, terminalRow, replRow);
        this.consoleRows = { terminal: terminalRow, repl: replRow };
        this.consoleTabs = { terminal: terminalTab, repl: replTab };
        main.append(toolbar, body, this.consolePane, this.status);        main.append(toolbar, body, this.consolePane, this.status);
        this.element.append(side, main);

        // 编辑器区域的右键菜单（添加到图表 / 格式化 / 语法检测 / 剪切 / 复制…）
        this.host.addEventListener('contextmenu', (event) => {
            if (!this.activePath) return;
            event.preventDefault();
            this._editorMenu(event.clientX, event.clientY);
        });
        // 点哪个 pane 就激活哪个（输入焦点也跟着 ✓）
        const focusPane = (index: number) => {
            this.activePane = index;
            const path = this.panePath[index];
            if (path && this.open.has(path)) this._activate(path, index);
        };
        this.host.addEventListener('mousedown', () => {
            if (this.activePane !== 0) focusPane(0);
        });
        this.paneB.addEventListener('mousedown', () => focusPane(1));
        // Ctrl+\ 分屏开关 / Ctrl+Shift+` REPL（和 VS Code 的习惯一致 ✓）
        this.element.addEventListener('keydown', (event) => {
            if ((event.ctrlKey || event.metaKey)
                && event.key === BACKSLASH) {
                event.preventDefault();
                this._toggleSplit();
            }
        });
        this._bindUnloadGuard();
        this._renderEmpty('正在读取目录…');
        // ★ 资源管理器**空白处**右键：新建文件 / 新建文件夹（用户要求 ✓）
        this.tree.addEventListener('contextmenu', (event) => {
            if ((event.target as HTMLElement).closest('.desk-editor-node')) {
                return;                    // 点在文件 / 文件夹上 → 用那一行的菜单
            }
            event.preventDefault();
            const base = this.activeDir || this.root;
            showMenuBelow(this._anchor(event.clientX, event.clientY), [
                { label: '新建文件…', run: () => this._newEntryAt('new_file', base) },
                { label: '新建文件夹…',
                  run: () => this._newEntryAt('new_folder', base) },
                { label: '', separator: true },
                { label: '刷新', run: () => this._refreshAll() },
            ]);
        });
        void ICON_ERASER;
    }

    // ------------------------------------------------------------ 生命周期
    show(): void {
        this.element.style.display = 'flex';
        // ★ 用户 2026-11-08：PI 页打开时如果**一个页签都没有**，
        //   必须显示初始化页（以前什么都不调 → 一片空白 ✗）
        this._syncWelcome();
        if (!this.mounted) {
            this.mounted = true;
            const hint = this.options.piRoot
                ? String(this.options.rootHint || '') : '';
            this.options.onCommand('explorer_list',
                                   hint ? { path: hint } : {});
            if (this.options.piRoot && !this.piModelsPatch) {
                this.options.onCommand('pi_models', {});
            }
            // ★ PI 装了没（没装 → PI 按钮禁用 + tooltip 提示 ✓）
            this.options.onCommand('pi_status', {});
            // ★ 恢复**上次打开的文件**（资源管理器根目录后端已按
            //   `settings.explorer_root` 恢复 ✓）——只在第一次显示时做，
            //   文件不在了后端会静默忽略 ✓
            this.options.onCommand('editor_restore', {});
        }
        if (this.piOnly) {
            // ★ PI 独立界面：左侧固定「PI 会话」，没有会话时右侧是初始化页 ✓
            if (!this.piPanel) {
                this.piOpen = false;
                this.togglePiPanel();
            }
            this._syncWelcome();
            this.welcome?.focus();
            return;
        }
        this._activeEditor()?.focus();
    }

    hide(): void {
        this.element.style.display = 'none';
    }

    setTheme(theme: 'light' | 'dark'): void {
        this.options.theme = theme;
        for (const tab of this.open.values()) tab.editor.setTheme(theme);
    }

    // ------------------------------------------------------------ 后端补丁
    /** `{type:'explorer'}` → 目录内容 ✓ */
    setExplorer(data: ExplorerData): void {
        if (!data || !data.ok) {
            this._renderEmpty(data?.error || '读取目录失败');
            return;
        }
        const previousRoot = this.root;
        this.root = data.root || this.root;
        // ★ PI 独立界面：记住自己的目录（`pi_root`），不碰全局 ✓
        if (this.options.piRoot && this.root && this.root !== previousRoot) {
            this.options.onCommand('set_setting',
                                   { key: 'pi_root', value: this.root });
        }
        // ★ 资源管理器切了目录 → PI 会话列表跟着切（双向同步 ✓）
        if (this.piPanel) {
            this.piPanel.setProject(this.root);
            if (previousRoot && previousRoot !== this.root) {
                this.options.onCommand('pi_sessions', {});
            }
        }
        const path = data.path || this.root;
        this.children.set(path, data.items || []);
        if (path !== this.root) this.expanded.add(path);
        if (!this.activeDir) this.activeDir = path;
        // 后端有时只推**子目录**（比如新建文件后推父目录）→ 根目录列表还没拿到
        // 就补一次请求，否则树是空的 ✗
        if (!this.children.has(this.root)) {
            this.options.onCommand('explorer_list', { path: this.root });
        }
        this._renderTree();
        // ★ 有"待定位"的文件 → 目录加载完继续展开 / 滚动 ✓
        if (this.pendingReveal) {
            const pending = this.pendingReveal;
            this.pendingReveal = '';
            this.revealInExplorer(pending);
        }
        // 根目录一变就查一次：是不是「我的脚本 / 我的策略」目录 ✓
        if (path === this.root) this._syncPersonal(this.root);
        this.sideHead.title = this.personalKind
            ? '当前目录是「我的脚本 / 我的策略」' : '';
    }

    /** `{type:'editor_file'}` → 打开 / 切换标签 ✓ */
    setFile(file: { path?: string; name?: string; kind?: string;
                    text?: string; new?: boolean }): void {
        const path = String(file.path || '');
        if (!path) return;
        if (this.open.has(path)) {
            this._activate(path);
            const read = this.pendingAiRead;
            if (read && read.path === path) {
                this.pendingAiRead = null;
                this._pushToAi(read.target, 'file', path,
                               this._fileText(path));
            }
            return;
        }
        const name = String(file.name || path.split(/[\\/]/).pop() || '');
        const text = String(file.text || '');
        const kind = file.kind === 'strategy'
            || /class\s+\w+\s*\([^)]*Strategy[^)]*\)/.test(text)
            ? 'strategy'
            : (file.kind === 'indicator' ? 'indicator' : 'file');
        const editor = new CodeEditor({
            parent: document.createElement('div'),
            value: text,
            theme: this.options.theme,
            // ★ 绝对路径 + LSP 地址：补全 / 悬停 / 跳转 / 语法浪线都靠它 ✓
            path,
            lsp: this.options.lsp?.(),
            onLspStatus: (statusText, level) => this._setLspStatus(
                statusText, level),
            // 跨文件 F12 / Ctrl+点击：打开目标文件再跳行 ✓
            onOpenLocation: (targetPath, line) => this._openAt(targetPath,
                                                               line),
            onCursor: (line, column) => this._setCursor(line, column),
            // ★ 行号左侧点一下 → 打 / 取消断点（v1.3.7 断点调试 ✓）
            onGutterClick: (line) => this._toggleBreakpoint(path, line),
            onChange: (value) => this._onChange(path, value),
            onSave: () => this._save(),
        });
        const button = document.createElement('button');
        button.className = 'desk-editor-tab';
        const label = document.createElement('span');
        label.textContent = name;
        const close = document.createElement('span');
        close.className = 'x';
        close.textContent = '×';
        close.addEventListener('click', (event) => {
            event.stopPropagation();
            this._closeTab(path);
        });
        button.append(label, close);
        button.addEventListener('click', () => this._activate(path));
        this.tabs.appendChild(button);
        this.open.set(path, { path, name, kind, text, saved: text, editor,
            button });
        this.activeDir = path.replace(/[\\/][^\\/]*$/, '');
        this._activate(path);
    }

    markSaved(path: string, text?: string): void {
        const tab = this.open.get(String(path || ''));
        if (!tab) return;
        if (text !== undefined) tab.text = text;
        tab.saved = tab.text;
        this._renderTabs();
    }

    setCheck(path: string, result: EditorCheckResult): void {
        const tab = this.open.get(String(path || ''));
        if (!tab) return;
        this._writeStatus('');
        if (result?.ok) {
            const ok = document.createElement('span');
            ok.className = 'ok';
            ok.textContent = '语法 OK';
            this.status.append(ok);
            const names = (result.defines || [])
                .map((item) => `${item.name}（${item.kind}）`).join('、');
            if (names) {
                const about = document.createElement('span');
                about.textContent = `定义：${names}`;
                this.status.appendChild(about);
            }
        } else {
            const bad = document.createElement('span');
            bad.className = 'err';
            bad.textContent = `第 ${result?.line || 0} 行：`
                + `${result?.error || '语法错误'}`;
            this.status.appendChild(bad);
        }
    }

    /** `{type:'editor_formatted'}` → 换掉编辑器内容 ✓ */
    setFormatted(path: string, text: string, tool: string): void {
        const tab = this.open.get(String(path || ''));
        if (!tab) return;
        // Ctrl+S / 保存按钮：后端会把同一份 text 回推一次。
        // 内容没变就不要 setValue —— 整篇 replace 会让编辑器跳回顶部 ✗。
        if (tab.text !== text) {
            tab.editor.setValue(text);
            tab.text = text;
        }
        if (tool === 'save') tab.saved = text;
        this._renderTabs();
        this._writeStatus(tool === 'save' ? '已保存' : `已格式化（${tool}）`);
    }

    remove(path: string): void {
        this._closeTab(String(path || ''), true);
    }

    /** 目录是不是「我的脚本 / 我的策略」（只在状态栏提示，不再有按钮 ✓） */
    setPersonalKind(kind: 'indicator' | 'strategy' | ''): void {
        this.personalKind = kind;
        if (kind) {
            this._writeStatus('当前目录是「'
                + (kind === 'indicator' ? '我的脚本' : '我的策略')
                + '」—— 保存后打开「更多指标和策略」即可看到');
        }
    }

    // ------------------------------------------------------------ 文件树
    private _renderEmpty(text: string): void {
        this.tree.textContent = '';
        const empty = document.createElement('div');
        empty.className = 'desk-editor-empty';
        empty.textContent = text;
        this.tree.appendChild(empty);
    }

    private _renderTree(): void {
        this.sideHead.textContent = '';
        const title = document.createElement('span');
        title.className = 'grow';
        title.textContent = this.root ? this.root.split(/[\\/]/).pop() || 'ROOT'
            : '资源管理器';
        title.title = this.root;
        const openBtn = document.createElement('button');
        openBtn.className = 'desk-editor-btn';
        openBtn.textContent = '打开';
        openBtn.title = '选择文件夹作为根目录';
        openBtn.addEventListener('click', () => {
            // ★ 一律弹**系统**文件夹框（后端 `choose_directory`：
            //   Qt 原生 / tkinter 兜底），用户不用手输路径 ✓
            this.options.onCommand('explorer_pick', {});
        });
        const newBtn = document.createElement('button');
        newBtn.className = 'desk-editor-btn';
        newBtn.textContent = '＋';
        newBtn.title = '新建文件 / 文件夹';
        newBtn.addEventListener('click', () => showMenuBelow(newBtn, [
            { label: '新建文件…', run: () => this._newEntry('new_file') },
            { label: '新建文件夹…', run: () => this._newEntry('new_folder') },
        ]));
        const refreshBtn = document.createElement('button');
        refreshBtn.className = 'desk-editor-btn';
        refreshBtn.textContent = '⟳';
        refreshBtn.title = '刷新';
        refreshBtn.addEventListener('click', () => this._refreshAll());
        // 「个人指标策略管理」：查看 / 删除已导入的目录（默认目录不显示 ✓）
        const manageBtn = document.createElement('button');
        manageBtn.className = 'desk-editor-btn';
        manageBtn.textContent = '⚙';
        manageBtn.title = '个人指标策略管理（查看 / 删除已导入的目录）';
        manageBtn.addEventListener('click', () => this._refreshPersonal());
        // ★ PI 按钮放在「打开」**左边**（用户 2026-11-08 要求 ✓）
        if (!this.piButton) {
            this.piButton = document.createElement('button');
            this.piButton.className = 'desk-editor-btn desk-pi-toggle';
            this.piButton.textContent = 'PI';
            this.piButton.title = 'PI 会话（再点一下回到资源管理器）';
            this.piButton.addEventListener('click', () => this.togglePiPanel());
        }
        this.piButton.classList.toggle('on', this.piOpen);
        this._syncPiButton();
        this.sideHead.append(title, this.piButton, openBtn, newBtn,
                             refreshBtn, manageBtn);
        this.sideHead.title = this.personalKind
            ? '当前目录是「我的脚本 / 我的策略」' : '';

        this.tree.textContent = '';
        if (!this.root) {
            this._renderEmpty('点「打开目录」选择文件夹');
            return;
        }
        const items = this.children.get(this.root) || [];
        if (!items.length) {
            this._renderEmpty('（空目录 —— 点「＋」新建文件）');
        }
        for (const item of items) this._renderNode(item, 0);
    }

    private _renderNode(item: ExplorerItem, depth: number): void {
        const row = document.createElement('div');
        row.className = 'desk-editor-node'
            + (item.path === this.activePath ? ' on' : '');
        row.dataset.path = item.path;          // 定位用 ✓
        row.style.paddingLeft = `${6 + depth * 12}px`;
        const twist = document.createElement('span');
        twist.className = 'twist';
        if (item.dir) {
            twist.textContent = this.expanded.has(item.path) ? '▾' : '▸';
        }
        const ico = document.createElement('span');
        ico.className = 'ico';
        ico.textContent = item.dir ? '📁' : (item.py ? '🐍'
            : (item.text ? '📝' : '📄'));
        const name = document.createElement('span');
        name.className = 'name';
        name.textContent = item.name;
        name.title = item.path;
        row.append(twist, ico, name);
        const tab = this.open.get(item.path);
        if (tab && tab.text !== tab.saved) {
            const dirty = document.createElement('span');
            dirty.className = 'dirty';
            dirty.textContent = '●';
            row.appendChild(dirty);
        }
        row.addEventListener('click', () => {
            this.activeDir = item.dir ? item.path : item.path.replace(
                /[\\/][^\\/]*$/, '');
            if (item.dir) {
                this._toggleDir(item.path);
                this._syncPersonal(item.path);
            } else if (item.py || item.text) {
                this.options.onCommand('editor_open', { path: item.path });
                this._syncPersonal(this.activeDir);
            } else {
                this._writeStatus('只支持编辑文本类文件（.py / .md / .txt …）');
            }
            this._renderTree();
        });
        row.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            event.stopPropagation();
            this._nodeMenu(item, event.clientX, event.clientY);
        });
        this.tree.appendChild(row);
        if (item.dir && this.expanded.has(item.path)) {
            for (const child of this.children.get(item.path) || []) {
                this._renderNode(child, depth + 1);
            }
        }
    }

    /**
     * 在**资源管理器**里定位并滚动到某个文件 ✓
     *
     * 用户要求（2026-11-03）：切换编辑器标签时，资源管理器要展开它所在的
     * 所有上层目录（折叠的也展开）、高亮并把这一行滚进可见区 ——
     * 以前只有「高亮」没有展开 / 滚动，折叠的文件夹里根本看不到 ✗
     */
    revealInExplorer(path: string): void {
        if (!path) return;
        if (!this.root) {
            // 资源管理器根目录还没拿到（刚建面板 / 刚「打开目录」）→
            // 记下来，`setExplorer()` 拿到根之后继续 ✓
            this.pendingReveal = path;
            return;
        }
        const root = this.root.replace(/[\\/]+$/, '');
        const sep = path.includes('\\') ? '\\' : '/';
        if (!path.toLowerCase().startsWith(root.toLowerCase())) {
            // 不在当前根目录（比如从别处打开的文件）→ 只切 activeDir ✓
            this.activeDir = path.replace(/[\\/][^\\/]*$/, '');
            return;
        }
        const rel = path.slice(root.length).replace(/^[\\/]+/, '');
        const parts = rel.split(/[\\/]+/).filter(Boolean);
        let current = root;
        for (let index = 0; index < parts.length - 1; index += 1) {
            current = current + sep + parts[index];
            const loaded = this.children.has(current);
            if (!this.expanded.has(current)) this.expanded.add(current);
            if (!loaded) {
                // 目录内容还没拉过 → 先请求，回来后再继续（`setExplorer` ✓）
                this.pendingReveal = path;
                this.options.onCommand('explorer_list', { path: current });
                this._renderTree();
                return;
            }
        }
        this._renderTree();
        this._scrollTreeTo(path);
    }

    /** 把树里某一行滚进可见区 + 短暂高亮 ✓ */
    private _scrollTreeTo(path: string): void {
        const rows = Array.from(
            this.tree.querySelectorAll<HTMLElement>('.desk-editor-node'));
        const row = rows.find((item) => item.dataset.path === path);
        if (!row) return;
        try {
            const treeRect = this.tree.getBoundingClientRect();
            const rowRect = row.getBoundingClientRect();
            if (rowRect.top < treeRect.top
                    || rowRect.bottom > treeRect.bottom) {
                row.scrollIntoView({ block: 'nearest' });
            }
        } catch {
            try {
                row.scrollIntoView();
            } catch { /* ignore */ }
        }
        row.classList.add('reveal');
        window.setTimeout(() => row.classList.remove('reveal'), 900);
    }

    private _toggleDir(path: string): void {
        if (this.expanded.has(path)) {
            this.expanded.delete(path);
            return;
        }
        this.expanded.add(path);
        this.options.onCommand('explorer_list', { path });
    }

    /** 目录对上「我的脚本 / 我的策略」→ 「刷新指标策略」可用 ✓ */
    private _syncPersonal(path: string): void {
        this.options.onCommand('explorer_check_personal', { path });
    }

    private _refreshAll(): void {
        this.children.clear();
        this.expanded.clear();
        this.options.onCommand('explorer_list', {});
    }

    /** 打开「个人指标策略管理」（后端推 `personal_menu` → 弹管理对话框 ✓） */
    private _refreshPersonal(): void {
        this.options.onCommand('personal_menu', {});
    }

    // ------------------------------------------------------------ 右键菜单
    private _nodeMenu(item: ExplorerItem, x: number, y: number): void {
        const items: MenuItem[] = [];
        if (!item.dir && item.py) {
            items.push({
                label: '打开', run: () => this.options.onCommand(
                    'editor_open', { path: item.path }),
            });
            if (!this.piOnly) items.push({
                label: '加到图表', run: () => {
                    // ★ 先打开文件（UX），但加图表必须用**右键这一项**的
                    //   path；`_addToChart()` 读 activePath 时 editor_open
                    //   还是异步的，会加成上一个文件 ✗
                    this.options.onCommand('editor_open',
                                           { path: item.path });
                    this._addToChart(item.path);
                },
            });
            items.push({ label: '', separator: true });
        }
        items.push({ label: '新建文件…',
                     run: () => this._newEntry('new_file', item) });
        items.push({ label: '新建文件夹…',
                     run: () => this._newEntry('new_folder', item) });
        items.push({ label: '', separator: true });
        items.push({
            label: '复制地址', run: () => this._copyPath(item.path),
        });
        if (!item.dir) {
            // ★ 发给 AI：文件地址 / 全部代码 → 选会话 ✓
            items.push({
                label: '发给 AI（文件地址）',
                submenu: this._aiSendMenu('path', item.path),
            });
            items.push({
                label: '发给 AI（全部代码）',
                submenu: this._aiSendMenu('file', item.path,
                                          this._fileText(item.path)),
            });
        }
        items.push({ label: '', separator: true });
        items.push({
            label: '剪切', run: () => this.options.onCommand(
                'explorer_op', { action: 'cut', path: item.path }),
        });
        items.push({
            label: '复制', run: () => this.options.onCommand(
                'explorer_op', { action: 'copy', path: item.path }),
        });
        items.push({
            label: '粘贴', run: () => this.options.onCommand(
                'explorer_op',
                { action: 'paste', path: item.dir ? item.path : this.activeDir }),
        });
        items.push({ label: '', separator: true });
        items.push({
            label: '重命名…', run: () => {
                const name = window.prompt('新名字', item.name);
                if (!name) return;
                this.options.onCommand('explorer_op', {
                    action: 'rename', path: item.path, name,
                });
            },
        });
        items.push({
            label: '删除', run: () => {
                if (!window.confirm(`删除 ${item.name}？`)) return;
                this.options.onCommand('explorer_op', {
                    action: 'delete', path: item.path,
                });
            },
        });
        showMenuBelow(this._anchor(x, y), items);
    }

    private _editorMenu(x: number, y: number): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        const items: MenuItem[] = [
            // ★ PI 独立界面没有图表 → 隐藏（功能代码保留 ✓）
            ...(this.piOnly ? [] : [
                { label: '添加到图表', run: () => this._addToChart() },
            ]),
            { label: '格式化整篇（Shift+Alt+F）', run: () => this._format() },
            { label: '格式化选区', run: () => this._formatSelection() },
            { label: '', separator: true },
            { label: '重命名符号（F2）', run: () => this._renameSymbol() },
            { label: '查找引用（Shift+F12）', run: () => this._findReferences() },
            { label: '', separator: true },
            { label: '切换断点（当前行）', run: () => this._toggleBreakpointAtCursor() },
            { label: '语法检测', run: () => this._check() },
            { label: '', separator: true },
            { label: '剪切', run: () => this._clipboard('cut') },
            { label: '复制', run: () => this._clipboard('copy') },
            { label: '粘贴', run: () => this._clipboard('paste') },
            { label: '全选', run: () => tab.editor.selectAll() },
            { label: '', separator: true },
            { label: '保存（Ctrl+S）', run: () => this._save() },
            { label: '复制全部代码', run: () => this._copyAll() },
            { label: '', separator: true },
            {
                label: '发给 AI',
                submenu: [
                    {
                        label: '选中代码',
                        disabled: !this._currentSelection().code,
                        submenu: this._aiSendMenu(
                            'selection', tab.path,
                            this._currentSelection().code),
                    },
                    {
                        label: '整个文件',
                        submenu: this._aiSendMenu('file', tab.path, tab.text),
                    },
                    {
                        label: '文件地址（@路径）',
                        submenu: this._aiSendMenu('path', tab.path),
                    },
                ],
            },
        ];
        showMenuBelow(this._anchor(x, y), items);
    }

    /** 文件全文：打开的用内存；没打开先让后端读（`editor_file` 回来再发 ✓） */
    private _fileText(path: string): string {
        const tab = this.open.get(path);
        return tab ? tab.text : '';
    }

    /** 菜单需要一个锚点元素（`showMenuBelow` 是按元素定位的 ✓） */
    private _anchor(x: number, y: number): HTMLElement {
        const anchor = document.createElement('span');
        anchor.style.cssText = `position:fixed;left:${x}px;top:${y}px;`
            + 'width:0;height:0;';
        document.body.appendChild(anchor);
        window.setTimeout(() => anchor.remove(), 0);
        return anchor;
    }

    // ------------------------------------------------------------ 动作
    private _activeEditor(): CodeEditor | null {
        return this.open.get(this.activePath)?.editor || null;
    }

    private _renderTabs(): void {
        for (const [path, tab] of this.open) {
            const inActive = path === this.activePath;
            const inOther = this.splitOn && (path === this.panePath[0]
                || path === this.panePath[1]) && path !== this.activePath;
            tab.button.classList.toggle('on', inActive);
            tab.button.classList.toggle('desk-editor-tab-split', inOther);
            const label = tab.button.firstElementChild as HTMLElement | null;
            if (label) {
                label.textContent = tab.text === tab.saved
                    ? tab.name : `${tab.name} ●`;
            }
        }
        if (this.root) this._renderTree();
        this._syncButtons();
        this._reportDirty();
    }


    /** 「符号」按钮：只在 Python 文件里出现（LSP 才有这个能力 ✓） */
    private _syncSymbolsButton(): void {
        const tab = this.open.get(this.activePath);
        const isPy = !!tab && /\.(py|pyi)$/i.test(tab.path || '');
        if (this.symbolButton) {
            this.symbolButton.style.display = isPy ? '' : 'none';
        }
        if (!isPy && this.symbolBox) this.symbolBox.style.display = 'none';
    }

    /** 打开 / 关闭符号搜索框 ✓ */
    private _toggleSymbols(): void {
        const box = this.symbolBox;
        if (!box) return;
        const show = box.style.display === 'none';
        box.style.display = show ? 'block' : 'none';
        if (!show) return;
        box.innerHTML = '<input class="desk-editor-symbol-input" '
            + 'placeholder="预览：搜索 class / def（跨文件）…" />'
            + '<div class="desk-editor-symbol-list"></div>';
        const input = box.querySelector('input') as HTMLInputElement;
        input.addEventListener('input', () => {
            if (this.symbolTimer !== undefined) {
                window.clearTimeout(this.symbolTimer);
            }
            this.symbolTimer = window.setTimeout(
                () => this._searchSymbols(input.value), 250);
        });
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') box.style.display = 'none';
        });
        input.focus();
        this._searchSymbols('');
    }

    /** 跑一次工作区符号搜索并渲染结果 ✓ */
    private _searchSymbols(query: string): void {
        const box = this.symbolBox;
        const tab = this.open.get(this.activePath);
        const handle = tab?.editor.handle as unknown as {
            searchSymbols?: (q: string) => Promise<Array<{
                name: string; kind: number; path: string; line: number }>>;
        } | null;
        const list = box?.querySelector('.desk-editor-symbol-list') as
            HTMLElement | null;
        if (!list || !handle?.searchSymbols) return;
        handle.searchSymbols(query).then((items) => {
            if (!items || !items.length) {
                list.innerHTML = '<div class="desk-editor-symbol-empty">'
                    + '没有匹配的符号</div>';
                return;
            }
            list.innerHTML = items.slice(0, 60).map((item) => {
                const fileName = item.path.split(/[\/]/).pop() || '';
                return `<button class="desk-editor-symbol-item"
                    data-symbol-path="${esc(item.path)}"
                    data-symbol-line="${item.line}"
                    title="${esc(item.path)}:${item.line + 1}"
                ><b>${item.kind === 5 ? 'C' : 'ƒ'}</b>
                <span>${esc(item.name)}</span>
                <em>${esc(fileName)}:${item.line + 1}</em></button>`;
            }).join('');
        }).catch(() => {
            list.innerHTML = '<div class="desk-editor-symbol-empty">搜索失败</div>';
        });
    }

    /** 格式化**选区**（没选中 → 整篇；后端 `editor_format_range` ✓） */
    private _formatSelection(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        const handle = tab.editor.handle as unknown as {
            getSelectionRange?: () => { from: number; to: number; text: string };
        } | null;
        const range = handle?.getSelectionRange?.();
        if (!range || !range.text.trim()) {
            this._writeStatus('格式化选区：先选中一段代码（没选就整篇）');
            this._format();
            return;
        }
        const text = tab.text;
        const lineStart = text.lastIndexOf(String.fromCharCode(10),
            Math.max(0, range.from - 1)) + 1;
        const indent = (/^[ 	]*/.exec(text.slice(lineStart)) || [''])[0];
        this.options.onCommand('editor_format_range', {
            path: tab.path, text: range.text, indent,
        });
    }

    /** 选区格式化回来了 → 替换（后端已经把缩进补齐 ✓） */
    setFormattedRange(path: string, text: string): void {
        const tab = this.open.get(String(path || ''));
        if (!tab) return;
        (tab.editor.handle as unknown as {
            replaceSelection?: (value: string) => void;
        } | null)?.replaceSelection?.(String(text || ''));
        this._writeStatus('已格式化选区');
    }

    /** 重命名符号（LSP rename；跨文件暂不支持 → 明确提示 ✓） */
    private _renameSymbol(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        const handle = tab.editor.handle as unknown as {
            renameSymbol?: (name: string) => Promise<{
                ok: boolean; changed: number; others: string[]; error?: string }>;
        } | null;
        if (!handle?.renameSymbol) {
            this._writeStatus('重命名：编辑器还没准备好');
            return;
        }
        const name = window.prompt('重命名符号为：', '');
        if (!name) return;
        void handle.renameSymbol(name).then((result) => {
            if (!result?.ok) {
                this._writeStatus(`重命名失败：${result?.error || '没有可改的符号'}`
                    + (result?.others?.length
                        ? `（还影响 ${result.others.length} 个文件）` : ''));
                return;
            }
            this._writeStatus(`已重命名 ${result.changed} 处 → ${name}`);
        });
    }

    /** 查找引用（LSP references → 列表里点一下跳过去 ✓） */
    private _findReferences(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        const handle = tab.editor.handle as unknown as {
            findReferences?: () => Promise<Array<{
                path: string; line: number; name: string }>>;
        } | null;
        if (!handle?.findReferences) return;
        void handle.findReferences().then((rows) => {
            if (!rows?.length) {
                this._writeStatus('没有找到引用');
                return;
            }
            const items: MenuItem[] = rows.slice(0, 60).map((row) => ({
                label: `${String(row.path || '').split(/[\/]/).pop()}`
                    + ` : ${row.line + 1}`,
                run: () => this._openAt(row.path, row.line),
            }));
            const box = this.element.getBoundingClientRect();
            showMenuBelow(this._anchor(box.left + 80, box.top + 60), items);
            this._writeStatus(`引用 ${rows.length} 处`);
        });
    }

    // ================================================ v1.3.7 编辑器增强
    /** 关窗口前提示（**切页面 / 切标签不提示**，用户 2026-11-08 明确要求 ✓） */
    private _bindUnloadGuard(): void {
        if (this.unloadBound) return;
        this.unloadBound = true;
        window.addEventListener('beforeunload', (event) => {
            const files = this.unsavedFiles;
            if (!files.length) return;
            const text = `还有 ${files.length} 个文件没保存：`
                + `${files.slice(0, 5).join('、')}`
                + `${files.length > 5 ? '…' : ''}`
                + '（确定关闭 desk？未保存的改动会丢失）';
            event.preventDefault();
            event.returnValue = text;
            return text;
        });
    }

    /** 上报未保存文件（关 desk 时桌面端会用它弹确认 ✓） */
    private _reportDirty(): void {
        const files = this.unsavedFiles;
        const key = files.join('|');
        if (key === this.reportedDirty) return;
        this.reportedDirty = key;
        this.options.onCommand('editor_dirty', { files });
    }

    /** 有没有未保存的文件（关 desk 前提示用 ✓） */
    get unsavedFiles(): string[] {
        const out: string[] = [];
        for (const tab of this.open.values()) {
            if (tab.text !== tab.saved) out.push(tab.name);
        }
        return out;
    }

    /** 「分屏」：左右两栏各挂一个文件（`Ctrl+\` 也能切 ✓） */
    private _toggleSplit(): void {
        if (!this.paneB) return;
        this.splitOn = !this.splitOn;
        this.paneB.style.display = this.splitOn ? '' : 'none';
        this.splitButton?.classList.toggle('on', this.splitOn);
        if (!this.splitOn) {
            const sessionId = this.paneSession[1];
            if (sessionId && this.piTabs.has(sessionId)) {
                this.paneSession[1] = '';
                this._activatePi(sessionId, 0);
            } else if (this.activePane === 1 && this.panePath[1]
                && this.open.has(this.panePath[1])) {
                this._activate(this.panePath[1], 0);
            }
            this.activePane = 0;
            this.panePath[1] = '';
            this._writeStatus('已退出分屏');
            return;
        }
        // 右栏优先放「另一个已打开的会话」，其次别的文件 ✓
        const sessionOthers = [...this.piTabs.keys()].filter(
            (id) => id !== this.activePi);
        const sessionTarget = sessionOthers[sessionOthers.length - 1] || '';
        if (sessionTarget) {
            this.splitOn = true;
            this.paneB.style.display = '';
            this._activatePi(sessionTarget, 1);
            this._writeStatus('分屏：左边 / 右边各一个（会话可以放在右栏 ✓）');
            return;
        }
        const others = [...this.open.keys()].filter(
            (path) => path !== this.activePath);
        const target = others[others.length - 1] || '';
        if (!target) {
            this.paneB.innerHTML = '<div class="desk-editor-empty">'
                + '先再打开一个文件（Ctrl+点击文件名）才能分屏 ✓</div>';
            this._writeStatus('分屏：右边还没有文件（再打开一个文件即可）');
            return;
        }
        this.panePath[1] = target;
        this._activate(target, 1);
        this._writeStatus('分屏：左边 / 右边各一个文件（点哪边就编辑哪边）');
    }

    /** 「片段 ▾」：把代码片段插到光标处（按当前行缩进对齐 ✓） */
    private _insertSnippet(key: string): void {
        const snippet = SNIPPETS.find((item) => item.key === key);
        const tab = this.open.get(this.activePath);
        if (!snippet || !tab) return;
        const handle = tab.editor.handle as unknown as {
            getSelectionRange?: () => { from: number; to: number; text: string };
            insert?: (text: string) => void;
        } | null;
        if (!handle?.insert) {
            this._writeStatus('片段：编辑器还没准备好，稍后再试 ✓');
            return;
        }
        const text = tab.text;
        const range = handle.getSelectionRange?.();
        const at = range ? range.from : text.length;
        const lineStart = text.lastIndexOf(String.fromCharCode(10),
            Math.max(0, at - 1)) + 1;
        const indent = (/^[ \t]*/.exec(text.slice(lineStart)) || [''])[0];
        handle.insert(indentSnippet(snippet.text, indent));
        this._writeStatus(`已插入片段：${snippet.label}`);
    }

    // ------------------------------------------------------ 右侧 dock（调试）
    private _openDock(): void {
        // dock 目前只有「调试」一个页签（AI 已改成独立页签 ✓）
        if (!this.dock) return;
        this.dock.style.display = '';
        this._renderDock();
    }

    private _renderDock(): void {
        const body = this.dockBody;
        if (!body) return;
        body.textContent = '';
        try {
            this._renderDebug(body);
        } catch (error) {
            body.textContent = `调试面板渲染失败：${String(error)}`;
        }
    }

    private _renderDebug(body: HTMLDivElement): void {
        const state = this.debugState || {};
        const status = String(state.status || '');
        const running = status === 'paused' || status === 'running';
        const head = document.createElement('div');
        head.className = 'desk-editor-dock-title';
        head.textContent = '断点调试';
        body.appendChild(head);
        const info = document.createElement('div');
        info.className = 'desk-editor-debug-info';
        const rows = this.breakpoints.get(this._breakpointKey(this.activePath))
            || [];
        info.textContent = rows.length
            ? `断点 ${rows.length} 个：${rows.map((line) => line + 1).join(', ')}`
            : '还没有断点 —— 点行号左侧打红点，再按工具栏「调试」';
        body.appendChild(info);
        // 输出区：启动 / 用户脚本 print / 报错 都在这看得见 ✓
        const output = document.createElement('div');
        output.className = 'desk-editor-debug-out';
        const text = (this.debugOutput || []).slice(-200)
            .join(String.fromCharCode(10));
        output.textContent = text || '（点工具栏「调试」后这里会打印过程）';
        body.appendChild(output);
        if (!status) return;
        const where = document.createElement('div');
        where.className = 'desk-editor-debug-where';
        where.textContent = `状态：${status}`
            + (state.path
                ? ` · ${String(state.path).split(/[\\/]/).pop()}` : '')
            + (typeof state.line === 'number' && Number(state.line) >= 0
                ? ` : 第 ${Number(state.line) + 1} 行` : '');
        body.appendChild(where);
        const actions = document.createElement('div');
        actions.className = 'desk-editor-dock-actions';
        const add = (label: string, cmd: string) => {
            actions.appendChild(this._button(label, () => {
                this.options.onCommand('debug_cmd', { action: cmd });
            }));
        };
        if (running) {
            add('继续', 'continue');
            add('单步', 'next');
            add('步入', 'step');
            add('步出', 'out');
        }
        add('停止', 'stop');
        body.appendChild(actions);
        const frames = (state.stack || []) as Array<Record<string, unknown>>;
        if (frames.length) {
            const stack = document.createElement('div');
            stack.className = 'desk-editor-debug-stack';
            stack.textContent = frames.map((frame, index) =>
                `#${index} ${String(frame.name || '?')}`
                + ` (${String(frame.path || '').split(/[\\/]/).pop()}`
                + `:${Number(frame.line || 0) + 1})`).join(String.fromCharCode(10));
            body.appendChild(stack);
        }
        const locals = (state.locals || {}) as Record<string, unknown>;
        const keys = Object.keys(locals);
        if (keys.length) {
            const vars = document.createElement('div');
            vars.className = 'desk-editor-debug-vars';
            vars.textContent = keys.slice(0, 60)
                .map((name) => `${name} = ${String(locals[name])}`)
                .join(String.fromCharCode(10));
            body.appendChild(vars);
        }
        const evalRow = document.createElement('div');
        evalRow.className = 'desk-editor-debug-eval';
        const input = document.createElement('input');
        input.placeholder = '表达式求值（如 len(self.kline.close)）';
        input.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter') return;
            this.options.onCommand('debug_cmd', {
                action: 'eval', arg: input.value,
            });
            input.value = '';
        });
        evalRow.appendChild(input);
        body.appendChild(evalRow);
    }

    // ------------------------------------------------------ 底部控制台
    /** 打开底部控制台（`terminal` / `repl` 两个页签 ✓） */
    openConsole(tab: 'terminal' | 'repl' = 'terminal'): void {
        if (!this.consolePane) return;
        this.consoleTab = tab;
        this.consoleOn = true;
        this.consolePane.style.display = '';
        this.consolePane.style.height = `${this.consoleHeight}px`;
        if (this.consoleRows) {
            for (const [key, row] of Object.entries(this.consoleRows)) {
                row.style.display = key === tab ? '' : 'none';
            }
        }
        if (this.consoleTabs) {
            for (const [key, button] of Object.entries(this.consoleTabs)) {
                button.classList.toggle('on', key === tab);
            }
        }
        if (this.terminalOutput) {
            this.terminalOutput.style.display = tab === 'terminal' ? '' : 'none';
        }
        if (this.replOutput) {
            this.replOutput.style.display = tab === 'repl' ? '' : 'none';
        }
        if (tab === 'terminal') {
            this.terminalCwd = String(this.activeDir || this.root || '');
            this._syncTerminalPrompt();
            this.options.onCommand('terminal_open', {
                cwd: this.activeDir || this.root,
            });
            this.terminalInput?.focus();
        } else {
            this.replInput?.focus();
        }
        this._syncConsoleStatus();
    }

    /** 控制台是否展开（测试用 ✓） */
    get consoleVisible(): boolean {
        return this.consoleOn;
    }

    /** 换 shell 重开终端（VS Code 也这么做 ✓） */
    private _reopenTerminal(shell: string): void {
        this.options.onCommand('terminal_close', {});
        this.options.onCommand('terminal_open', { shell,
            cwd: this.activeDir || this.root });
        if (this.terminalOutput) this.terminalOutput.textContent = '';
        this._appendTerminal(`$ （切换 shell：${shell || '系统默认'}）`);
    }

    /** ↑↓ 翻历史（到顶 / 到底就清空 ✓） */
    private _historyStep(input: HTMLInputElement | null,
                         rows: string[], up: boolean,
                         kind: 'terminal' | 'repl'): void {
        if (!input || !rows.length) return;
        const key = kind === 'terminal' ? 'terminalHistoryAt' : 'replHistoryAt';
        let at = this[key];
        at = up ? Math.min(rows.length - 1, at + 1) : Math.max(-1, at - 1);
        this[key] = at;
        input.value = at < 0 ? '' : (rows[rows.length - 1 - at] || '');
        input.selectionStart = input.value.length;
    }

    private _sendTerminal(text: string): void {
        const line = String(text || '');
        if (!line.trim()) return;
        this.terminalHistory.push(line);
        if (this.terminalHistory.length > 200) this.terminalHistory.shift();
        this.terminalHistoryAt = -1;
        if (this.terminalInput) this.terminalInput.value = '';
        this._trackCd(line);
        this.options.onCommand('terminal_input', { text: line });
    }

    /** `cd xxx` → 提示符跟着变（用户 2026-11-08：搞不清在哪个目录 ✓） */
    private _trackCd(line: string): void {
        const matched = /^\s*cd(?:\s+(.*))?$/i.exec(line.trim());
        if (!matched) return;
        const raw = String(matched[1] || '~').trim();
        const target = raw.replace(/^"|"$/g, '').replace(/^'|'$/g, '');
        if (!this.terminalCwd) return;
        const isWindows = /^[A-Za-z]:/.test(this.terminalCwd)
            || this.terminalCwd.indexOf('\\') >= 0;
        const sep = isWindows ? '\\' : '/';
        if (target === '~' || !target) {
            this.terminalCwd = isWindows ? 'C:\\Users' : '~';
        } else if (/^[A-Za-z]:[\\/]/.test(target) || /^[\\/]/.test(target)) {
            this.terminalCwd = target;              // 绝对路径 ✓
        } else if (target === '..') {
            const parts = this.terminalCwd.split(/[\\/]/).filter(Boolean);
            if (parts.length > 1) parts.pop();
            this.terminalCwd = parts.join(sep);
        } else if (target === '.') {
            return;
        } else {
            this.terminalCwd = this.terminalCwd.replace(/[\\/]+$/, '')
                + sep + target;
        }
        this._syncTerminalPrompt();
    }

    /** 提示符显示目录最后一段（`indicators>`，完整路径在 title 里 ✓） */
    private _syncTerminalPrompt(): void {
        const node = this.terminalPromptEl;
        if (!node) return;
        const path = String(this.terminalCwd || '');
        if (!path) {
            node.textContent = '>';
            node.title = '';
            return;
        }
        const parts = path.split(/[\\/]/).filter(Boolean);
        node.textContent = (parts[parts.length - 1] || path) + '>';
        node.title = path;
    }

    private _appendTerminal(text: string): void {
        const node = this.terminalOutput;
        if (!node) return;
        const line = document.createElement('div');
        line.className = 'desk-editor-repl-line';
        // 终端输出带 ANSI 颜色 → 转成 span（VS Code 同款观感 ✓）
        this._renderAnsi(line, String(text ?? ''));
        node.appendChild(line);
        while (node.childElementCount > 500) node.removeChild(node.firstChild!);
        // 「跟随输出」：用户往上翻时不要抢滚动条（VS Code 行为 ✓）
        if (!this.terminalPinned) node.scrollTop = node.scrollHeight;
    }

    /** 极简 ANSI SGR → span（16 色 + 粗体 + 下划线 ✓） */
    private _renderAnsi(target: HTMLElement, text: string): void {
        const code = /\u001b\[([0-9;]*)m/g;
        let index = 0;
        let match: RegExpExecArray | null;
        const palette = ['#2e3440', '#ef5350', '#26a69a', '#e5c07b',
            '#61afef', '#c678dd', '#56b6c2', '#d8d9db', '#7f8c98',
            '#ff6b6b', '#4dd0a5', '#ffd166', '#82b1ff', '#e39ff6',
            '#7fdde8', '#ffffff'];
        while ((match = code.exec(text)) !== null) {
            const chunk = text.slice(index, match.index);
            if (chunk) target.appendChild(document.createTextNode(chunk));
            index = match.index + match[0].length;
            const codes = (match[1] || '0').split(';').map(Number);
            if (codes.includes(0)) continue;
            const span = document.createElement('span');
            let style = '';
            for (const value of codes) {
                if (value >= 30 && value <= 37) {
                    style += `color:${palette[value - 30 + 1]};`;
                } else if (value >= 90 && value <= 97) {
                    style += `color:${palette[value - 90 + 9]};`;
                } else if (value === 1) {
                    style += 'font-weight:600;';
                } else if (value === 2) {
                    style += 'opacity:.75;';
                } else if (value === 4) {
                    style += 'text-decoration:underline;';
                } else if (value === 7) {
                    style += 'background:var(--desk-hover);';
                }
            }
            span.setAttribute('style', style);
            code.lastIndex = index;
            const next = /\u001b\[[0-9;]*m/.exec(text.slice(index));
            const stop = next ? index + next.index : text.length;
            span.textContent = text.slice(index, stop);
            target.appendChild(span);
            index = stop;
            code.lastIndex = index;
        }
        if (index < text.length) {
            const rest = text.slice(index);
            // 去掉残留的控制字符（进度条里的 `\r` 之类 ✓）
            target.appendChild(document.createTextNode(rest.replace(/\u001b\[[0-9;]*[A-Za-z]/g, '')));
        }
    }

    private _syncConsoleStatus(): void {
        const node = this.element.querySelector('[data-console]') as
            HTMLElement | null;
        if (!node) return;
        node.textContent = this.consoleOn
            ? (this.consoleTab === 'terminal' ? '终端' : 'REPL')
            : '';
    }

    private _sendRepl(code: string): void {
        const text = String(code || '').trim();
        if (!text) return;
        this.replHistory.push(text);
        if (this.replHistory.length > 100) this.replHistory.shift();
        if (this.replInput) this.replInput.value = '';
        this._appendRepl(`>>> ${text}`, 'in');
        this.options.onCommand('repl_eval', { code: text });
    }

    private _appendRepl(text: string, kind: 'in' | 'out' | 'err' = 'out'): void {
        const node = this.replOutput;
        if (!node) return;
        const line = document.createElement('div');
        line.className = `desk-editor-repl-line ${kind}`;
        this._renderAnsi(line, String(text ?? ''));
        node.appendChild(line);
        while (node.childElementCount > 500) node.removeChild(node.firstChild!);
        node.scrollTop = node.scrollHeight;
    }

    // ------------------------------------------------------- 断点 / 调试
    /** 断点表的 key（Windows 统一小写 ✓） */
    private _breakpointKey(path: string): string {
        const value = String(path || '');
        return /^[A-Za-z]:/.test(value) ? value.toLowerCase() : value;
    }

    /** 断点：点行号左侧 → 打 / 取消（后端也存一份，启动调试时用 ✓） */
    private _toggleBreakpoint(path: string, line: number): void {
        if (!path) return;
        // ⚠ map 的 key 用小写，但 `open` 的 key 是**原始路径** ——
        //   以前直接把 path 改小写会导致 `this.open.get()` 查不到 tab，
        //   红点就画不出来 ✗（用户 2026-11-08 反馈）
        const key = this._breakpointKey(path);
        const rows = new Set(this.breakpoints.get(key) || []);
        if (rows.has(line)) rows.delete(line);
        else rows.add(line);
        const list = [...rows].sort((a, b) => a - b);
        this.breakpoints.set(key, list);
        const tab = this.open.get(path);
        (tab?.editor.handle as unknown as {
            setBreakpoints?: (lines: number[]) => void;
        } | null)?.setBreakpoints?.(list);
        this.options.onCommand('debug_breakpoints', { path, lines: list });
        if (this.dock && this.dock.style.display !== 'none') this._renderDock();
        this._writeStatus(list.length
            ? `断点 ${list.length} 个（第 ${list.map((l) => l + 1).join(', ')} 行）`
            : '已取消全部断点');
    }

    /** 当前行断点开关（右键 / F9 ✓） */
    private _toggleBreakpointAtCursor(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        const cursor = this.element.querySelector('[data-cursor]')
            ?.textContent || '';
        const match = /行\s*(\d+)/.exec(cursor);
        const line = match ? Number(match[1]) - 1 : 0;
        this._toggleBreakpoint(tab.path, line);
    }

    /** AI 回答里的代码块 → 插到当前文件光标处（用户点了才插 ✓） */
    insertAtCursor(code: string): void {
        const tab = this.open.get(this.activePath);
        const text = String(code || '');
        if (!tab || !text) return;
        // `handle.insert` 是必有的（CodeEditor 接口），只是类型上可选 ✓
        (tab.editor.handle as unknown as {
            insert: (value: string) => void;
        }).insert(text);
        this._writeStatus(`已插入 ${text.split(String.fromCharCode(10)).length}`
            + ' 行代码（Ctrl+Z 可撤销）');
    }

    // =========================================================== PI 助手
    /** 「PI」按钮：会话列表 ↔ 资源管理器（用户要求：再点一下切回来 ✓） */
    private togglePiPanel(): void {
        if (this.piInstalled === false) {
            this.options.onToast?.('warning', PI_INSTALL_HINT);
            this._writeStatus(PI_INSTALL_HINT);
            return;
        }
        this.piOpen = !this.piOpen;
        this._ensurePiPanel();
        const tree = this.tree;
        const outlineHead = this.outlineHead;
        const outline = this.outline;
        if (this.piPanel) {
            this.piPanel.element.style.display = this.piOpen ? '' : 'none';
            this.piPanel.setProject(this.root);
        }
        tree.style.display = this.piOpen ? 'none' : '';
        outlineHead.style.display = this.piOpen ? 'none' : '';
        outline.style.display = this.piOpen ? 'none' : '';
        this.piButton?.classList.toggle('on', this.piOpen);
        if (this.piOpen) {
            this.options.onCommand('pi_sessions', {});
            this.options.onCommand('pi_models', {});
        } else {
            this.options.onCommand('explorer_list', { path: this.root });
        }
    }

    /** PI 按钮状态：没装 pi → **禁用** + tooltip 提示（用户 2026-11-08 ✓） */
    private _syncPiButton(): void {
        const button = this.piButton;
        if (!button) return;
        const missing = this.piInstalled === false;
        button.disabled = missing;
        button.classList.toggle('off', missing);
        button.title = missing
            ? PI_INSTALL_HINT
            : 'PI 会话（再点一下回到资源管理器）';
    }

    private _ensurePiPanel(): void {
        if (this.piPanel) return;
        this.piPanel = new PiPanel({
            onCommand: (cmd, payload) => this.options.onCommand(cmd, payload),
            onToast: (level, text) => this.options.onToast?.(level, text),
            onOpen: (id) => this.openPiSession(id),
            onNew: () => {
                const before = this.piTabs.size;
                this.options.onCommand('pi_new_session', { cwd: this.root });
                window.setTimeout(() => {
                    if (this.piTabs.size === before && !this.piRows.length) {
                        this.options.onToast?.('warning',
                            '后端没有响应 pi_new_session：确认用 '
                            + 'python -m minibt desk 启动（仓库版 ≥ 1.3.7）');
                    }
                }, 1500);
            },
            onModels: () => this._openPiModels(),
            onSkills: () => this._openPiSkills(),
            // ★ 切目录：走后端统一入口 → 资源管理器 + 会话列表一起切 ✓
            onDir: (path) => this.options.onCommand('explorer_set_root',
                                                    { path,
                                                      ...this._piFlag() }),
            onPickDir: () => this.options.onCommand('explorer_pick',
                                                    this._piFlag()),
            onPin: (id, on) => this.options.onCommand('pi_pin', { id, on }),
        });
        this.piPanel.element.style.display = 'none';
        // 插在文件树后面（同一个左栏容器 ✓）
        this.side?.appendChild(this.piPanel.element);
    }

    private _openPiModels(): void {
        if (!this.piModels) {
            this.piModels = new PiModelsDialog({
                theme: this.options.theme === 'light' ? 'light' : 'dark',
                onCommand: (cmd, payload) =>
                    this.options.onCommand(cmd, payload),
                onToast: (level, text) => this.options.onToast?.(level, text),
            });
        }
        // ★ 先把缓存喂进去（后端慢 / 没回包也不留白 ✓）
        if (this.piModelsPatch) this.piModels.setData(this.piModelsPatch);
        this.piModels.open();
        this.options.onCommand('pi_models', {});
        this.options.onCommand('pi_status', {});
        window.setTimeout(() => {
            if (!this.piModelsPatch && this.piModels) {
                this.piOffline = true;
                this.piModels.setOffline();
            }
        }, 1500);
    }

    private _openPiSkills(): void {
        if (!this.piSkills) {
            this.piSkills = new PiSkillsDialog({
                theme: this.options.theme === 'light' ? 'light' : 'dark',
                onCommand: (cmd, payload) =>
                    this.options.onCommand(cmd, payload),
                onToast: (level, text) => this.options.onToast?.(level, text),
            });
        }
        if (this.piSkillsPatch) this.piSkills.setSkills(this.piSkillsPatch);
        this.piSkills.open();
        this.options.onCommand('pi_skills', {});
        window.setTimeout(() => {
            if (!this.piSkillsPatch && this.piSkills) {
                this.options.onToast?.('warning',
                    '后端没有响应 pi_skills：确认用 python -m minibt desk 启动'
                    + '（仓库版 ≥ 1.3.7）');
            }
        }, 1500);
    }

    /** pane 的宿主元素（右栏没建就用左栏 ✓） */
    private _paneHost(pane: number): HTMLDivElement {
        return pane === 1 && this.paneB ? this.paneB : this.host;
    }

    /** 这次打开应该挂到哪一栏：分屏 + 右栏空着 → 右栏（用户要求 ✓） */
    private _targetPane(id: string): number {
        if (!this.splitOn) return 0;
        if (this.paneSession[1] === id) return 1;
        if (this.panePath[1] === id) return 1;
        const busyB = !!this.panePath[1] || !!this.paneSession[1];
        if (!busyB && this.activePane === 0) return 1;
        return this.activePane;
    }

    /** PI 工具：关闭编辑器页签 / PI 会话（全部或指定）✓ */
    closeTabs(kind: string, ids: string[] = [], all = false): number {
        let closed = 0;
        if (kind === 'pi') {
            const targets = all ? [...this.piTabs.keys()] : ids;
            for (const id of targets) {
                if (!this.piTabs.has(id)) continue;
                this.closePiSession(id);
                closed += 1;
            }
            this._syncWelcome();       // 全关掉 → 回到初始化页 ✓
            return closed;
        }
        const targets = all ? [...this.open.keys()] : ids;
        for (const path of targets) {
            if (!this.open.has(path)) continue;
            this._closeTab(path);
            closed += 1;
        }
        this._syncWelcome();
        return closed;
    }

    /** 目录类命令带上 `pi: true`（PI 页只改自己的根 ✓） */
    private _piFlag(): Record<string, unknown> {
        return this.options.piRoot ? { pi: true } : {};
    }

    /** 初始化页要不要显示：PI 独立界面 + 没有任何会话/文件页签 ✓ */
    private _syncWelcome(): void {
        if (!this.welcome) return;
        let hasSession = !!this.activePi && this.piTabs.has(this.activePi);
        let hasFile = !!this.activePath && this.open.has(this.activePath);
        // ★ 有页签但**一个都没激活** → 先把最后一个激活（否则宿主是空的，
        //   界面一片空白 —— 用户 2026-11-08 截图反馈 ✗）。先自愈再判断 ✓
        if (!hasSession && !hasFile) {
            const lastPi = [...this.piTabs.keys()].pop();
            if (lastPi) {
                this._activatePi(lastPi);
                return;
            }
            const lastPath = [...this.open.keys()].pop();
            if (lastPath) {
                this._activate(lastPath);
                return;
            }
        }
        // 真的一无所有 → 初始化页
        const show = !hasSession && !hasFile;
        this.welcome.element.style.display = show ? '' : 'none';
        // ★ 初始化页和「编辑器 / 对话宿主」**互斥**：以前只藏宿主，
        //   两个 flex 项并排 → 对话区被挤到 0 宽（漏看右侧按钮 ✗）
        const panes = this.host.parentElement;
        if (panes) panes.style.display = show ? 'none' : '';
        this.piTabs.forEach((tab) => tab.chat.element
            .style.setProperty('display', show ? 'none' : ''));
    }

    /**
     * 初始化页发送 = 「**先建会话（落盘），再问模型**」✓
     *
     * 用户 2026-11-08：以前初始化页的对话"能聊"，但会话没保存、左边列表也看不到
     * —— 根因是前端先 `pi_new_session`、再等会话补丁发文字，中间任何一环没回来
     * 就只剩前端在聊 ✗。
     *
     * 现在只走**一条**路：`pi_send{id:""}` → 后端 `_on_pi_send` 发现没有会话就先
     * `create_session(title = 首句话)` + `save_session` + 推 `pi_session` /
     * `pi_sessions`，然后才开始跑模型（顺序固化在后端，前端不再兜底）。
     */
    private _sendFromWelcome(text: string): void {
        const value = String(text || '').trim();
        if (!value) return;
        this.welcome && (this.welcome.setText(''));
        this.pendingPiSend = value;
        this.options.onCommand('pi_send', {
            id: '',
            text: value,
            cwd: this.root,
            title: value.slice(0, 40),
        });
        this._writeStatus('正在新建 PI 会话并发送…');
    }

    /** 外部入口（「＋ → PI 助手」）：直接展开左栏 PI 会话 ✓ */
    openPiSidebar(): void {
        this.show();
        if (!this.piOpen) this.togglePiPanel();
        else this.options.onCommand('pi_sessions', {});
    }

    /** 打开（或切换）一个 PI 会话标签 ✓ */
    openPiSession(id: string, pane?: number): void {
        const key = String(id || '');
        if (!key) return;
        let tab = this.piTabs.get(key);
        if (!tab) {
            const chat = new PiChat(key, {
                onCommand: (cmd, payload) => this.options.onCommand(cmd, payload),
                onToast: (level, text) => this.options.onToast?.(level, text),
                context: () => this.contextForAi(),
            });
            const known = this.piRows.find((row) => row.id === key);
            const title = String(known?.title || known?.name || 'PI');
            const button = document.createElement('button');
            button.className = 'desk-editor-tab desk-pi-tab';
            const label = document.createElement('span');
            label.textContent = title;
            const close = document.createElement('span');
            close.className = 'x';
            close.textContent = '×';
            close.addEventListener('click', (event) => {
                event.stopPropagation();
                this.closePiSession(key);
            });
            button.append(label, close);
            button.addEventListener('click', () => this._activatePi(key));
            this.tabs.appendChild(button);
            tab = { id: key, name: title, button, chat };
            this.piTabs.set(key, tab);
            this.options.onCommand('pi_history', { id: key });
        }
        this._activatePi(key, pane);
    }

    private _activatePi(id: string, pane?: number): void {
        const tab = this.piTabs.get(String(id || ''));
        if (!tab) return;
        const target = pane ?? this._targetPane(tab.id);
        const host = this._paneHost(target);
        // 另一个 pane 已经显示这个会话 → 不重复挂（一个 chat 只有一个宿主 ✓）
        const other = target === 0 ? 1 : 0;
        if (this.paneSession[other] === tab.id) this.paneSession[other] = '';
        host.textContent = '';
        host.appendChild(tab.chat.element);
        tab.chat.scrollToBottom();
        this.activePi = tab.id;
        this.activePath = '';
        this.activePane = target;
        this.paneSession[target] = tab.id;
        this.panePath[target] = '';
        tab.chat.focus();
        this.piPanel?.setActive(tab.id);
        this._renderTabs();
        this._syncButtons();
        this._writeStatus(`PI 会话：${tab.name}`
            + (this.root ? ` · ${piShortPath(this.root)}` : ''));
        // ★ 初始化页要让位（否则 welcome + 宿主并排 → 对话区宽度被挤成 0 ✗）
        this._syncWelcome();
    }

    closePiSession(id: string): void {
        const tab = this.piTabs.get(String(id || ''));
        if (!tab) return;
        tab.button.remove();
        this.piTabs.delete(String(id));
        for (const pane of [0, 1]) {
            if (this.paneSession[pane] === String(id)) this.paneSession[pane] = '';
        }
        if (this.activePi === String(id)) {
            this.activePi = '';
            const next = [...this.piTabs.keys()].pop();
            if (next) this._activatePi(next, 0);
            else {
                this._paneHost(0).textContent = '';
                const path = [...this.open.keys()].pop();
                if (path) this._activate(path, 0);
                else this._writeStatus('选择左侧文件开始编辑（Ctrl+S 保存）');
            }
        }
        this._renderTabs();
        this._syncWelcome();
    }

    /** 当前标签是 PI 会话吗（`_renderTabs` / 按钮状态用 ✓） */
    get piActive(): boolean {
        return !!this.activePi && this.piTabs.has(this.activePi);
    }

    /** 「测试连接」结果 → 模型对话框（`ai_ping` 补丁 ✓） */
    piPingResult(patch: Record<string, unknown>): void {
        this.piModels?.setPing(patch);
    }

    /** 后端 `pi_*` 补丁统一入口（任何异常都要暴露出来 ✓） */
    piOnPatch(patch: Record<string, unknown>): void {
        try {
            this._piOnPatch(patch);
        } catch (error) {
            this.options.onToast?.('error',
                `PI 面板出错：${String((error as Error)?.message || error)}`);
        }
    }

    private _piOnPatch(patch: Record<string, unknown>): void {
        const kind = String(patch.type || '');
        if (kind === 'pi_sessions') {
            this.piRows = (patch.items || []) as PiSessionRow[];
            this.piOffline = false;
            this._ensurePiPanel();
            if (patch.default) {
                this.piPanel?.setDefaultDir(String(patch.default));
            }
            if (Array.isArray(patch.recent)) {
                this.piPanel?.setRecent(patch.recent as string[]);
            }
            this.piPanel?.setProject(String(patch.dir || this.root));
            this.piPanel?.setSessions(this.piRows);
            for (const row of this.piRows) {
                const tab = this.piTabs.get(String(row.id));
                if (!tab) continue;
                const name = String(row.title || row.name || 'PI');
                tab.name = name;
                const label = tab.button.firstElementChild as HTMLElement | null;
                if (label) label.textContent = name;
            }
            this.piPanel?.setActive(this.activePi);
            // ★ 初始化页下方显示「最近会话」（点一下直接进 ✓）
            this.welcome?.setRecent(this.piRows as never[]);
            this._renderTabs();
            if (this.piOffline) {
                this._writeStatus('PI：后端没有响应（确认用 python -m minibt '
                    + 'desk 启动 / 仓库版 ≥ 1.3.7）');
            } else if (this.piStatusPatch) {
                this._writeStatus(`PI · minibt ${String(
                    this.piStatusPatch.version || '?')}`
                    + (this.root ? ` · ${piShortPath(this.root)}` : ''));
            }
            return;
        }
        if (kind === 'pi_paste') {
            // ★ 输入框右键粘贴：后端读剪贴板 → 插到光标处（用户 2026-11-08 ✓）
            this.piTabs.get(String(patch.id || ''))?.chat.applyPaste(
                String(patch.text || ''), patch.ok !== false);
            return;
        }
        if (kind === 'pi_status') {
            this.piStatusPatch = patch;
            this.piInstalled = patch.installed !== false;
            // ★ 用户 2026-11-08：`pi v1.3.7` 用的是 minibt 版本号 ✗ →
            //   pi 版本单独用 `piVersion`（`pi --version`，现在是 1.5.1 ✓）
            this.welcome?.setVersions(String(patch.version || ''),
                                      String(patch.piVersion || ''));
            this._syncPiButton();
            if (patch.ok === false && this.piModels) {
                this.piModels.setOffline(String(patch.error || ''));
            }
            return;
        }
        if (kind === 'pi_models') {
            this.piModelsPatch = patch;
            this.piOffline = false;
            this.piModels?.setData(patch);
            for (const tab of this.piTabs.values()) {
                tab.chat.setModels(patch as never);
            }
            // ★ 用户 2026-11-08：初始化页左下角一直显示「未选择模型」——
            //   配置其实早就选好了，只是这里没把 active.model 传给初始化页 ✗
            const active = (patch.active || {}) as { model?: string };
            this.welcome?.setModel(String(active.model || ''));
            return;
        }
        if (kind === 'pi_skills') {
            this.piSkillsPatch = patch;
            this.piSkills?.setSkills(patch);
            return;
        }
        if (kind === 'pi_skills_search') {
            this.piSkills?.setSearch(patch);
            return;
        }
        if (kind === 'ai_files') {
            for (const tab of this.piTabs.values()) {
                tab.chat.setFiles((patch.items || []) as never);
            }
            return;
        }
        if (kind === 'pi_session' || kind === 'pi_history') {
            const session = (patch.session || {}) as Record<string, unknown>;
            const id = String(session.id || '');
            if (!id) return;
            this.openPiSession(id);
            this.piTabs.get(id)?.chat.bind(session);
            this._syncWelcome();
            // ★ 初始化页发起的对话：会话建好后把这句话真正发出去 ✓
            if (this.pendingPiSend) {
                const text = this.pendingPiSend;
                this.pendingPiSend = '';
                this.piTabs.get(id)?.chat.sendText(text);
                this._writeStatus('已发送（正在等模型回复）');
            }
            // ★ 「发给 AI → 新建会话」：拿到新会话就把代码放进输入框 ✓
            if (this.pendingAi) {
                const text = this.pendingAi;
                this.pendingAi = '';
                this.piTabs.get(id)?.chat.appendToInput(text);
                this._writeStatus('已放进 PI 输入框（直接回车发送）');
            }
            const tab = this.piTabs.get(id);
            if (tab) {
                tab.name = String(session.title || session.name || 'PI');
                const label = tab.button.firstElementChild as HTMLElement | null;
                if (label) label.textContent = tab.name;
            }
            this.options.onCommand('pi_models', {});
            this._renderTabs();
            return;
        }
        if (kind === 'pi_deleted') {
            this.closePiSession(String(patch.id || ''));
            return;
        }
        if (kind === 'pi_event') {
            const id = String(patch.id || '');
            const tab = this.piTabs.get(id);
            if (tab) tab.chat.event(patch);
            return;
        }
    }

    /** 给 PI 的 `@文件` 用：当前文件路径 + 选中代码 / 全文 ✓ */
    contextForAi(): { path?: string; code?: string } {
        const tab = this.open.get(this.activePath);
        if (!tab) return {};
        const selection = this._currentSelection();
        return {
            path: tab.path,
            code: (selection.code || tab.text || '').slice(0, 6000),
        };
    }

    // ------------------------------------------------- 发给 AI（v1.3.7-23）
    /**
     * 工具栏 / 右键 / 资源管理器 的「发给 AI」都走这里：
     * 把**选中代码 / 整个文件 / 文件地址**插进指定 PI 会话的输入框
     * （用户 2026-11-08：要能选发到哪个对话页面 ✓）
     */
    private _aiSendMenu(kind: 'selection' | 'file' | 'path', path: string,
                        code = ''): MenuItem[] {
        const targets = this._aiTargets();
        const items: MenuItem[] = [];
        for (const item of targets) {
            items.push({
                label: item.title,
                run: () => this._pushToAi(item.id, kind, path, code),
            });
        }
        if (items.length) items.push({ label: '', separator: true });
        items.push({
            label: '＋ 新建会话',
            run: () => this._pushToAi('', kind, path, code),
        });
        return items;
    }

    /** 可选的会话：已打开的在前面，其余（最近）按列表补足 ✓ */
    private _aiTargets(): Array<{ id: string; title: string }> {
        const rows: Array<{ id: string; title: string }> = [];
        const seen = new Set<string>();
        for (const id of this.piTabs.keys()) {
            seen.add(id);
            const row = this.piRows.find((item) => item.id === id);
            const title = row && (row.title || row.name);
            rows.push({ id, title: String(title || '对话') });
        }
        for (const row of this.piRows) {
            if (rows.length >= 12) break;
            if (seen.has(row.id)) continue;
            seen.add(row.id);
            rows.push({ id: String(row.id),
                        title: String(row.title || row.name || row.id) });
        }
        return rows;
    }

    /** 拼插入文本：`@路径` / 代码块（带语言、超长截断 ✓） */
    private _aiInsertText(kind: 'selection' | 'file' | 'path', path: string,
                          code = ''): string {
        const file = String(path || '');
        if (kind === 'path') return `@${file}`;
        const name = file.split(/[\\/]/).pop() || 'file';
        const lang = /\.py$/i.test(name) ? 'python'
            : (/\.(ts|js)$/i.test(name) ? 'ts'
                : (/\.(md|markdown)$/i.test(name) ? 'markdown' : ''));
        let body = String(code || '').split('\r\n').join('\n');
        body = body.replace(new RegExp('\n+$'), '');   // 结尾别多空一行 ✓
        const limit = 20000;
        let note = '';
        if (body.length > limit) {
            body = body.slice(0, limit);
            note = '\n……（已截断，原文件更长）';
        }
        const head = kind === 'selection'
            ? `选中的代码 · ${file}` : `文件 · ${file}`;
        return `${head}\n\`\`\`${lang}\n${body}${note}\n\`\`\``;
    }

    /** 真正插入（`target=''` → 先新建会话，等 `pi_session` 回来再插 ✓） */
    private _pushToAi(target: string, kind: 'selection' | 'file' | 'path',
                      path: string, code = ''): void {
        if (kind === 'file' && !String(code || '').trim()) {
            // 这个文件还没打开 → 让后端读回来，`setFile` 里接着发 ✓
            this.pendingAiRead = { target, path };
            this.options.onCommand('editor_open', { path });
            this._writeStatus('正在读取文件…读完就放进 PI 输入框');
            return;
        }
        const text = this._aiInsertText(kind, path, code);
        if (!target) {
            this.pendingAi = text;
            this.options.onCommand('pi_new_session', { cwd: this.root });
            this._writeStatus('已新建 PI 会话：代码放进输入框（点标签查看）');
            return;
        }
        this.openPiSession(target);
        const tab = this.piTabs.get(target);
        if (!tab) {
            this.pendingAi = text;
            this.options.onCommand('pi_new_session', { cwd: this.root });
            return;
        }
        tab.chat.appendToInput(text);
        this._writeStatus('已放进 PI 输入框（直接回车发送）');
    }

    /** 当前编辑器里选中的代码（没选中就返回空 ✓） */
    private _currentSelection(): { path: string; code: string } {
        const tab = this.open.get(this.activePath);
        if (!tab) return { path: '', code: '' };
        const handle = tab.editor.handle as unknown as {
            getSelectionRange?: () => { from: number; to: number; text: string };
        } | null;
        return {
            path: tab.path,
            code: handle?.getSelectionRange?.().text || '',
        };
    }

    /** 「发给 AI」可用的源文件：前台不是文件（比如 PI 页签）时退回上一个 ✓ */
    private _aiSourceTab(): { path: string; text: string } | null {
        const active = this.open.get(this.activePath);
        if (active) return active;
        let fallback: { path: string; text: string } | null = null;
        for (const tab of this.open.values()) fallback = tab;
        return fallback;
    }

    /** 「发给 AI」按钮 → 先选发什么，再选发到哪个会话 ✓ */
    private _sendToAiMenu(x: number, y: number): void {
        const tab = this._aiSourceTab();
        if (!tab) {
            this._writeStatus('发给 AI：先打开一个文件');
            this.options.onToast?.('info', '先打开一个文件再发给 AI');
            return;
        }
        const selection = this._currentSelection();
        const items: MenuItem[] = [
            {
                label: selection.code ? '选中代码' : '选中代码（当前没选中）',
                disabled: !selection.code,
                submenu: this._aiSendMenu('selection', selection.path,
                                          selection.code),
            },
            {
                label: '整个文件',
                submenu: this._aiSendMenu('file', tab.path, tab.text),
            },
            {
                label: '文件地址（@路径）',
                submenu: this._aiSendMenu('path', tab.path),
            },
        ];
        showMenuBelow(this._anchor(x, y), items);
    }

    /** 工具栏「调试」：把当前文件 + 断点交给后端起子进程 ✓ */
    private _startDebug(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) {
            this._writeStatus('调试：先打开一个 .py 文件');
            return;
        }
        if (!/\.py$/i.test(tab.path)) {
            this._writeStatus('调试：只有 .py 文件能调试');
            return;
        }
        this._openDock();
        this.debugState = null;
        this.debugOutput = [];
        const key = this._breakpointKey(tab.path);
        const lines = this.breakpoints.get(key) || [];
        const payload: Record<string, unknown> = {
            path: tab.path, text: tab.text,
        };
        if (lines.length) payload.lines = lines;
        this.options.onCommand('debug_start', payload);
        this._writeStatus(lines.length
            ? `调试：已启动（${lines.length} 个断点）`
            : '调试：已启动（**这个文件没有断点**，会直接跑完）');
    }

    /** 字号（跟 desk 缩放 / 设置联动 ✓） */
    setFontSize(px: number): void {
        this.fontPx = Math.max(9, Math.min(28, Number(px) || 12.5));
        for (const tab of this.open.values()) {
            (tab.editor.handle as unknown as {
                setFontSize?: (value: number) => void;
            } | null)?.setFontSize?.(this.fontPx);
        }
    }

    // ---- 后端补丁（调试 / 终端 / REPL）----
    setDebugState(state: Record<string, unknown>): void {
        const incoming = String((state || {}).output || '');
        if (incoming) {
            this.debugOutput.push(incoming);
            if (this.debugOutput.length > 500) {
                this.debugOutput = this.debugOutput.slice(-500);
            }
        }
        this.debugState = state || null;
        if (this.dock && this.dock.style.display !== 'none') this._renderDock();
        const line = Number((state || {}).line);
        const path = String((state || {}).path || '');
        if (path && Number.isFinite(line) && line >= 0) {
            if (!this.open.has(path)) {
                this.options.onCommand('editor_open', { path });
            }
            const target = path;
            window.setTimeout(() => {
                if (this.open.has(target)) {
                    this._activate(target, this.activePane);
                }
                (this.open.get(target)?.editor.handle as unknown as {
                    jumpToLine?: (value: number) => void;
                } | null)?.jumpToLine?.(line);
            }, 150);
        }
    }

    /** 终端流式输出（后端 `terminal_output` 补丁 ✓） */
    setTerminalOutput(text: string): void {
        if (text) this._appendTerminal(String(text));
    }

    /** REPL 输出 ✓ */
    setReplResult(output: string, error = ''): void {
        if (output) this._appendRepl(output, error ? 'err' : 'out');
    }

    /** 打开另一个文件并跳到某一行（F12 / 符号搜索 / Ctrl+点击 ✓） */
    private _openAt(path: string, line: number): void {
        const target = String(path || '');
        if (!target) return;
        if (!this.open.has(target)) {
            this.options.onCommand('editor_open', { path: target });
        }
        window.setTimeout(() => {
            this._activate(target);
            window.setTimeout(() => {
                (this.open.get(target)?.editor.handle as unknown as {
                    jumpToLine?: (value: number) => void;
                } | null)?.jumpToLine?.(line);
            }, 250);
        }, this.open.has(target) ? 0 : 900);
    }

    /** 状态栏：行 / 列 ✓ */
    private _setCursor(line: number, column: number): void {
        const node = this.element.querySelector('[data-cursor]') as HTMLElement
            | null;
        if (!node) return;
        node.textContent = `行 ${line}，列 ${column}`;
    }

    /** 是否 Markdown 文件（决定「预览」按钮显不显示 ✓） */
    private _isMarkdown(path: string): boolean {
        return /\.(md|markdown)$/i.test(String(path || ''));
    }

    /** 预览开关 / 内容同步（只有 .md 用 ✓） */
    private _syncPreview(): void {
        const tab = this.open.get(this.activePath);
        const isMarkdown = !!tab && this._isMarkdown(tab.path);
        if (this.previewButton) {
            this.previewButton.style.display = isMarkdown ? '' : 'none';
            this.previewButton.classList.toggle('on', isMarkdown
                && this.previewOn);
        }
        if (!this.previewPane) return;
        if (!isMarkdown || !this.previewOn) {
            this.previewOn = isMarkdown && this.previewOn;
            this.previewPane.style.display = 'none';
            return;
        }
        this.previewPane.style.display = '';
        this.previewPane.innerHTML = renderMarkdown(
            tab ? tab.editor.value : '');
    }

    /** 刷新左侧「大纲」（jedi 的 documentSymbol ✓） */
    private _refreshOutline(): void {
        const tab = this.open.get(this.activePath);
        if (!this.outline) return;
        if (!tab) {
            this.outline.innerHTML = '';
            return;
        }
        const handle = tab.editor.handle as unknown as {
            outline?: () => Promise<Array<{ name: string; kind: number;
                                            line: number; depth: number }>>;
        } | null;
        if (!handle?.outline) {
            this.outline.innerHTML = '';
            return;
        }
        handle.outline().then((items) => {
            if (!items || !items.length) {
                this.outline.innerHTML = '<div class="desk-editor-outline-empty">'
                    + '（无符号 / 非 Python 文件）</div>';
                return;
            }
            const icon = (kind: number) => (kind === 5 ? 'C'
                : (kind === 12 ? 'ƒ' : 'm'));
            this.outline.innerHTML = items.map((item) =>
                `<button class="desk-editor-outline-item" data-outline-line="${item.line}"
                    data-outline-depth="${item.depth || 0}"
                    title="${esc(item.name)}（第 ${item.line + 1} 行）"
                ><i>${icon(item.kind)}</i>${esc(item.name)}</button>`).join('');
        }).catch(() => {
            this.outline.innerHTML = '';
        });
    }

    private _activate(path: string, pane = this.activePane): void {
        const tab = this.open.get(path);
        if (!tab) return;
        const host = pane === 1 && this.paneB ? this.paneB : this.host;
        // 同一个文件不能同时挂在两个 pane 上（一个 tab 只有一个编辑器实例）
        if (pane === 1 && this.panePath[0] === path) return;
        this.activePath = path;
        this.activePane = pane;
        this.panePath[pane] = path;
        this.paneSession[pane] = '';
        host.textContent = '';
        host.appendChild(tab.editor.options.parent);
        void tab.editor.mount().then(() => {
            if (this.activePath === path) {
                tab.editor.focus();
                (tab.editor.handle as unknown as {
                    setBreakpoints?: (lines: number[]) => void;
                    setFontSize?: (px: number) => void;
                } | null)?.setBreakpoints?.(
                    this.breakpoints.get(path) || []);
                (tab.editor.handle as unknown as {
                    setFontSize?: (px: number) => void;
                } | null)?.setFontSize?.(this.fontPx);
            }
        });
        this._writeStatus(tab.kind === 'strategy'
            ? '策略可回测 / 参数优化（数据源由策略里的 get_kline 决定）'
            : 'Ctrl+S 保存后可在「指标 → 个人」里加到图表');
        // LSP 连上后再拉大纲（刚 mount 时 client 还没 ready，等一拍 ✓）
        window.setTimeout(() => this._refreshOutline(), 1200);
        this._syncPreview();
        this._syncSymbolsButton();
        this._syncStrategyButtons();
        this._renderTabs();
        this._syncWelcome();
        // ★ 切到某个文件 → 资源管理器定位 / 展开 / 滚动 ✓
        this.revealInExplorer(path);
    }

    private _closeTab(path: string, force = false): void {
        const tab = this.open.get(path);
        if (!tab) return;
        if (!force && tab.text !== tab.saved
            && !window.confirm(`${tab.name} 还没保存，确定关闭？`)) {
            return;
        }
        tab.editor.destroy();
        tab.button.remove();
        this.open.delete(path);
        if (this.activePath === path) {
            this.activePath = '';
            this.host.textContent = '';
            const next = [...this.open.keys()].pop();
            if (next) this._activate(next);
            else this._writeStatus('选择左侧文件开始编辑（Ctrl+S 保存）');
        }
        this._renderTabs();
        this._syncWelcome();       // 关掉最后一个页签 → 回到初始化页 ✓
    }

    private _onChange(path: string, value: string): void {
        if (this._isMarkdown(path) && this.previewOn) {
            if (this.previewTimer !== undefined) {
                window.clearTimeout(this.previewTimer);
            }
            this.previewTimer = window.setTimeout(() => {
                if (this.previewPane) {
                    this.previewPane.innerHTML = renderMarkdown(value);
                }
            }, 200);
        }
        const tab = this.open.get(path);
        if (!tab || tab.text === value) return;
        tab.text = value;
        this._renderTabs();
    }

    private _syncButtons(): void {
        const tab = this.open.get(this.activePath);
        this.saveButton.disabled = !tab;
        this.saveButton.classList.toggle('on',
            !!tab && tab.text !== tab.saved);
        this.checkButton.disabled = !tab;
        this.formatButton.disabled = !tab;
        // 指标 / 策略都能加到图表（策略优先，后端判断 ✓）——只要有打开的文件
        this.addButton.disabled = !tab;
    }

    /** 设置 → 编辑器「保存时自动格式化」✓ */
    setFormatOnSave(enabled: boolean): void {
        this.formatOnSave = !!enabled;
    }

    private _save(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        this.options.onCommand('editor_save', {
            path: tab.path, text: tab.text, format: this.formatOnSave,
        });
    }

    private _check(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        this.options.onCommand('editor_check', { path: tab.path, text: tab.text });
    }

    private _format(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        this.options.onCommand('editor_format', {
            path: tab.path, text: tab.text,
        });
    }

    /**
     * 当前文件是不是 Strategy；决定「策略回测 / 参数优化」是否可用 ✓
     *
     * ⚠ 判据不能只看 `tab.kind`：文件**打开时**还不是策略（刚新建 / 刚写完类
     * 还没保存）时 kind 会是 `file`，之后永远灰着（用户实测：关掉回测页后
     * 两个按钮还是不可用 ✗）。这里再按**当前源码**兜底判一次 ✓
     */
    private _syncStrategyButtons(): void {
        const tab = this.open.get(this.activePath);
        const source = String(tab?.text ?? '');
        const looksStrategy = tab?.kind === 'strategy'
            || /class\s+\w+\s*\([^)]*Strategy[^)]*\)/.test(source);
        void looksStrategy;
        if (looksStrategy && tab && tab.kind !== 'strategy') {
            tab.kind = 'strategy';           // 兜底修正，下次直接用 ✓
        }
        // ★ 用户要求：**不限制**（不因为「已有一个回测页 / 文件不是策略」而灰掉）
        //   没有处理函数才禁用（那种情况点了也没用）
        const enabled = !!(this.options.onBacktest || this.options.onOptimize);
        this.backtestButton.disabled = !enabled;
        this.optimizeButton.disabled = !enabled;
    }

    /** 策略实盘状态（后端 `strategy_live` 补丁 → 按钮变「运行中 PID」✓） */
    setStrategyLive(patch: Record<string, any>): void {
        // ★ 策略实盘可以**同时跑多个**（一个文件一个子进程）✓
        const items: Array<Record<string, any>> = Array.isArray(patch.items)
            ? patch.items : [];
        const alive = items.filter((item) => !!item.running);
        const running = items.length ? alive.length > 0 : !!patch.running;
        const count = alive.length;
        const pid = Number(alive[0]?.pid || patch.pid) || 0;
        if (this.liveButton) {
            this.liveButton.textContent = running
                ? (count > 1 ? `运行中 ${count}`
                    : (pid ? `运行中 ${pid}` : '运行中'))
                : '策略实盘';
            this.liveButton.title = running
                ? `策略正在后台运行（${count} 个${pid ? `，首个 PID ${pid}` : ''}）`
                    + '：天勤模拟/实盘会真的下单'
                : '把当前策略常驻运行（天勤模拟号 / 实盘会真的下单；可同时跑多个）';
            this.liveButton.classList.toggle('on', running);
        }
        if (this.stopLiveButton) {
            // 实时图表始终显示「停止实盘」，未运行时禁用；
            // 本地图表（allowLive=false）始终隐藏 ✓
            const allowLive = this.options.allowLive !== false;
            this.stopLiveButton.style.display = allowLive ? '' : 'none';
            this.stopLiveButton.disabled = !running;
            this.stopLiveButton.title = running
                ? `停止**全部** ${count} 个策略实盘（结束子进程，不平仓 ✓）`
                : '当前没有运行中的策略实盘';
        }
        // 状态栏徽标（像 VS Code 底部）
        const badge = this.status.querySelector('[data-live]') as
            HTMLElement | null;
        if (badge) {
            badge.className = 'desk-editor-live-badge '
                + (running ? 'on' : 'off');
            badge.textContent = running
                ? `● 实盘 运行中${count > 1 ? ` ×${count}`
                    : (pid ? ` · PID ${pid}` : '')}`
                : '● 实盘 未运行';
            badge.title = running
                ? `策略实盘在后台运行（${count} 个）—— 点「停止实盘」全部结束`
                : '策略实盘未运行（点工具栏「策略实盘」启动）';
        }
        if (patch.error) this._toastTop('error', String(patch.error));
    }

    /** 外部（关掉回测 / 优化页签后）刷新两个按钮的可用状态 ✓ */
    refreshStrategyButtons(): void {
        this._syncStrategyButtons();
    }

    /**
     * 回测 / 参数优化：**先体检**（语法 → Strategy 子类 → `op_config`）✓
     *
     * 以前直接开策略 Tab，没语法没策略也能开一个空白页 ✗
     * 现在把检查交给后端（只读源码、不执行），不通过就在**顶部中间**弹提示。
     */
    private _strategyAction(mode: 'backtest' | 'optimize'): void {
        const tab = this.open.get(this.activePath);
        if (!tab) {
            this._toastTop('warning', '先打开一个 Strategy 文件');
            return;
        }
        if (tab.text !== tab.saved) this._save();
        const id = String(Date.now());
        this.pendingStrategy.set(id, { path: tab.path, mode });
        this.options.onCommand('strategy_check',
                               { id, path: tab.path, mode });
    }

    /** 后端体检结果：通过 → 开策略 Tab；否则顶部中间提示 ✓ */
    setStrategyCheck(patch: Record<string, any>): void {
        const id = String(patch.id || '');
        const pending = this.pendingStrategy.get(id);
        this.pendingStrategy.delete(id);
        const ok = !!patch.ok;
        if (!ok) {
            this._toastTop('warning', String(patch.reason || '检查没有通过'));
            return;
        }
        const path = String(patch.path || pending?.path || '');
        const mode = (patch.mode === 'optimize' ? 'optimize' : 'backtest') as
            'backtest' | 'optimize';
        const strategies = (patch.strategies || []) as string[];
        if (mode === 'backtest') this.options.onBacktest?.(path);
        else this.options.onOptimize?.(path);
        if (strategies.length > 1) {
            this._toastTop('info',
                `文件里有 ${strategies.length} 个策略：${strategies.join(' / ')}`);
        }
    }

    /**
     * 写状态栏文字：**保留右侧的 LSP 徽标**（`textContent = ''` 会连徽标一起清掉 ✗）
     *
     * ★ 2026-11-08：文字改成单独的 `<span>`（`flex: 0 1 auto` + 省略号）——
     *   以前是裸文本节点，窄窗口里**不肯收缩**，把行/列与 LSP 徽标顶到屏幕外 ✗
     */
    private _writeStatus(text: string): void {
        const keep = Array.from(this.status.children).filter(
            (child) => (child as HTMLElement).dataset?.statusText !== '1');
        const label = document.createElement('span');
        label.className = 'desk-editor-status-text';
        label.dataset.statusText = '1';
        label.textContent = text;
        this.status.textContent = '';
        this.status.appendChild(label);
        for (const child of keep) this.status.appendChild(child);
        if (!keep.length) this._ensureLspBadge();
    }

    private _ensureLspBadge(): void {
        if (this.status.querySelector('[data-meta]')) {
            /* 元信息已就位 ✓ */
        } else {
            const meta = document.createElement('span');
            meta.className = 'desk-editor-meta';
            meta.dataset.meta = '1';
            const cursor = document.createElement('span');
            cursor.dataset.cursor = '1';
            cursor.textContent = '行 1，列 1';
            meta.append(cursor, document.createTextNode(
                '    LF    UTF-8    空格: 4'));
            this.status.appendChild(meta);
        }
        if (!this.status.querySelector('[data-live]')) {
            // ★ 状态栏「策略实盘」徽标（● 运行中 PID / 未运行 ✓）
            const live = document.createElement('span');
            live.className = 'desk-editor-live-badge off';
            live.dataset.live = '1';
            live.textContent = '● 实盘 未运行';
            live.title = '策略实盘状态（点工具栏「策略实盘」启动）';
            this.status.appendChild(live);
        }
        if (this.status.querySelector('[data-lsp]')) return;
        const badge = document.createElement('span');
        badge.className = 'desk-editor-lsp';
        badge.dataset.lsp = '1';
        badge.dataset.level = 'off';
        badge.textContent = 'LSP 未启用';
        badge.title = this._lspTitle();
        this.status.appendChild(badge);
    }

    /**
     * LSP 徽标的 tooltip：带上**编辑器解析到的 minibt 路径** ✓
     *
     * 「悬停看不到 minibt 的注释」九成是编辑器（jedi）的 sys.path 里没有 minibt
     * （没装 + 也不在仓库里）→ 这里直接把路径写出来，省得靠猜 🔍
     */
    private _lspTitle(): string {
        const info = this.options.lsp?.();
        const base = 'LSP（jedi）：补全 / 悬停 / 跳转定义 / 语法浪线';
        if (!info) return base;
        const parts = [base];
        const where = String(info.minibtPath || '');
        if (where) {
            parts.push(`minibt → ${where}`);
        } else {
            parts.push('minibt 未在 sys.path 上（悬停不会有注释，检查是否已安装 / 是否打开仓库目录）');
        }
        const count = Number(info.sysPathCount) || 0;
        if (count) parts.push(`sys.path ${count} 项`);
        return parts.join(' · ');
    }

    /** LSP 状态（状态栏右侧的小徽标 ✓） */
    private _setLspStatus(text: string, level?: 'ok' | 'error' | 'off'): void {
        const badge = this.element.querySelector('[data-lsp]') as HTMLElement
            | null;
        if (!badge) return;
        // ★ 2026-11-08：徽标只留短标签（长说明进 tooltip），
        //   否则 `LSP 已连接（jedi：补全 / 悬停 / 跳转 / 语法检查）` 236px
        //   会把窄窗口的状态栏顶出屏幕 ✗
        const short = /^[^（(]{1,20}/.exec(text)?.[0]?.trim() || text;
        badge.textContent = short;
        badge.dataset.level = level || 'off';
        badge.title = short === text ? this._lspTitle()
            : `${text}
${this._lspTitle()}`;
    }

    /** 顶部中间的提示（体检不通过 / 多个策略 等 ✓） */
    private _toastTop(level: string, text: string): void {
        this.options.onToast?.(level, text, [], undefined, 'top');
    }

    /** 把参数写回当前文件的编辑器缓冲区（不自动保存 ✓） */
    applyParams(path: string, params: Record<string, unknown>): void {
        const tab = this.open.get(path);
        if (!tab || !params || !Object.keys(params).length) return;
        const entries = Object.entries(params).map(([key, value]) =>
            `${key}=${typeof value === 'string' ? JSON.stringify(value) : value}`
        ).join(', ');
        const replacement = `params = dict(${entries})`;
        let text = tab.text;
        const replaced = replaceParamsDict(text, replacement);
        if (replaced !== null) {
            text = replaced;
        } else {
            const classLine = /^class\s+\w+\s*\([^)]*\)\s*:\s*$/m;
            if (classLine.test(text)) {
                text = text.replace(classLine, (line) => `${line}
    ${replacement}`);
            } else {
                text += `
${replacement}
`;
            }
        }
        tab.text = text;
        tab.editor.setValue(text);
        this._activate(path);
        this.options.onToast?.('info', '最优参数已写回编辑器缓冲区（未保存）');
    }

    /** 复制文件 / 文件夹的**绝对路径**（走后端系统剪贴板，`file://` 也能用 ✓） */
    private _copyPath(path: string): void {
        const text = String(path || '');
        if (!text) return;
        // ★ 先让**后端**写系统剪贴板：`file://` 页面里 navigator.clipboard
        //   需要安全上下文，实测直接 reject → 以前「复制地址点不动」✗
        this.options.onCommand('clipboard_set', { text });
        this.options.onToast?.('success', `已复制地址：${text}`);
    }

    private _addToChart(pathOverride?: string, overlay = false): void {
        const path = String(pathOverride
            || this.open.get(this.activePath)?.path
            || this.activePath || '');
        if (!path) {
            this.options.onToast?.('warning', '先打开一个指标文件');
            return;
        }
        if (overlay && !this.options.local) {
            this.options.onToast?.(
                'warning', '只读叠加目前只支持本地图表（实时图表请用策略实盘）');
            return;
        }
        // 后端按**文件路径**算 `pi:<分类>/<名字>`（类 / 函数都认 ✓）
        this.options.onCommand('editor_add_indicator', {
            path,
            local: !!this.options.local,
            overlay: !!overlay,
            symbol: this.options.symbol ? this.options.symbol() : '',
            cell: this.options.cell ? this.options.cell() : 0,
        });
    }

    private _newEntry(action: 'new_file' | 'new_folder',
                      item?: ExplorerItem): void {
        const base = item
            ? (item.dir ? item.path : this.activeDir)
            : (this.activeDir || this.root);
        const name = window.prompt(
            action === 'new_file' ? '新文件名（如 demo.py）' : '新文件夹名', '');
        if (!name) return;
        this.options.onCommand('explorer_op', { action, path: base, name });
    }

    /** 在**指定目录**新建文件 / 文件夹（空白处右键用 ✓） */
    private _newEntryAt(action: 'new_file' | 'new_folder',
                        base: string): void {
        const name = window.prompt(
            action === 'new_file' ? '新文件名（如 demo.py）' : '新文件夹名', '');
        if (!name) return;
        this.options.onCommand('explorer_op', { action, path: base, name });
    }

    private _newPersonal(kind: 'indicator' | 'strategy'): void {
        const name = window.prompt(kind === 'strategy'
            ? '策略文件名（不用写 .py）' : '指标文件名（不用写 .py）', '');
        if (!name) return;
        this.options.onCommand('editor_new', { kind, name });
    }

    private _removeFile(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        if (!window.confirm(`删除 ${tab.name}？`)) return;
        this.options.onCommand('editor_delete', { path: tab.path });
    }

    private _copyAll(): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        void navigator.clipboard?.writeText(tab.text);
        this._writeStatus('已复制全部代码到剪贴板');
    }

    /** 编辑器右键的剪切 / 复制 / 粘贴（走系统剪贴板 ✓） */
    private _clipboard(mode: 'cut' | 'copy' | 'paste'): void {
        const tab = this.open.get(this.activePath);
        if (!tab) return;
        const editor = tab.editor;
        if (mode === 'paste') {
            void navigator.clipboard?.readText().then((text) => {
                if (text) editor.insert(text);
            }).catch(() => {
                this.options.onToast?.('warning',
                    '剪贴板不可用（浏览器权限）');
            });
            return;
        }
        const selected = editor.getSelection();
        if (!selected) {
            this.options.onToast?.('info', '先选中一段代码');
            return;
        }
        void navigator.clipboard?.writeText(selected);
        if (mode === 'cut') editor.insert('');
        this._writeStatus(mode === 'cut' ? '已剪切' : '已复制');
    }

    private _button(label: string,
                    run: (button: HTMLButtonElement) => void): HTMLButtonElement {
        const button = document.createElement('button');
        button.className = 'desk-editor-btn';
        button.textContent = label;
        button.addEventListener('click', () => run(button));
        return button;
    }

    private _ensureStyle(): void {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = CSS;
        document.head.appendChild(style);
    }
}
