/** Floating menu shared by the quote page (right click) and the chart toolbar. */

export interface MenuItem {
    label: string;
    /** greyed-out + not clickable */
    disabled?: boolean;
    /** draw a divider above this item */
    separator?: boolean;
    run?: () => void;
    /** 行尾的 ✕（删除这条记录等，不会触发 `run` ✓） */
    onDelete?: () => void;
    /** **二级子菜单**（有它就渲染成 `标签 ›`，hover / 点击展开 ✓） */
    submenu?: MenuItem[];
}

let current: HTMLDivElement | null = null;
/** 一级菜单行 → 它展开的二级菜单（**按行登记**，收起才不会漏 ✓） */
const subMenus = new Map<HTMLElement, HTMLDivElement>();
let dismissHandler: ((event: MouseEvent) => void) | null = null;

/** 收起某一行的二级菜单 ✓ */
function closeSub(owner: HTMLElement): void {
    const node = subMenus.get(owner);
    if (!node) return;
    node.remove();
    subMenus.delete(owner);
}

/** 只留 `keep` 那一行（`null` = 全收）✓ */
function closeSubsExcept(keep: HTMLElement | null): void {
    for (const [owner, node] of Array.from(subMenus)) {
        if (keep && owner === keep) continue;
        node.remove();
        subMenus.delete(owner);
    }
}

const subNodes = (): HTMLDivElement[] => Array.from(subMenus.values());

export function closeMenu(): void {
    if (dismissHandler) {
        document.removeEventListener('mousedown', dismissHandler);
        dismissHandler = null;
    }
    closeSubsExcept(null);
    current?.remove();
    current = null;
}

/**
 * 画一个菜单（`items` → DOM），返回容器 ✓
 *
 * 二级子菜单：`item.submenu` 存在时这一行右边画 `›`，hover / 点击展开一层
 * （周期菜单的 秒 / 分 / 时 / 天 就是这种结构 ✓）。
 */
function buildMenu(items: MenuItem[], className = 'desk-menu',
                  depth = 0): HTMLDivElement {
    const menu = document.createElement('div');
    menu.className = className;
    for (const item of items) {
        if (item.separator) {
            const line = document.createElement('div');
            line.className = 'desk-menu-sep';
            menu.appendChild(line);
        }
        const row = document.createElement('div');
        row.className = 'desk-menu-item';
        const text = document.createElement('span');
        text.className = 'desk-menu-label';
        text.textContent = item.label;
        row.appendChild(text);

        if (item.submenu && item.submenu.length) {
            row.classList.add('has-submenu');
            const arrow = document.createElement('span');
            arrow.className = 'desk-menu-arrow';
            arrow.textContent = '›';
            row.appendChild(arrow);
            if (item.disabled) row.classList.add('disabled');
            // ★ 悬停状态自己记（不用 `:hover`：菜单可能在 Qt webview 里，
            //   而且测试用的 DOM stub 也没有 matches() ✓）
            let rowHover = false;
            let subHover = false;
            let hideTimer = 0;
            const scheduleHide = () => {
                window.clearTimeout(hideTimer);
                hideTimer = window.setTimeout(() => {
                    if (rowHover || subHover) return;
                    closeSub(row);
                }, 160);
            };
            const openSub = () => {
                window.clearTimeout(hideTimer);
                if (subMenus.get(row)) return;
                closeSubsExcept(row);          // 同时只留一个二级菜单 ✓
                const sub = buildMenu(item.submenu!,
                                      'desk-menu desk-menu-sub', depth + 1);
                document.body.appendChild(sub);
                subMenus.set(row, sub);
                const box = row.getBoundingClientRect();
                const size = sub.getBoundingClientRect();
                const left = Math.min(box.right + 2,
                                      window.innerWidth - size.width - 6);
                const top = Math.min(box.top - 6,
                                     window.innerHeight - size.height - 6);
                sub.style.left = `${Math.max(6, left)}px`;
                sub.style.top = `${Math.max(6, top)}px`;
                // ★ 鼠标**离开二级菜单本身**也要收（用户实测 2026-11-17：
                //   以前只有一级行有 mouseleave，子菜单一展开就再也收不起来 ✗）
                sub.addEventListener('mouseenter', () => {
                    subHover = true;
                    window.clearTimeout(hideTimer);
                });
                sub.addEventListener('mouseleave', () => {
                    subHover = false;
                    scheduleHide();
                });
            };
            row.addEventListener('mouseenter', () => {
                rowHover = true;
                openSub();
            });
            row.addEventListener('mouseleave', () => {
                rowHover = false;
                scheduleHide();
            });
            row.addEventListener('click', (event) => {
                event.stopPropagation();
                if (subMenus.get(row)) closeSub(row);
                else openSub();
            });
        } else if (item.disabled) {
            row.classList.add('disabled');
        } else {
            row.addEventListener('click', () => {
                closeMenu();
                item.run?.();
            });
        }

        // ★ 移到**一级菜单的别的行**（尤其是不带子菜单的行）就把已展开的
        //   二级菜单收掉，否则「已保存的布局」多了会一直挡住下面的
        //   「布局管理…」等菜单项（用户实测 2026-11-17 ✗）。
        //   ⚠ 只在 `depth === 0` 上挂：二级菜单**自己的行**也挂的话，鼠标一进
        //   子菜单里任意一项就把父级子菜单收了 → 又立刻重新展开 → 菜单疯狂
        //   闪烁（用户实测 2026-11-17 第二次反馈 ✗）。
        if (depth === 0 && !row.classList.contains('has-submenu')) {
            row.addEventListener('mouseenter', () => closeSubsExcept(null));
        }

        if (item.onDelete) {
            const remove = document.createElement('button');
            remove.className = 'desk-menu-remove';
            remove.textContent = '✕';
            remove.title = '删除这条记录（文件不会删）';
            remove.addEventListener('click', (event) => {
                event.stopPropagation();       // 别触发 run ✓
                closeMenu();
                item.onDelete?.();
            });
            row.appendChild(remove);
        }
        menu.appendChild(row);
    }
    return menu;
}

/** Show `items` at viewport coordinates (keeps the menu inside the window). */
export function showMenu(x: number, y: number, items: MenuItem[]): void {
    closeMenu();
    const menu = buildMenu(items);
    document.body.appendChild(menu);
    current = menu;

    const box = menu.getBoundingClientRect();
    const left = Math.min(x, window.innerWidth - box.width - 6);
    const top = Math.min(y, window.innerHeight - box.height - 6);
    menu.style.left = `${Math.max(6, left)}px`;
    menu.style.top = `${Math.max(6, top)}px`;

    const dismiss = (event: MouseEvent) => {
        const node = event.target as Node;
        if (current && !current.contains(node)
            && !subNodes().some((sub) => sub.contains(node))) {
            closeMenu();
            document.removeEventListener('mousedown', dismiss);
        }
    };
    dismissHandler = dismiss;
    document.addEventListener('mousedown', dismiss);
}

/** Same menu, anchored under a toolbar button. */
export function showMenuBelow(anchor: HTMLElement, items: MenuItem[]): void {
    const box = anchor.getBoundingClientRect();
    showMenu(box.left, box.bottom + 2, items);
}
