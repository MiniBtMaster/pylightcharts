/** PI 面板共用的小工具（HTML 转义 ✓） */
export function esc(value: unknown): string {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch] || ch));
}

/** 路径缩短成 `…/最后两段`（会话面板的项目路径 ✓） */
export function shortPath(path: string, keep = 2, limit = 26): string {
    const value = String(path || '');
    if (value.length <= limit) return value;
    const parts = value.split(/[\/]/).filter(Boolean);
    const tail = parts.slice(-keep).join('/');
    return `…/${tail}`;
}

/** 时间戳 → `3 分钟前` / `2026/11/08` ✓ */
export function whenText(value?: number): string {
    const stamp = Number(value || 0);
    if (!stamp) return '';
    const date = new Date(stamp * 1000);
    if (Number.isNaN(date.getTime())) return '';
    const diff = (Date.now() - date.getTime()) / 1000;
    if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))} 分钟前`;
    if (diff < 86400) return `${Math.round(diff / 3600)} 小时前`;
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${date.getFullYear()}/${month}/${day}`;
}

/** 供应商目录（和后端 `pi.PROVIDERS` 对齐；后端没回包时前端也能画 ✓） */
export interface PiProvider {
    id: string;
    label: string;
    base: string;
    models: string[];
    kind: 'api-key' | 'local' | 'custom';
}

export const PI_PROVIDERS: PiProvider[] = [
    { id: 'deepseek', label: 'DeepSeek', kind: 'api-key',
      base: 'https://api.deepseek.com/v1',
      models: ['deepseek-chat', 'deepseek-reasoner'] },
    { id: 'openai', label: 'OpenAI', kind: 'api-key',
      base: 'https://api.openai.com/v1',
      models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1-mini', 'o3-mini'] },
    { id: 'anthropic', label: 'Anthropic / 兼容', kind: 'api-key',
      base: '', models: [] },
    { id: 'dashscope', label: '通义千问（DashScope）', kind: 'api-key',
      base: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      models: ['qwen-plus', 'qwen-max'] },
    { id: 'moonshot', label: 'Moonshot AI', kind: 'api-key',
      base: 'https://api.moonshot.cn/v1',
      models: ['moonshot-v1-8k', 'kimi-k2-0905-preview'] },
    { id: 'groq', label: 'Groq', kind: 'api-key',
      base: 'https://api.groq.com/openai/v1',
      models: ['llama-3.3-70b-versatile'] },
    { id: 'openrouter', label: 'OpenRouter', kind: 'api-key',
      base: 'https://openrouter.ai/api/v1',
      models: ['openai/gpt-4o-mini', 'deepseek/deepseek-chat'] },
    { id: 'xai', label: 'xAI', kind: 'api-key',
      base: 'https://api.x.ai/v1', models: ['grok-2-latest'] },
    { id: 'together', label: 'Together AI', kind: 'api-key',
      base: 'https://api.together.xyz/v1', models: [] },
    { id: 'ollama', label: 'Ollama（本地）', kind: 'local',
      base: 'http://127.0.0.1:11434/v1',
      models: ['qwen2.5-coder:7b', 'llama3.1:8b'] },
    { id: 'lmstudio', label: 'LM Studio（本地）', kind: 'local',
      base: 'http://127.0.0.1:1234/v1', models: [] },
    { id: 'custom', label: '自定义 OpenAI / Anthropic 兼容', kind: 'custom',
      base: '', models: [] },
];
