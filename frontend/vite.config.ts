import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // Source maps publish the full original source to anyone who can fetch
    // /assets/*.map. The production app is served as a static bundle, so maps
    // are never needed for debugging a deployed build - turn them off
    // explicitly rather than relying on the default.
    sourcemap: false,
    rollupOptions: {
      output: {
        // Split the heavyweight libraries out of the entry chunk so a first
        // load does not download map rendering, globe rendering and the
        // framework all in one file. Route-level splitting comes from
        // React.lazy in src/App.tsx.
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('maplibre-gl')) return 'maplibre'
          if (id.includes('react-globe.gl') || id.includes('/three/')) return 'globe'
          if (
            id.includes('react-router') ||
            id.includes('/react/') ||
            id.includes('react-dom') ||
            id.includes('/scheduler/')
          ) {
            return 'react-vendor'
          }
          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 3100,
    // Loopback by default: a bare `npm run dev` on a workstation must not open
    // the unauthenticated dev server to the whole LAN. Docker Compose passes
    // `--host 0.0.0.0` explicitly so the container still accepts nginx's
    // proxy traffic over the compose network.
    host: process.env.VITE_HOST ?? 'localhost',
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
        ws: true,
      },
      '/ws': {
        target: 'ws://backend:8000',
        ws: true,
      },
    },
  },
})
