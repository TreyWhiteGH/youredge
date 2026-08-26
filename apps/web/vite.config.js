import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// The engine runs on :8000. Proxying under /api keeps the browser on one origin, so the
// app works unchanged whether Vite serves it in dev or a static host sits in front of the
// engine in production — no CORS, and no build-time URL baked into the bundle.
//
// Point it somewhere else with ENGINE_URL, in the shell or in a local .env file:
//   ENGINE_URL=http://localhost:8010
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.ENGINE_URL || 'http://localhost:8000';

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { '/api': { target, changeOrigin: true } },
    },
    build: { outDir: 'dist', sourcemap: true },
  };
});
