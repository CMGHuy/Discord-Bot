// Pure helpers for browse.mjs (argument parsing, clip geometry); browse.mjs
// launches a browser at top level, so the testable logic lives here.
// Tested by browse-lib.test.mjs.

export const CLIP_MARGIN_PX = 8;

export function parseArgs(argv) {
  const opts = { cmd: argv[0] ?? 'login', paths: [], widths: [1440, 1024, 768, 390], base: 'https://bomeo-capital.com', out: null, clicks: [], settle: 1500, clip: null };
  for (let i = 1; i < argv.length; i += 2) {
    const [flag, value] = [argv[i], argv[i + 1]];
    // Leading slash optional: Git Bash rewrites "/trades/x" into a Windows
    // path unless MSYS_NO_PATHCONV=1, so "trades/x" is the portable form.
    if (flag === '--path') opts.paths.push(value.startsWith('/') ? value : `/${value}`);
    else if (flag === '--widths') opts.widths = value.split(',').map(Number);
    else if (flag === '--base') opts.base = value.replace(/\/$/, '');
    else if (flag === '--out') opts.out = value;
    else if (flag === '--click') opts.clicks.push(value);
    else if (flag === '--settle') opts.settle = Number(value);
    else if (flag === '--clip') {
      if (!value) throw new Error('--clip needs a CSS selector');
      opts.clip = value;
    } else throw new Error(`unknown flag ${flag}`);
  }
  return opts;
}

export function clipBox(box, page, margin = CLIP_MARGIN_PX) {
  if (!box || box.width <= 0 || box.height <= 0) return null;
  const x = Math.max(0, Math.floor(box.x - margin));
  const y = Math.max(0, Math.floor(box.y - margin));
  const right = Math.min(page.width, Math.ceil(box.x + box.width + margin));
  const bottom = Math.min(page.height, Math.ceil(box.y + box.height + margin));
  if (right <= x || bottom <= y) return null;
  return { x, y, width: right - x, height: bottom - y };
}
