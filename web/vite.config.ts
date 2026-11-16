import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The API, for `npm run dev`. 127.0.0.1 and not localhost: on Windows localhost is
// tried over IPv6 first, and the miss is waited out on every request (see the
// README, "The addresses say 127.0.0.1"). The page calls the API by relative paths,
// so there is no CORS anywhere: in development this proxy is the only thing between
// the page and the API, and live they are one server.
const API = 'http://127.0.0.1:8048'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/portfolios': API,
      '/trades': API,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // Every test runs on a machine set to UTC, whatever the machine really is. A
    // formatter that forgets to name its zone then gives UTC times here, and its test
    // goes red even on a laptop that is on UK time.
    env: { TZ: 'UTC' },
  },
})
