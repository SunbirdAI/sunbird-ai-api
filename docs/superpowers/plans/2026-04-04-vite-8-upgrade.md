# Vite 8 Upgrade Plan

**Status:** Planned (not started)
**Current version:** Vite 5.4.21
**Target version:** Vite 8.x
**Priority:** Low — the immediate security concern (esbuild GHSA-67mh-4wv8-2f99) is already resolved via an npm override. This upgrade is for performance gains and long-term maintenance.

## Why Upgrade

- **Performance:** Vite 8 replaces esbuild + Rollup with Rolldown + Oxc, delivering 10-30x faster builds
- **Security:** Removes the need for the esbuild override workaround
- **Long-term support:** Vite 5 will eventually stop receiving patches

## Migration Path: 3 Major Versions (5 → 6 → 7 → 8)

Each version has its own migration guide. The recommended approach is to upgrade one major version at a time, test, then proceed.

### Phase 1: Vite 5 → 6

**Migration guide:** https://v6.vite.dev/guide/migration

Breaking changes relevant to our project:
- **CSS output naming (library mode only):** Not applicable — we're building an SPA, not a library
- **`resolve.conditions` defaults changed:** Check `vite.config.ts` — our config doesn't set this, so verify default behavior still works
- **`json.stringify` + `json.namedExports` interaction:** Not applicable — we don't configure JSON handling
- **`commonjsOptions.strictRequires` now `true`:** May increase bundle size slightly. Our dependencies (chart.js, framer-motion) use ESM so impact should be minimal
- **HTML asset processing expanded:** Should be transparent — more HTML elements can reference assets

**Risk to our project: Low.** Our `vite.config.ts` is minimal (just React plugin + path alias + output dir).

### Phase 2: Vite 6 → 7

**Migration guide:** https://v7.vite.dev/guide/migration

Breaking changes relevant to our project:
- **Drops Node.js 18:** Verify CI and local environments use Node.js 20.19+ or 22.12+. Check `.github/workflows/` for Node version
- **Removes Sass legacy API:** Not applicable — we use Tailwind CSS, not Sass
- **New default build target `baseline-widely-available`:** Replaces the old `modules` target. Should be fine for modern browsers
- **Plugin hook `enforce` → `order`, `transform` → `handler`:** Only affects custom Vite plugins. Check `@vitejs/plugin-react` version compatibility — will likely need an update

**Risk to our project: Low.** Main action item is ensuring Node.js version is 20+ everywhere.

### Phase 3: Vite 7 → 8

**Migration guide:** https://vite.dev/guide/migration
**Announcement:** https://vite.dev/blog/announcing-vite8

Breaking changes relevant to our project:
- **Rolldown replaces esbuild + Rollup:** The big one. Vite 8 has a compatibility layer that auto-converts `rollupOptions` → `rolldownOptions`. Since we don't use `rollupOptions` in our config, this should be transparent
- **`optimizeDeps.esbuildOptions` deprecated:** We don't use this
- **CSS minification via Lightning CSS by default:** Can fall back to `build.cssMinify: 'esbuild'` if issues arise. Tailwind output should be fine
- **CommonJS interop changes:** Default import behavior from CJS modules changes. Test chart.js and framer-motion imports
- **`import.meta.hot.accept` URL form removed:** We don't use HMR API directly

**Risk to our project: Low-Medium.** The Rolldown swap is the main unknown. The compatibility layer handles most cases, but chart.js (CJS) interop should be tested carefully.

## Implementation Steps

1. **Create a feature branch** `chore/vite-8-upgrade`
2. **Verify Node.js version** — ensure 20.19+ locally and in CI (`.github/workflows/`)
3. **Upgrade incrementally:**
   ```bash
   cd frontend
   # Step 1: Vite 6
   npm install vite@^6.0.0 @vitejs/plugin-react@^4.3.0
   npm run build && npm run dev  # smoke test
   
   # Step 2: Vite 7
   npm install vite@^7.0.0 @vitejs/plugin-react@^4.4.0
   npm run build && npm run dev  # smoke test
   
   # Step 3: Vite 8
   npm install vite@^8.0.0 @vitejs/plugin-react@^4.5.0
   npm run build && npm run dev  # smoke test
   ```
   (Plugin versions are approximate — check compatibility at each step)
4. **Remove the esbuild override** from `package.json` — no longer needed with Vite 8
5. **Test all pages manually:** Landing, Login, Register, Dashboard (charts), API Keys, Account Settings
6. **Verify production build output:** Check bundle size is reasonable, no missing assets
7. **Run `npm audit`** — should be 0 vulnerabilities
8. **Update `vite.config.ts`** if any deprecation warnings appear (e.g., `rollupOptions` → `rolldownOptions`)

## Risk Assessment for Our Project

| Area | Risk | Reason |
|------|------|--------|
| `vite.config.ts` | Very Low | Minimal config — just React plugin, path alias, output dir |
| Tailwind CSS | Very Low | PostCSS pipeline is independent of Vite internals |
| React 18 | Low | React plugin compatibility tracked by `@vitejs/plugin-react` |
| Chart.js / react-chartjs-2 | Low-Medium | CJS package — test CommonJS interop after upgrade |
| Framer Motion | Low | ESM package, should be fine |
| TypeScript compilation | Very Low | `tsc` runs before Vite, independent |

## Estimated Effort

- **1-2 hours** if no issues (likely for our simple config)
- **Half day** if chart.js CJS interop needs workarounds

## References

- [Vite 8.0 Announcement](https://vite.dev/blog/announcing-vite8)
- [Migration from Vite 7 → 8](https://vite.dev/guide/migration)
- [Migration from Vite 6 → 7](https://v7.vite.dev/guide/migration)
- [Migration from Vite 5 → 6](https://v6.vite.dev/guide/migration)
- [Breaking Changes Reference](https://vite.dev/changes/)
- [esbuild GHSA-67mh-4wv8-2f99 Advisory](https://github.com/advisories/GHSA-67mh-4wv8-2f99)
- [Vite issue #19412 — esbuild security](https://github.com/vitejs/vite/issues/19412)
- [Vite 8 Rolldown Migration Guide (byteiota)](https://byteiota.com/vite-8-rolldown-migration-guide-10-30x-faster-builds/)
