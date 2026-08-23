import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const APP = join(process.cwd(), 'src/app');

/** Every template-bearing source outside `ui/`, which is where primitives
 *  are allowed to use raw elements because that is what they wrap. */
export function callSites(): { name: string; source: string }[] {
  const out: { name: string; source: string }[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        if (entry !== 'ui' && entry !== 'testing') walk(full);
        continue;
      }
      if (!/\.(ts|html)$/.test(entry) || entry.endsWith('.spec.ts')) continue;
      // Forward slashes always, regardless of path.join's platform separator
      // -- Windows' backslashes would otherwise silently break every
      // gate that keys an allowlist Map by this name (Task 4 onward).
      const name = full.slice(APP.length + 1).replace(/\\/g, '/');
      out.push({ name, source: readFileSync(full, 'utf8') });
    }
  };
  walk(APP);
  return out;
}
