/**
 * PiPage —— **PI 独立界面**（v1.3.7-38）
 *
 * 需求：只想「跟 AI 对话 + 编辑代码」时，不必先开本地图表 / 实时图表。
 * 所以这里就是**一个编辑器实例**（同一套 `EditorPanel`），只是：
 *
 * | 差异 | 做法 |
 * | --- | --- |
 * | 工具栏「加到图表 / 只读叠加 / 策略管理 / 策略回测 / 参数优化 / 策略实盘 / 停止实盘 / 帮助」 | 隐藏（`variant: 'pi'`） |
 * | 编辑器 / 资源管理器右键里的「加到图表」 | 隐藏 |
 * | 左栏默认 | 打开 **PI 会话**（不是资源管理器） |
 * | 右侧没有会话时 | 显示**初始化页**（不是页签；一发送就新建会话 ✓） |
 *
 * 入口：首页工作区（预警中心下面）+ 顶栏「＋ → PI 助手」。
 */
import { EditorPanel } from './editor-panel';

export interface PiPageOptions {
    theme: 'light' | 'dark';
    version?: string;
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string, actions?: unknown[],
               detail?: string, placement?: 'bottom' | 'top') => void;
    lsp?: () => {
        url: string; root: string;
        minibtPath?: string; sysPathCount?: number;
    } | undefined;
    formatOnSave?: boolean;
    /** pi（命令行）版本，`pi --version`（和 minibt 版本不是一回事 ✓） */
    piVersion?: string;
    /** 上次用的目录（`settings.pi_root`；空 = 用后端默认 ✓） */
    rootHint?: string;
}

export class PiPage {
    readonly element: HTMLDivElement;
    readonly editorPanel: EditorPanel;
    private readonly options: PiPageOptions;

    constructor(options: PiPageOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = 'desk-pi-page';
        this.editorPanel = new EditorPanel({
            theme: options.theme,
            variant: 'pi',
            onCommand: (cmd, payload) => options.onCommand(cmd, payload),
            onToast: (level, text, _actions, _detail, placement) => {
                options.onToast?.(level, text, undefined, undefined,
                                  placement === 'top' ? 'top' : 'bottom');
            },
            lsp: () => options.lsp?.(),
            formatOnSave: options.formatOnSave,
            // ★ 初始化页右上角版本号：desk = minibt、pi = pi CLI（1.5.1 ✓）
            version: options.version,
            piVersion: options.piVersion,
            allowLive: false,
            // ★ 目录独立：PI 页有自己的 `pi_root`（和资源管理器分开 ✓）
            piRoot: true,
            rootHint: options.rootHint || '',
        });
        this.element.appendChild(this.editorPanel.element);
    }

    show(): void {
        this.element.style.display = 'flex';
        this.editorPanel.show();
    }

    hide(): void { this.element.style.display = 'none'; }

    destroy(): void {
        this.editorPanel.element.remove();
        this.element.remove();
    }

    applyTheme(theme: 'light' | 'dark'): void {
        this.options.theme = theme;
        this.editorPanel.setTheme(theme);
    }

    /** 兼容图表页的接口（app.ts 里统一调 `setSettings` ✓） */
    setSettings(values: Record<string, unknown>): void {
        const font = Number(values.editor_font_size || 0);
        if (font) this.editorPanel.setFontSize(font);
        this.editorPanel.setFormatOnSave(
            values.editor_format_on_save === true);
    }

    /** 兼容：图表页用 `openEditor()` 切到编辑器 ✓ */
    openEditor(): void { this.show(); }
}
