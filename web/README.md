# agentic.ai/pmi

Static Astro site for Hubgentic's PMI landing page. No client framework, no
analytics, no third-party requests. Fonts (Caladea, Lato) are self-hosted in
`public/fonts`. Deployed on Netlify (see `../netlify.toml`, base dir `web/`).

| URL | Source |
|---|---|
| `/pmi` | `src/pages/pmi.astro` |
| `/privacy` | `src/pages/privacy.astro` (placeholder, `noindex` until the text is in) |

```sh
npm install
npm run dev      # http://localhost:4321/pmi
npm run build    # outputs dist/pmi.html, dist/privacy.html
```

## Assets

1. Put `Hubgentic_logo_light.png` (755×170, transparent) in `assets/`, then run
   `npm run assets`. It writes the header logo (AVIF, WebP, PNG at 1x/2x), the
   favicons cut from the hexagon, and `favicon.ico` into `public/`. Until the
   logo exists the header shows a text wordmark and no favicon is linked.
2. Run `npm run og` to regenerate `public/img/og-pmi.png` (1200×630, logo + H1)
   with the real logo. Uses Playwright's Chromium.
3. Put `Hubgentic_memo_PMI.pdf` in `public/docs/`. The hero links to
   `/docs/Hubgentic_memo_PMI.pdf`.

Commit the generated files; the Netlify build does not run these scripts.

## Contact form

Netlify Forms, form name `pmi-contatti`, honeypot `bot-field`. The request is
sent from `src/lib/submit-lead.ts`: change `FORM_ENDPOINT` there to move to
another provider. Set the notification recipient in the Netlify UI
(Forms → pmi-contatti → Form notifications).

## Open TODOs

- Legal details (ragione sociale, sede legale, P.IVA): `src/data/site.ts`, `LEGAL`.
- Privacy text: `src/pages/privacy.astro`. Remove `noindex` when done.
- Logo, favicon and PDF: see Assets.
- Form recipient and contact email.
