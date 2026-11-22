/**
 * minibt desk app entry point (quote window + chart window, all TS).
 *
 * Bundled to `desk.js` (IIFE, global `Desk`) and loaded by `desk.html`:
 *
 *     <script src="./lightweight-charts.js"></script>
 *     <script src="./desk.js"></script>
 *
 * Hosts:
 *   - Qt        `minibt.desk.app.DeskWindow`  (QWebChannel)
 *   - browser   `minibt.desk.web`             (SSE + POST /callback)
 *   - minibt-charts / tests                   (bring your own DeskTransport)
 */
import { DeskApp, registerDesk } from './app';
import { PiFloat } from './pi-float';
import { mountDesk } from './sdk';
import { detectTransport, MockTransport, RestTransport, SseTransport, QtTransport } from './transport';

declare global {
    interface Window {
        __desk?: DeskApp;
        __deskConfig?: Record<string, unknown>;
    }
}

const config = (window.__deskConfig || {}) as Record<string, any>;

/** 独立浮窗（`desk.html?pi=float`）：整页只放 AI 悬浮窗 ✓ */
const FLOAT_MODE = /(?:^|[?&])pi=float/.test(window.location.search)
    || config.float === true;

const app = new DeskApp({
    theme: config.theme === 'light' ? 'light' : 'dark',
    title: config.title,
    transport: detectTransport(config as never),
});

registerDesk(app);

function startFloat(): void {
    const transport = detectTransport(config as never);
    const theme = config.theme === 'light' ? 'light' : 'dark';
    const float = new PiFloat({
        theme,
        onCommand: (cmd: string, payload?: unknown) =>
            transport.send({ cmd, payload }),
        onToast: (level: string, text: string) => {
            // 独立窗口没有 toast 壳 → 先打印（需要时再加小提示 ✓）
            // eslint-disable-next-line no-console
            console.log(`[pi-float] ${level}: ${text}`);
        },
        onOpenSession: (id: string) => {
            transport.send({ cmd: 'pi_open_session_hint',
                             payload: { id } });
        },
        onModels: () => transport.send({ cmd: 'pi_models', payload: {} }),
    });
    // 独立窗口：铺满、无拖拽（系统标题栏搬动），隐藏收起图标 ✓
    document.body.classList.add('desk-float-detached');
    const host = document.getElementById('desk') || document.body;
    host.appendChild(float.element);
    host.appendChild(float.icon);
    float.element.classList.add('desk-pi-float-max');
    float.element.style.display = 'flex';
    float.icon.style.display = 'none';
    // 独立窗口不吃「贴边收起」→ 隐藏钉住按钮 ✓
    float.element.querySelectorAll('.desk-pi-float-btn').forEach((button) => {
        if (button.textContent === '📍' || button.textContent === '📌') {
            (button as HTMLElement).style.display = 'none';
        }
    });
    // 后端补丁 → 直接喂给悬浮窗 ✓
    (window as unknown as { __desk: unknown }).__desk = {
        applyPatch: (patch: Record<string, unknown>) => float.piOnPatch(patch),
    };
    (window as unknown as { __deskFloat?: PiFloat }).__deskFloat = float;
    // ★ 独立小窗（`?pi=float`）里当然要**直接显示对话窗口**（不是小球 ✓）
    float.openCard();
}

function start(): void {
    if (FLOAT_MODE) {
        startFloat();
        return;
    }
    const host = document.getElementById('desk') || document.body;
    app.mount(host as HTMLElement);
    app.boot();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
} else {
    start();
}

export {
    DeskApp, registerDesk, detectTransport, mountDesk,
    MockTransport, RestTransport, SseTransport, QtTransport,
};
