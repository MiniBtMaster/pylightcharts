/**
 * PiModels —— 「模型」对话框（v1.3.7-9），复刻 `Pi-Agent-Web-main`
 * 的 `ModelsConfig.tsx`（`模型.png` / `模型供应商.png`）：
 *
 *   ┌ 模型  ~/.minibt/ai/models.json                        ✕ ┐
 *   │ ┌ 供应商 ─────┐ ┌ API KEY               ● 已配置        ┐ │
 *   │ │ ● DeepSeek  │ │ Key 已保存，可替换 / 断开…             │ │
 *   │ │ …           │ │ [输入新 Key …………  👁] [保存]           │ │
 *   │ │ ＋添加提供商 │ │ [断开连接]                             │ │
 *   │ └─────────────┘ └───────────────────────────────────────┘ │
 *   │                                       [取消] [保存]        │
 *   └────────────────────────────────────────────────────────────┘
 *
 * 「添加提供商」是 pi 那张供应商网格（自定义 / 订阅 / API KEY 分组）。
 */
import { esc, PI_PROVIDERS } from './pi-util';

export interface PiModelsOptions {
    theme: 'light' | 'dark';
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string) => void;
}

interface ProviderRow {
    id: string;
    label: string;
    base?: string;
    models?: string[];
    kind?: string;
    configured?: boolean;
}

export class PiModelsDialog {
    readonly element: HTMLDivElement;
    private readonly options: PiModelsOptions;
    private readonly list: HTMLDivElement;
    private readonly body: HTMLDivElement;
    private readonly title: HTMLElement;
    private providers: ProviderRow[] = [];
    private data: Record<string, unknown> = {};
    private active = '';
    private pickerOpen = false;
    private offline = false;
    private offlineText = '';
    private pingBox: HTMLDivElement | null = null;
    /** 高级限制（模型对话框底部 ✓） */
    private limits: Record<string, number> = {};
    private advBox: HTMLDivElement | null = null;
    private offlineBox: HTMLDivElement | null = null;

    constructor(options: PiModelsOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = 'desk-pi-mask';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'desk-pi-dialog desk-pi-models';
        const head = document.createElement('div');
        head.className = 'desk-pi-dialog-head';
        const label = document.createElement('span');
        label.textContent = '模型';
        this.title = document.createElement('code');
        this.title.className = 'desk-pi-path';
        this.title.textContent = '~/.minibt/ai/models.json';
        const close = document.createElement('button');
        close.className = 'desk-pi-x';
        close.textContent = '✕';
        close.addEventListener('click', () => this.close());
        head.append(label, this.title, close);

        this.offlineBox = document.createElement('div');
        this.offlineBox.className = 'desk-pi-offline';
        this.offlineBox.style.display = 'none';
        const content = document.createElement('div');
        content.className = 'desk-pi-models-body';
        this.list = document.createElement('div');
        this.list.className = 'desk-pi-providers';
        this.body = document.createElement('div');
        this.body.className = 'desk-pi-model-panel';
        content.append(this.list, this.body);

        // ★ 底部「高级」限制条（工具轮数 / 命令超时 / 工具输出 / 上下文窗口）✓
        this.advBox = document.createElement('div');
        this.advBox.className = 'desk-pi-advanced';

        const foot = document.createElement('div');
        foot.className = 'desk-pi-dialog-foot';
        const cancel = document.createElement('button');
        cancel.className = 'desk-pi-btn';
        cancel.textContent = '取消';
        cancel.addEventListener('click', () => this.close());
        const save = document.createElement('button');
        save.className = 'desk-pi-btn primary';
        save.textContent = '保存';
        save.addEventListener('click', () => this.save());
        foot.append(cancel, save);

        box.append(head, this.offlineBox, content, this.advBox, foot);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
        document.body.appendChild(this.element);
    }

    open(): void {
        this.element.style.display = '';
        this.pickerOpen = false;
        // ★ 先用「缓存 / 内置目录」画一遍：后端慢或没回包时也不留白 ✓
        if (!this.providers.length) {
            this.providers = PI_PROVIDERS.map((row) => ({ ...row }));
        }
        this.renderList();
        this.renderBody();
        this.offline = false;
        this.renderOffline();
        this.options.onCommand('pi_models', {});
    }

    /** 后端 1.5 秒没回 `pi_models` → 顶部给一句明确提示 ✓ */
    setOffline(text = ''): void {
        this.offline = true;
        this.offlineText = text || ('后端没有响应 pi_models —— 确认用 '
            + '`python -m minibt desk` 启动（仓库版 ≥ 1.3.7），'
            + '或重装本地包 `pip install -e .`。下面仍可填 Key 并保存 ✓');
        this.renderOffline();
    }

    private renderOffline(): void {
        if (!this.offlineBox) return;
        this.offlineBox.textContent = this.offline ? `⚠ ${this.offlineText}` : '';
        this.offlineBox.style.display = this.offline ? '' : 'none';
    }

    close(): void {
        this.element.style.display = 'none';
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    setData(patch: Record<string, unknown>): void {
        this.offline = false;
        this.renderOffline();
        this.data = (patch.models || {}) as Record<string, unknown>;
        const rows = (patch.providers || []) as ProviderRow[];
        this.providers = rows.length ? rows
            : PI_PROVIDERS.map((row) => ({ ...row }));
        if (patch.file) this.title.textContent = String(patch.file);
        const active = (patch.active || {}) as Record<string, unknown>;
        if (!this.active) this.active = String(active.provider || '');
        if (!this.providers.some((row) => row.id === this.active)) {
            this.active = this.providers[0]?.id || '';
        }
        const limits = (patch.limits || {}) as Record<string, unknown>;
        this.limits = {
            turns: Number(limits.turns || 12),
            timeout: Number(limits.timeout || 25),
            output: Number(limits.output || 8000),
            read: Number(limits.read || 60000),
            window: Number(limits.window || 0),
        };
        this.renderAdvanced();
        if (!this.visible) return;
        this.renderList();
        this.renderBody();
    }

    // ------------------------------------------------------------- 渲染
    private renderList(): void {
        this.list.textContent = '';
        for (const row of this.providers) {
            const item = document.createElement('button');
            item.className = 'desk-pi-provider'
                + (row.id === this.active ? ' on' : '');
            item.innerHTML = `<i></i><span>${esc(row.label)}</span>`;
            item.title = `${row.base || ''}`;
            item.addEventListener('click', () => {
                this.active = row.id;
                this.pickerOpen = false;
                this.renderList();
                this.renderBody();
            });
            this.list.appendChild(item);
        }
        const add = document.createElement('button');
        add.className = 'desk-pi-provider add';
        add.textContent = '＋ 添加提供商';
        add.addEventListener('click', () => {
            this.pickerOpen = true;
            this.renderBody();
        });
        this.list.appendChild(add);
    }

    private saved(id: string): Record<string, unknown> {
        const providers = (this.data.providers || {}) as Record<
            string, Record<string, unknown>>;
        return providers[id] || {};
    }

    private renderBody(): void {
        if (this.pickerOpen) {
            this.renderPicker();
            return;
        }
        const row = this.providers.find((item) => item.id === this.active);
        this.body.innerHTML = '';
        if (!row) {
            this.body.innerHTML = '<div class="desk-pi-empty">选一个供应商</div>';
            return;
        }
        const record = this.saved(row.id);
        const key = String(record.apiKey || '');
        const base = String(record.base || row.base || '');
        const models = (record.models as string[] | undefined)
            || row.models || [];
        const isLocal = row.kind === 'local';

        const top = document.createElement('div');
        top.className = 'desk-pi-model-head';
        top.innerHTML = `<b>${esc(row.label)}</b>`
            + `<span class="${key || isLocal ? 'ok' : ''}">`
            + `${key || isLocal ? '● 已配置' : '○ 未配置'}</span>`;
        this.body.appendChild(top);

        // 接口地址
        this.body.appendChild(this.field('接口地址（OpenAI 兼容 /v1）',
            'base', base, 'https://api.deepseek.com/v1'));
        // API Key
        const status = document.createElement('div');
        status.className = 'desk-pi-model-desc';
        status.textContent = key
            ? 'API Key 已保存在本机。下面输入新 Key 可以替换，或点「断开连接」。'
            : (isLocal ? '本地服务通常不需要 Key（留空即可）。'
                : '还没填 API Key：填好后点「保存」。');
        this.body.appendChild(status);

        const keyRow = document.createElement('div');
        keyRow.className = 'desk-pi-key-row';
        const input = document.createElement('input');
        input.className = 'desk-pi-input-small';
        input.type = 'password';
        input.placeholder = '输入新 Key 进行替换…';
        input.value = '';
        const eye = document.createElement('button');
        eye.className = 'desk-pi-btn';
        eye.textContent = '👁';
        eye.title = '显示 / 隐藏';
        eye.addEventListener('click', () => {
            input.type = input.type === 'password' ? 'text' : 'password';
        });
        keyRow.append(input, eye);
        this.body.appendChild(keyRow);

        // 模型列表
        this.body.appendChild(this.field('模型（逗号分隔）', 'models',
            models.join(', '), 'deepseek-chat, deepseek-reasoner'));
        // ★ 明确告诉用户「对话将用哪个模型」（选了列表里没有的会自动退回第一个 ✓）
        const resolved = String((((this.data.active || {}) as Record<
            string, unknown>).provider) === row.id
            ? ((this.data.active || {}) as Record<string, unknown>).model || ''
            : '');
        const willUse = resolved || String(models[0] || '（未填模型）');
        const hint = document.createElement('div');
        hint.className = 'desk-pi-model-desc';
        const anthropic = /\/anthropic\/?$/i.test(base);
        hint.textContent = `对话将使用：${willUse}`
            + (anthropic
                ? '　⚠ 这个地址是 Anthropic 兼容端点，desk 只支持 OpenAI 兼容'
                    + '（DeepSeek 用 https://api.deepseek.com 即可）'
                : '');
        this.body.appendChild(hint);

        // 当前选择
        const active = (this.data.active || {}) as Record<string, unknown>;
        const isActive = String(active.provider || '') === row.id;
        const pick = document.createElement('label');
        pick.className = 'desk-pi-check';
        pick.innerHTML = `<input type="checkbox" ${isActive ? 'checked' : ''}>`
            + ' 设为当前使用的供应商';
        this.body.appendChild(pick);

        const actions = document.createElement('div');
        actions.className = 'desk-pi-actions';
        const saveKey = document.createElement('button');
        saveKey.className = 'desk-pi-btn primary';
        saveKey.textContent = '保存 Key';
        saveKey.addEventListener('click', () => {
            const value = input.value.trim();
            if (!value) {
                this.options.onToast?.('warning', '请输入 API Key');
                return;
            }
            // ★ 先把**当前输入框里的值**收进 data，再写 Key ——
            //   以前用渲染快照覆盖，会把用户刚改的地址 / 模型顶回默认值 ✗
            this.readFields(row);
            const target = this.saved(row.id);
            target.apiKey = value;
            target.label = row.label;
            this.putProvider(row.id, target);
            input.value = '';
            this.options.onToast?.('success',
                '已记住（地址 / 模型 / Key），点右下「保存」写入文件');
            this.renderList();
            this.renderBody();
        });
        const disconnect = document.createElement('button');
        disconnect.className = 'desk-pi-btn danger';
        disconnect.textContent = '断开连接';
        disconnect.addEventListener('click', () => {
            this.readFields(row);
            const target = this.saved(row.id);
            delete target.apiKey;
            this.putProvider(row.id, target);
            this.renderBody();
        });
        const ping = document.createElement('button');
        ping.className = 'desk-pi-btn';
        ping.textContent = '测试连接';
        ping.title = '用当前地址 / 模型 / Key 发一次 1-token 请求';
        ping.addEventListener('click', () => {
            this.readFields(row);
            const saved = this.saved(row.id);
            this.setPing({ pending: true });
            this.options.onCommand('ai_ping', {
                config: {
                    base: String(saved.base || row.base || ''),
                    model: String((saved.models as string[] | undefined)?.[0]
                        || ''),
                    key: String(saved.apiKey || ''),
                },
            });
        });
        actions.append(saveKey, disconnect, ping);
        this.body.appendChild(actions);

        this.pingBox = document.createElement('div');
        this.pingBox.className = 'desk-pi-model-desc';
        this.body.appendChild(this.pingBox);

        // 输入变化 → 直接写回内存（点「保存」才落盘 ✓）
        this.body.querySelectorAll('input[data-field]').forEach((element) => {
            const field = (element as HTMLInputElement).dataset.field || '';
            element.addEventListener('input', () => {
                const value = (element as HTMLInputElement).value;
                if (field === 'models') {
                    record.models = value.split(',').map((item) => item.trim())
                        .filter(Boolean);
                } else {
                    record[field] = value.trim();
                }
                record.label = row.label;
                this.putProvider(row.id, record);
            });
        });
        this.body.querySelector('input[type="checkbox"]')?.addEventListener(
            'change', (event) => {
                const checked = (event.target as HTMLInputElement).checked;
                this.readFields(row);
                const saved = this.saved(row.id);
                const list = (saved.models as string[] | undefined) || [];
                this.data.active = checked
                    ? { provider: row.id, model: String(list[0] || '') }
                    : { provider: '', model: '' };
            });
    }

    /** 底部「高级」：4 个下拉，改了立刻写进 data.limits（点「保存」落盘 ✓） */
    private renderAdvanced(): void {
        const box = this.advBox;
        if (!box) return;
        box.textContent = '';
        const label = document.createElement('span');
        label.className = 'desk-pi-advanced-title';
        label.textContent = '高级';
        label.title = '这些是 PI 助手的执行上限，改了记得点「保存」';
        box.appendChild(label);

        const pick = (name: string, title: string,
                      options: Array<[number, string]>) => {
            const wrap = document.createElement('label');
            wrap.className = 'desk-pi-advanced-item';
            wrap.title = title;
            const text = document.createElement('span');
            text.textContent = title;
            const select = document.createElement('select');
            select.className = 'desk-pi-advanced-select';
            for (const [value, name2] of options) {
                const option = document.createElement('option');
                option.value = String(value);
                option.textContent = name2;
                if (String(value) === String(this.limits[name] ?? '')) {
                    option.selected = true;
                }
                select.appendChild(option);
            }
            select.addEventListener('change', () => {
                this.limits[name] = Number(select.value);
                this.data.limits = { ...(this.data.limits || {}),
                                     ...this.limits };
            });
            wrap.append(text, select);
            box.appendChild(wrap);
        };

        pick('turns', '工具轮数', [[6, '6 轮'], [12, '12 轮（默认）'],
                                   [24, '24 轮'], [48, '48 轮']]);
        pick('timeout', '命令超时', [[25, '25 秒（默认）'], [60, '60 秒'],
                                     [120, '120 秒'], [300, '300 秒']]);
        pick('output', '工具输出', [[8000, '8000 字符（默认）'],
                                    [16000, '16000'],
                                    [32000, '32000'], [64000, '64000 字符']]);
        pick('window', '上下文窗口', [[0, '跟随模型'], [32000, '32k'],
                                      [64000, '64k'], [128000, '128k'],
                                      [256000, '256k']]);
    }

    /** 把「当前面板」里的输入框值读回 data（保存 / 动作前都先调 ✓） */
    private readFields(row: ProviderRow): void {
        const target = this.saved(row.id);
        this.body.querySelectorAll('input[data-field]').forEach((element) => {
            const input = element as HTMLInputElement;
            const field = input.dataset.field || '';
            if (!field) return;
            const value = input.value;
            if (field === 'models') {
                target.models = value.split(',')
                    .map((item) => item.trim()).filter(Boolean);
            } else {
                target[field] = value.trim();
            }
        });
        target.label = row.label;
        this.putProvider(row.id, target);
    }

    private field(label: string, field: string, value: string,
                  placeholder: string): HTMLDivElement {
        const box = document.createElement('div');
        box.className = 'desk-pi-field';
        const name = document.createElement('div');
        name.className = 'desk-pi-field-label';
        name.textContent = label;
        const input = document.createElement('input');
        input.className = 'desk-pi-input-small';
        input.dataset.field = field;
        input.value = value;
        input.placeholder = placeholder;
        input.spellcheck = false;
        box.append(name, input);
        return box;
    }

    private renderPicker(): void {
        this.body.innerHTML = '';
        const title = document.createElement('div');
        title.className = 'desk-pi-model-head';
        title.innerHTML = '<b>添加提供商</b><span>选一个，填 Key 即可</span>';
        this.body.appendChild(title);
        const grid = document.createElement('div');
        grid.className = 'desk-pi-provider-grid';
        const groups: Array<[string, ProviderRow[]]> = [
            ['自定义', this.providers.filter((row) => row.kind === 'custom')],
            ['API KEY', this.providers.filter((row) => row.kind !== 'custom'
                && row.kind !== 'local')],
            ['本地', this.providers.filter((row) => row.kind === 'local')],
        ];
        for (const [label, rows] of groups) {
            if (!rows.length) continue;
            const head = document.createElement('div');
            head.className = 'desk-pi-grid-group';
            head.textContent = label;
            grid.appendChild(head);
            for (const row of rows) {
                const card = document.createElement('button');
                card.className = 'desk-pi-provider-card';
                card.innerHTML = `<b>${esc(row.label)}</b>`
                    + `<span>${(row.models || []).length} 个模型`
                    + `${row.configured ? ' · 已配置' : ''}</span>`;
                card.addEventListener('click', () => {
                    this.active = row.id;
                    this.pickerOpen = false;
                    this.renderList();
                    this.renderBody();
                });
                grid.appendChild(card);
            }
        }
        this.body.appendChild(grid);
    }

    /** 「测试连接」结果（后端 `ai_ping` ✓） */
    setPing(patch: Record<string, unknown>): void {
        if (!this.pingBox) return;
        if (patch.pending) {
            this.pingBox.textContent = '正在测试连接…';
            return;
        }
        if (patch.ok) {
            this.pingBox.textContent = `✔ 连接正常（${String(patch.model || '')}`
                + ` · ${Number(patch.ms || 0)} ms）`;
            this.options.onToast?.('success', '连接正常');
            return;
        }
        this.pingBox.textContent = `✘ ${String(patch.error || '连接失败')}`;
        this.options.onToast?.('warning',
            `连接失败：${String(patch.error || '')}`);
    }

    // ------------------------------------------------------------- 数据
    private putProvider(id: string, record: Record<string, unknown>): void {
        const providers = (this.data.providers || {}) as Record<
            string, Record<string, unknown>>;
        providers[id] = { ...(providers[id] || {}), ...record };
        this.data.providers = providers;
    }

    private save(): void {
        this.data.limits = { ...(this.data.limits || {}), ...this.limits };
        // ★ 落盘前把当前输入框的值全部收进 data（手快直接点保存也不丢 ✓）
        const row = this.providers.find((item) => item.id === this.active);
        if (row) this.readFields(row);
        const active = (this.data.active || {}) as Record<string, unknown>;
        if (!active.provider && row) {
            const saved = this.saved(row.id);
            const list = (saved.models as string[] | undefined) || [];
            if (saved.apiKey) {
                this.data.active = { provider: row.id,
                                     model: String(list[0] || '') };
            }
        }
        this.options.onCommand('pi_models_save', { models: this.data });
        this.options.onToast?.('success', '模型配置已保存');
        this.close();
    }
}
