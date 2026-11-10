// astro.config.mjs: example for a Blend guide. Versions in package.json mirror the reference builds
// (Starlight 0.40.0, Astro 6.4.x). built and checked 2026-11-10 (npm install, astro build, Pagefind); commands in
// references/starlight-theme.md.
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid'; // renders <pre class="mermaid"> in the browser, as the reference builds do

export default defineConfig({
  // Blend Share serves under https://share.blend360.com/<slug>/ : base must equal the share path.
  site: 'https://share.blend360.com',
  base: '/my-guide',
  integrations: [
    mermaid({ theme: 'default', autoTheme: true }), // must come BEFORE starlight
    starlight({
      title: 'My Guide',
      description: 'One sentence about the guide.',
      defaultLocale: 'root',
      locales: { root: { label: 'English', lang: 'en' } }, // use { label: 'Espanol', lang: 'es' } for Spanish
      logo: { src: './src/assets/blend-symbol-blue.svg', alt: 'Blend' },
      favicon: '/favicon.svg',
      customCss: ['./src/styles/blend-theme.css'],
      // PP Telegraf is bundled by blend-theme.css (@font-face); no Google Fonts link needed.
      // Pagefind search is built in: `astro build` runs it and writes dist/pagefind/.
      sidebar: [
        { label: 'Introduction', items: [{ slug: 'index' }, { slug: 'introduction/what-this-is' }] },
        { label: 'Core topics', items: [{ autogenerate: { directory: 'topics' } }] }, // Starlight >= 0.39: autogenerate goes inside items when the group has a label
      ],
      // The theme selector (Auto / Light / Dark) is Starlight's own; nothing to configure.
    }),
  ],
});
