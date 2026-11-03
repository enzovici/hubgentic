// Builds the optimised logo and favicon set from the source logo.
// Usage: put Hubgentic_logo_light.png (755x170, transparent) in web/assets/, then `npm run assets`.
// Outputs are committed to public/img, so the Netlify build does not need this step.
import sharp from 'sharp';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const src = `${root}assets/Hubgentic_logo_light.png`;
const out = `${root}public/img`;
mkdirSync(out, { recursive: true });

if (!existsSync(src)) {
  console.error(`Missing ${src}. Add the logo and run again.`);
  process.exit(1);
}

// Header logo: displayed at 40px tall, so 1x and 2x widths.
const HEIGHT = 40;
for (const scale of [1, 2]) {
  const h = HEIGHT * scale;
  const base = sharp(src).resize({ height: h });
  const suffix = scale === 1 ? '' : '@2x';
  await base.clone().png({ compressionLevel: 9, palette: true }).toFile(`${out}/logo${suffix}.png`);
  await base.clone().webp({ quality: 90, alphaQuality: 100 }).toFile(`${out}/logo${suffix}.webp`);
  await base.clone().avif({ quality: 70 }).toFile(`${out}/logo${suffix}.avif`);
}
// Larger PNG for structured data and the Open Graph image.
await sharp(src).png({ compressionLevel: 9 }).toFile(`${out}/logo-full.png`);

// Favicon: the hexagon is the leftmost shape. Find the first fully transparent
// column after it and crop there.
const { data, info } = await sharp(src).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
const opaqueCol = (x) => {
  for (let y = 0; y < info.height; y++) {
    if (data[(y * info.width + x) * info.channels + 3] > 16) return true;
  }
  return false;
};
let start = 0;
while (start < info.width && !opaqueCol(start)) start++;
let end = start;
while (end < info.width && opaqueCol(end)) end++;
// Two pipelines: sharp would otherwise trim before extracting.
const cropped = await sharp(src)
  .extract({ left: start, top: 0, width: end - start, height: info.height })
  .png()
  .toBuffer();
const icon = await sharp(cropped).trim().png().toBuffer();
const meta = await sharp(icon).metadata();
const side = Math.max(meta.width, meta.height);
const square = await sharp(icon)
  .extend({
    top: Math.floor((side - meta.height) / 2),
    bottom: Math.ceil((side - meta.height) / 2),
    left: Math.floor((side - meta.width) / 2),
    right: Math.ceil((side - meta.width) / 2),
    background: { r: 0, g: 0, b: 0, alpha: 0 },
  })
  .png()
  .toBuffer();

const pad = (size, ratio) => Math.round(size * ratio);
for (const size of [32, 192, 512]) {
  await sharp(square).resize(size, size).png().toFile(`${out}/favicon-${size}.png`);
}
// favicon.ico at the site root (browsers request it even with <link rel=icon>): an ICO wrapping a 32px PNG.
const png32 = await sharp(square).resize(32, 32).png().toBuffer();
const header = Buffer.alloc(22);
header.writeUInt16LE(0, 0); // reserved
header.writeUInt16LE(1, 2); // type: icon
header.writeUInt16LE(1, 4); // one image
header.writeUInt8(32, 6); // width
header.writeUInt8(32, 7); // height
header.writeUInt16LE(1, 10); // colour planes
header.writeUInt16LE(32, 12); // bits per pixel
header.writeUInt32LE(png32.length, 14);
header.writeUInt32LE(22, 18); // image offset
writeFileSync(`${root}public/favicon.ico`, Buffer.concat([header, png32]));

// Apple touch icon needs an opaque background.
await sharp(square)
  .resize(pad(180, 0.75), pad(180, 0.75))
  .extend({ top: 22, bottom: 23, left: 22, right: 23, background: '#ffffff' })
  .flatten({ background: '#ffffff' })
  .png()
  .toFile(`${out}/apple-touch-icon.png`);

console.log(`Logo and favicons written to ${out} (icon columns ${start}-${end}).`);
