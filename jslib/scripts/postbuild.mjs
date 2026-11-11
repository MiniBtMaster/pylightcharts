// Copies build artifacts into the python package.
// Layout produced in pylightcharts/js/:
//   bundle.js               - our bridge + drawing plugins (IIFE, global `Lib`)
//   lightweight-charts.js   - upstream standalone build (global `LightweightCharts`)
//   styles.css              - chart UI styles
//   index.html              - the webview host page
import { createHash } from 'node:crypto';
import { copyFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url)); // jslib/scripts
const jslib = resolve(here, '..');
const target = resolve(jslib, '..', 'pylightcharts', 'js');

const LWC_STANDALONE = resolve(
  jslib,
  'node_modules', 'lightweight-charts', 'dist',
  'lightweight-charts.standalone.production.js',
);

const INDEX_HTML = `<!DOCTYPE html>
<html lang="">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>pylightcharts</title>
    <link rel="stylesheet" href="./styles.css">
    <script src="./lightweight-charts.js"></script>
    <style>
    body { margin: 0; padding: 0; overflow: hidden; background: #000; }
    </style>
</head>
<body>
    <div id="container"></div>
    <script src="./bundle.js"></script>
</body>
</html>
`;

const steps = [
  ['bundle.js', resolve(jslib, 'dist', 'bundle.js')],
  ['styles.css', resolve(jslib, 'src', 'general', 'styles.css')],
  ['lightweight-charts.js', LWC_STANDALONE],
  // minibt desk（报价 + 看盘）：脚本 + 样式 + 宿主页
  ['desk.js', resolve(jslib, 'dist', 'desk.js')],
  // 编辑器（CodeMirror）：懒加载，点「代码」页签才下载 ✓
  ['desk-editor.js', resolve(jslib, 'dist', 'desk-editor.js')],
  ['desk.css', resolve(jslib, 'src', 'desk', 'desk.css')],
  ['desk.html', resolve(jslib, 'src', 'desk', 'desk.html')],
];

await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });

// ★ 行尾统一成 LF：`.gitattributes` 里源码是 `eol=lf`，但 `pylightcharts/js/*`
//   是 `-text`（字节级比对）。Windows 工作区里源码是 CRLF → 直接拷过去产物
//   也是 CRLF，而 Linux（CI）拷出来是 LF → `git diff --exit-code --
//   pylightcharts/js` 永远红。这里对**文本**产物强制 LF，两边构建字节一致 ✓
const TEXT_ASSETS = new Set(['styles.css', 'desk.css', 'desk.html']);

for (const [name, from] of steps) {
  const to = resolve(target, name);
  await copyFile(from, to);
  if (TEXT_ASSETS.has(name)) {
    const text = await readFile(to, 'utf8');
    const normalised = text.replace(/\r\n/g, '\n');
    if (normalised !== text) await writeFile(to, normalised, 'utf8');
  }
  console.log(`[pylightcharts] copied ${name}`);
}

// ★ 缓存击穿：desk.html 里的 desk.js / desk.css 带上构建版本号 ——
//   QtWebEngine 会把 file:// 的 JS/CSS 缓存住，改了 bundle 还跑老代码（✗），
//   加 `?v=<时间戳>` 每次构建都强制重新加载 ✓
// ★ 以前是 `Date.now().toString(36)`：每次构建 desk.html 都变 →
//   CI 的「产物是否最新」检查（`git diff -- pylightcharts/js`）**永远不可能通过** ✗
//   改成 **desk.js + desk.css 内容哈希**：内容不变 → 字节不变（可复现构建），
//   内容一变 → 版本号自动变，缓存击穿照样有效 ✓
const digest = createHash('sha256');
for (const name of ['desk.js', 'desk.css']) {
  digest.update(await readFile(resolve(target, name)));
}
const stamp = digest.digest('hex').slice(0, 8);
const deskHtmlPath = resolve(target, 'desk.html');
let deskHtml = await readFile(deskHtmlPath, 'utf8');
// ⚠ 以前只在**没有** `?v=` 时才替换 → 第一次之后就把 token 冻住了，
//   之后每次构建 desk.html 的版本号都不变 → QtWebEngine 继续用**缓存里的旧
//   desk.js**，改了前端"永远不生效"（用户实测 ✗）。这里连旧 token 一起换 ✓
deskHtml = deskHtml
  .replace(/\.\/desk\.css(\?v=[^"]*)?/, `./desk.css?v=${stamp}`)
  .replace(/\.\/desk\.js(\?v=[^"]*)?/, `./desk.js?v=${stamp}`);
await writeFile(deskHtmlPath, deskHtml, 'utf8');
console.log(`[pylightcharts] desk.html cache-bust v=${stamp}`);

await writeFile(resolve(target, 'index.html'), INDEX_HTML, 'utf8');
console.log('[pylightcharts] wrote index.html');
console.log(`[pylightcharts] build complete -> ${target}`);
