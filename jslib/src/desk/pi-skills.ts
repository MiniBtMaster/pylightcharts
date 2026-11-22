/**
 * PiSkills —— 「技能」对话框（v1.3.7-9），复刻 `Pi-Agent-Web-main`
 * 的 `SkillsConfig.tsx`（`技能.png`）：
 *
 *   ┌ 技能  C:\...\pylightcharts                                ✕ ┐
 *   │ ┌ 已安装 ──────┐ ┌ 添加技能                              ┐ │
 *   │ │ ✔ minibt-xx  │ │ [ minibt                ] [搜索]       │ │
 *   │ │ 空           │ │ [全局] [项目]   → ~/.minibt/ai/skills/ │ │
 *   │ │              │ │ event-vip-management   6.6K installs   │ │
 *   │ │              │ │ …                        [安装]        │ │
 *   │ │ ＋添加技能    │ │                                       │ │
 *   │ └──────────────┘ └───────────────────────────────────────┘ │
 *   │                                                    [关闭]   │
 *   └────────────────────────────────────────────────────────────┘
 *
 * 安装用 **git clone**（`skills.sh` 的搜索走纯 HTTP），不需要 npm ✓
 */
import { esc } from './pi-util';

export interface PiSkillsOptions {
    theme: 'light' | 'dark';
    onCommand: (cmd: string, payload?: unknown) => void;
    onToast?: (level: string, text: string) => void;
}

interface SkillRow {
    name: string;
    folder: string;
    description?: string;
    enabled?: boolean;
    chars?: number;
}

export class PiSkillsDialog {
    readonly element: HTMLDivElement;
    private readonly options: PiSkillsOptions;
    private readonly installed: HTMLDivElement;
    private readonly results: HTMLDivElement;
    private readonly searchBox: HTMLInputElement;
    private readonly scopeBox: HTMLDivElement;
    private readonly dirLabel: HTMLElement;
    private rows: SkillRow[] = [];
    private scope: 'global' | 'project' = 'global';
    private searching = false;
    private searchButton: HTMLButtonElement | null = null;
    private searchTimer = 0;

    constructor(options: PiSkillsOptions) {
        this.options = options;
        this.element = document.createElement('div');
        this.element.className = 'desk-pi-mask';
        this.element.style.display = 'none';

        const box = document.createElement('div');
        box.className = 'desk-pi-dialog desk-pi-skills';
        const head = document.createElement('div');
        head.className = 'desk-pi-dialog-head';
        const label = document.createElement('span');
        label.textContent = '技能';
        this.dirLabel = document.createElement('code');
        this.dirLabel.className = 'desk-pi-path';
        this.dirLabel.textContent = '~/.minibt/ai/skills';
        const close = document.createElement('button');
        close.className = 'desk-pi-x';
        close.textContent = '✕';
        close.addEventListener('click', () => this.close());
        head.append(label, this.dirLabel, close);

        const content = document.createElement('div');
        content.className = 'desk-pi-skills-body';
        const left = document.createElement('div');
        left.className = 'desk-pi-installed';
        this.installed = document.createElement('div');
        this.installed.className = 'desk-pi-installed-list';
        const addLocal = document.createElement('button');
        addLocal.className = 'desk-pi-provider add';
        addLocal.textContent = '＋ 添加技能';
        addLocal.title = '从本地文件夹安装（里面有 SKILL.md）';
        addLocal.addEventListener('click', () => {
            const path = window.prompt('技能文件夹路径（含 SKILL.md）', '');
            if (!path) return;
            this.options.onCommand('pi_skills_install', { path });
        });
        left.append(this.installed, addLocal);

        const right = document.createElement('div');
        right.className = 'desk-pi-skills-main';
        const title = document.createElement('div');
        title.className = 'desk-pi-model-head';
        title.innerHTML = '<b>添加技能</b><span>从 skills.sh 搜索（git clone 安装）</span>';
        const searchRow = document.createElement('div');
        searchRow.className = 'desk-pi-search-row';
        this.searchBox = document.createElement('input');
        this.searchBox.className = 'desk-pi-input-small';
        this.searchBox.placeholder = '搜索技能包（如 minibt / papercraft）';
        this.searchBox.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') this.search();
        });
        const searchButton = document.createElement('button');
        searchButton.className = 'desk-pi-btn primary';
        searchButton.textContent = '搜索';
        searchButton.addEventListener('click', () => this.search());
        searchRow.append(this.searchBox, searchButton);
        this.searchButton = searchButton;

        this.scopeBox = document.createElement('div');
        this.scopeBox.className = 'desk-pi-scope';
        for (const [key, text] of [['global', '全局'], ['project', '项目']]) {
            const button = document.createElement('button');
            button.className = 'desk-pi-chip' + (key === 'global' ? ' on' : '');
            button.textContent = text;
            button.addEventListener('click', () => {
                this.scope = key as 'global' | 'project';
                this.renderScope();
            });
            this.scopeBox.appendChild(button);
        }
        const hint = document.createElement('span');
        hint.className = 'desk-pi-scope-hint';
        hint.textContent = '→ ~/.minibt/ai/skills/';
        this.scopeBox.appendChild(hint);

        this.results = document.createElement('div');
        this.results.className = 'desk-pi-results';
        right.append(title, searchRow, this.scopeBox, this.results);

        content.append(left, right);
        const foot = document.createElement('div');
        foot.className = 'desk-pi-dialog-foot';
        const closeButton = document.createElement('button');
        closeButton.className = 'desk-pi-btn';
        closeButton.textContent = '关闭';
        closeButton.addEventListener('click', () => this.close());
        foot.appendChild(closeButton);

        box.append(head, content, foot);
        this.element.appendChild(box);
        this.element.addEventListener('mousedown', (event) => {
            if (event.target === this.element) this.close();
        });
        document.body.appendChild(this.element);
    }

    open(): void {
        this.element.style.display = '';
        this.results.textContent = '';
        this.options.onCommand('pi_skills', {});
    }

    close(): void {
        this.element.style.display = 'none';
    }

    get visible(): boolean {
        return this.element.style.display !== 'none';
    }

    setSkills(patch: Record<string, unknown>): void {
        this.rows = (patch.items || []) as SkillRow[];
        if (patch.dir) this.dirLabel.textContent = String(patch.dir);
        if (patch.error) {
            this.options.onToast?.('warning', `安装失败：${patch.error}`);
        }
        if (!this.visible) return;
        this.renderInstalled();
        this.renderScope();
    }

    setSearch(patch: Record<string, unknown>): void {
        this.resetSearching();
        const items = (patch.items || []) as Array<Record<string, unknown>>;
        this.results.textContent = '';
        if (patch.ok === false) {
            const error = document.createElement('div');
            error.className = 'desk-pi-empty';
            error.textContent = `搜索不可用：${String(patch.error || '网络问题')}`
                + ' —— 可以用左边「＋ 添加技能」从本地文件夹安装';
            this.results.appendChild(error);
            return;
        }
        if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-pi-empty';
            empty.textContent = '（没有搜索结果）';
            this.results.appendChild(empty);
            return;
        }
        for (const item of items) {
            const row = document.createElement('div');
            row.className = 'desk-pi-result';
            const name = String(item.name || item.package || '');
            const packageName = String(item.package || name);
            row.innerHTML = `<div class="desk-pi-result-main">`
                + `<b>${esc(name)}</b>`
                + `<span>${esc(packageName)}`
                + `${item.installs ? ` · ${esc(item.installs)} installs` : ''}`
                + '</span></div>';
            const install = document.createElement('button');
            install.className = 'desk-pi-btn';
            install.textContent = '安装';
            install.addEventListener('click', () => {
                install.disabled = true;
                install.textContent = '安装中…';
                this.options.onCommand('pi_skills_install', {
                    package: packageName, scope: this.scope,
                });
                window.setTimeout(() => {
                    install.disabled = false;
                    install.textContent = '安装';
                }, 20000);
            });
            row.appendChild(install);
            this.results.appendChild(row);
        }
    }

    private search(): void {
        if (this.searching) return;
        const query = this.searchBox.value.trim();
        if (!query) {
            // ★ v1.3.7-103：空关键词以前**什么都不发生**（像点坏了 ✗）
            this.searchBox.focus();
            this.options.onToast?.('info', '先输入关键词再搜索（如 minibt）');
            return;
        }
        this.searching = true;
        this.searchBox.disabled = true;
        if (this.searchButton) {
            this.searchButton.disabled = true;
            this.searchButton.textContent = '搜索中…';
        }
        this.results.innerHTML = '<div class="desk-pi-empty">搜索中…</div>';
        this.options.onCommand('pi_skills_search', { query });
        // 网络卡住 / 后端没回 → 12 秒后复原，别让按钮永久变灰 ✗
        window.clearTimeout(this.searchTimer);
        this.searchTimer = window.setTimeout(() => this.resetSearching(), 12000);
    }

    /** 复原搜索按钮（拿到结果 / 超时都走这里 ✓） */
    private resetSearching(): void {
        window.clearTimeout(this.searchTimer);
        this.searching = false;
        this.searchBox.disabled = false;
        if (this.searchButton) {
            this.searchButton.disabled = false;
            this.searchButton.textContent = '搜索';
        }
    }

    private renderInstalled(): void {
        this.installed.textContent = '';
        if (!this.rows.length) {
            const empty = document.createElement('div');
            empty.className = 'desk-pi-empty';
            empty.textContent = '还没有安装技能 —— 右边搜一个，或点「＋ 添加技能」'
                + '从本地文件夹安装';
            this.installed.appendChild(empty);
            return;
        }
        for (const row of this.rows) {
            const item = document.createElement('div');
            item.className = 'desk-pi-skill';
            const name = document.createElement('div');
            name.className = 'desk-pi-skill-name';
            name.textContent = row.name;
            const desc = document.createElement('div');
            desc.className = 'desk-pi-skill-desc';
            desc.textContent = row.description || row.folder;
            const actions = document.createElement('div');
            actions.className = 'desk-pi-skill-actions';
            const toggle = document.createElement('button');
            toggle.className = 'desk-pi-chip' + (row.enabled ? ' on' : '');
            toggle.textContent = row.enabled ? '已启用' : '已停用';
            toggle.addEventListener('click', () => {
                this.options.onCommand('pi_skills_toggle', {
                    name: row.name, enabled: !row.enabled,
                });
            });
            const remove = document.createElement('button');
            remove.className = 'desk-pi-chip danger';
            remove.textContent = '删除';
            remove.addEventListener('click', () => {
                if (!window.confirm(`删除技能「${row.name}」？`)) return;
                this.options.onCommand('pi_skills_remove',
                                       { folder: row.folder });
            });
            actions.append(toggle, remove);
            item.append(name, desc, actions);
            this.installed.appendChild(item);
        }
    }

    private renderScope(): void {
        this.scopeBox.querySelectorAll('button').forEach((button, index) => {
            button.classList.toggle('on',
                (index === 0 ? 'global' : 'project') === this.scope);
        });
    }
}
