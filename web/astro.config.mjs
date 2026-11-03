import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://agentic.ai',
  // pmi.html is served by Netlify at /pmi without a trailing-slash redirect,
  // so the canonical URL https://agentic.ai/pmi resolves directly.
  build: { format: 'file', inlineStylesheets: 'always' },
  trailingSlash: 'never',
  compressHTML: true,
});
