import './styles.css'

export const metadata = {
  title: 'Copycat',
  description: 'Hyperliquid smart-wallet intelligence',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body>
        <style id="copycat-mobile-layout-lock" dangerouslySetInnerHTML={{ __html: `/* Copycat mobile layout lock: desktop remains untouched because every rule is mobile-only. */
@media (max-width: 820px) {
  html,
  body {
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: hidden !important;
  }

  body {
    -webkit-text-size-adjust: 100%;
  }

  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }

  main,
  section,
  article,
  header,
  nav,
  footer,
  .cc-shell,
  .cc-page,
  .cc-home,
  .cc-dashboard,
  .cc-dashboard-fit,
  .cc-index-dashboard-fit {
    max-width: 100% !important;
    min-width: 0 !important;
    overflow-x: hidden !important;
  }

  header,
  nav,
  .cc-nav,
  .copycat-nav,
  .site-nav,
  .top-nav {
    width: 100% !important;
    max-width: 100% !important;
  }

  header img,
  nav img,
  header svg,
  nav svg {
    max-width: min(50vw, 220px) !important;
    height: auto !important;
  }

  header [aria-haspopup="menu"],
  nav [aria-haspopup="menu"],
  header button,
  nav button,
  .cc-menu-button,
  .copycat-menu-button {
    flex: 0 0 auto !important;
    z-index: 80 !important;
  }

  header time,
  nav time,
  .cc-local-time,
  .cc-viewer-time,
  .cc-top-time,
  [class*="local-time"],
  [class*="viewer-time"] {
    max-width: 52vw !important;
    min-width: 0 !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    font-size: clamp(12px, 3.25vw, 16px) !important;
    line-height: 1.15 !important;
  }

  .cc-grid,
  .cc-dashboard-grid,
  .cc-home-grid,
  .cc-main-grid,
  .cc-bottom-grid,
  .cc-card-grid,
  .cc-two-col,
  .cc-two-column,
  .cc-split,
  .cc-donut-layout {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
  }

  .cc-card,
  .cc-panel,
  .cc-tile,
  .cc-index-card,
  .cc-glance-card,
  .cc-pressure-card,
  .cc-allocation-card,
  .cc-exposure-card,
  .cc-table-card,
  .cc-donut-layout,
  .cc-donut-stage,
  .cc-donut-legend,
  .cc-scroll-y,
  .cc-scroll-x {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    overflow-x: hidden !important;
  }

  .cc-scroll-x,
  .cc-table-wrap,
  .cc-table-scroll {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
  }

  table {
    width: 100% !important;
    max-width: 100% !important;
    table-layout: fixed !important;
  }

  th,
  td {
    min-width: 0 !important;
    max-width: 46vw !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
  }

  .cc-index-card svg,
  .cc-donut-svg {
    max-width: 100% !important;
  }

  .cc-index-note,
  .cc-index-warning,
  footer,
  footer * {
    max-width: 100% !important;
    overflow-wrap: anywhere !important;
  }
}` }} />{children}        <script defer src="/copycat_local_viewer_time.js"></script>
              <script src="/copycat_top_metrics_tight_asset_flush_v1.js" defer></script>
<script src="/copycat_compact_footer_v1.js" defer></script>
              <script src="/copycat_layer_footer_fix_v2.js" defer></script>
              <script src="/copycat_restore_index_only_v1.js" defer></script>
              <script src="/copycat_menu_layer_hotfix_v1.js" defer></script>
      </body>
    </html>
  )
}
