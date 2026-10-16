// Copies build artifacts into the python package.
// Layout produced in pylightcharts/js/:
//   bundle.js               - our bridge + drawing plugins (IIFE, global `Lib`)
//   lightweight-charts.js   - upstream standalone build (global `LightweightCharts`)
//   styles.css              - chart UI styles
//   index.html              - the webview host page
import { copyFile, mkdir, rm, writeFile } from 'node:fs/promises';
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
];

await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });

for (const [name, from] of steps) {
  await copyFile(from, resolve(target, name));
  console.log(`[pylightcharts] copied ${name}`);
}

await writeFile(resolve(target, 'index.html'), INDEX_HTML, 'utf8');
console.log('[pylightcharts] wrote index.html');
console.log(`[pylightcharts] build complete -> ${target}`);
