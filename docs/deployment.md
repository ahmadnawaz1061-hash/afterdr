# Deploy After Dr to Render and Netlify

1. Create the Netlify site from this repository's main branch. The root
   `netlify.toml` sets the frontend directory, build and publish settings.
   Note its HTTPS site origin before the first successful build.
2. Create a Render Blueprint from this repository's `render.yaml`. This uses
   the paid Starter service and a 1 GB persistent disk to preserve SQLite data.
   Enter `GEMINI_API_KEY` and set `ALLOWED_ORIGINS` to the exact Netlify HTTPS
   origin, without a trailing slash. Other settings and a random session secret
   are provided by the Blueprint. Wait for `/api/health` to return `ok`.
3. Set Netlify environment variable `RENDER_API_ORIGIN` to the actual Render
   origin, such as `https://your-service.onrender.com`, without `/api`.
   Trigger a new Netlify production build. Keep `VITE_API_BASE_URL=/api` and
   `VITE_USE_MOCKS=false`; these defaults are in `netlify.toml`.

The Netlify build generates an API proxy before the SPA fallback. Browser API
requests and cookies therefore stay on the Netlify origin. Missing/invalid
backend configuration fails the build instead of shipping a broken API URL.
No credentials belong in frontend environment variables or Git.

Check registration, login, refreshing `/dashboard`, packaging analysis and PDF
download after deployment. Platform/provider timeouts and quotas still apply;
this configuration is not a live deployment or a guarantee of external-service
availability. Free Render services lack this persistent disk; removing it makes
local database records temporary across restarts/redeploys.
