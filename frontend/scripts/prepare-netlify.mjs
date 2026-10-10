import { writeFileSync } from 'node:fs';

// Keep browser API requests on the Netlify origin so secure SameSite=Lax
// session cookies work without depending on third-party cookie permissions.
const configured = process.env.RENDER_API_ORIGIN;
if (!configured) throw new Error('Set RENDER_API_ORIGIN in Netlify to your Render URL, e.g. https://your-service.onrender.com');
const backend = new URL(configured);
if (backend.protocol !== 'https:' || backend.username || backend.password ||
    backend.search || backend.hash || backend.pathname !== '/') {
  throw new Error('RENDER_API_ORIGIN must be an HTTPS origin without /api, credentials, query or fragment.');
}
writeFileSync(new URL('../dist/_redirects', import.meta.url),
  `/api/* ${backend.origin}/api/:splat 200!\n/* /index.html 200\n`);
console.log('Prepared Netlify API proxy and SPA fallback.');
