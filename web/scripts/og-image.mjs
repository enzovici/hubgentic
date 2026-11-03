// Renders public/img/og-pmi.png (1200x630): logo plus the H1 on white, in the site fonts.
// Uses the Playwright Chromium available locally. Run `npm run assets` first so the logo exists.
// Usage: npm run og
import { chromium } from 'playwright';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const font = (f) => readFileSync(`${root}public/fonts/${f}`).toString('base64');
const logoPath = `${root}public/img/logo-full.png`;
const logo = existsSync(logoPath)
  ? `<img src="data:image/png;base64,${readFileSync(logoPath).toString('base64')}" alt="" style="height:96px">`
  : `<div style="font-family:Caladea;font-weight:700;font-size:64px;color:#0E1B2A">Hubgentic</div>`;

const html = `<!doctype html><html><head><style>
@font-face{font-family:Caladea;font-weight:700;src:url(data:font/woff2;base64,${font('caladea-700.woff2')}) format('woff2')}
@font-face{font-family:Lato;font-weight:700;src:url(data:font/woff2;base64,${font('lato-700.woff2')}) format('woff2')}
html,body{margin:0;width:1200px;height:630px;background:#fff}
.wrap{box-sizing:border-box;height:630px;padding:84px 96px;display:flex;flex-direction:column;justify-content:space-between;border-bottom:16px solid #0E1B2A}
h1{font-family:Caladea;font-weight:700;font-size:76px;line-height:1.1;color:#16212C;margin:0;max-width:960px}
.bar{width:96px;height:6px;background:#C8A24A;margin-bottom:28px}
.url{font-family:Lato;font-weight:700;font-size:26px;color:#2E6E73}
</style></head><body><div class="wrap">
<div>${logo}</div>
<div><div class="bar"></div><h1>L'AI che lavora davvero nella vostra azienda</h1></div>
<div class="url">agentic.ai/pmi</div>
</div></body></html>`;

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
await page.setContent(html);
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: `${root}public/img/og-pmi.png` });
await browser.close();
console.log('Wrote public/img/og-pmi.png');
