// Writes public/config.js from Netlify environment variables at build time,
// so the repo never contains project keys. The anon key is public by design;
// the service role key must NEVER appear here.
import { writeFileSync } from 'node:fs';

const url = process.env.SUPABASE_URL;
const anon = process.env.SUPABASE_ANON_KEY;

if (!url || !anon) {
  console.error(
    'Missing SUPABASE_URL or SUPABASE_ANON_KEY.\n' +
    'Set them in Netlify: Site configuration -> Environment variables.\n' +
    'See SETUP.md.'
  );
  process.exit(1);
}
if (process.env.SUPABASE_SERVICE_ROLE_KEY && anon === process.env.SUPABASE_SERVICE_ROLE_KEY) {
  console.error('SUPABASE_ANON_KEY is set to the service role key. Never ship that to the browser.');
  process.exit(1);
}

writeFileSync(
  new URL('../public/config.js', import.meta.url),
  `window.MX_CONFIG=${JSON.stringify({ SUPABASE_URL: url, SUPABASE_ANON_KEY: anon })};\n`
);
console.log('Wrote public/config.js');
