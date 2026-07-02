import './styles.css'

export const metadata = {
  title: 'Copycat',
  description: 'Hyperliquid smart-wallet intelligence',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body>
        <style id="copycat-mobile-layout-lock" dangerouslySetInnerHTML={ __html: `@media (max-width: 820px) {
  html, body { width:100% !important; max-width:100% !important; overflow-x:hidden !important; }
  *, *::before, *::after { box-sizing:border-box; }
  body { -webkit-text-size-adjust:100%; }

  main, section, article, footer,
  .cc-shell, .cc-page, .cc-home, .cc-dashboard, .cc-dashboard-fit, .cc-index-dashboard-fit {
    width:100% !important; max-width:100% !important; min-width:0 !important; overflow-x:hidden !important;
  }

  header, nav, .cc-nav, .copycat-nav, .site-nav, .top-nav {
    position:relative !important; width:100% !important; max-width:100% !important; min-width:0 !important;
    display:flex !important; align-items:flex-start !important; justify-content:space-between !important;
    flex-wrap:nowrap !important; gap:12px !important; padding-right:116px !important; overflow:visible !important;
  }

  header img, nav img, header svg, nav svg { max-width:min(48vw,210px) !important; height:auto !important; }

  header [aria-haspopup="menu"], nav [aria-haspopup="menu"],
  header button[aria-expanded], nav button[aria-expanded],
  .cc-menu-button, .copycat-menu-button {
    position:absolute !important; top:18px !important; right:22px !important; left:auto !important;
    margin:0 !important; transform:none !important; z-index:1000 !important;
  }

  header [role="menu"], nav [role="menu"],
  .cc-menu-panel, .copycat-menu-panel, .site-menu-panel, .top-menu-panel {
    position:fixed !important; top:82px !important; right:16px !important; left:auto !important;
    max-width:calc(100vw - 32px) !important; z-index:1001 !important;
  }

  header time, nav time, .cc-local-time, .cc-viewer-time, .cc-top-time,
  [class*="local-time"], [class*="viewer-time"] {
    max-width:42vw !important; min-width:0 !important; white-space:normal !important; overflow-wrap:anywhere !important;
    font-size:clamp(11px,3vw,15px) !important; line-height:1.15 !important;
  }

  .cc-grid, .cc-dashboard-grid, .cc-home-grid, .cc-main-grid, .cc-bottom-grid, .cc-card-grid,
  .cc-section-grid, .cc-dashboard-section, .cc-two-col, .cc-two-column, .cc-split, .cc-columns,
  .cc-donut-layout, [class*="dashboard-grid"], [class*="home-grid"], [class*="main-grid"],
  [class*="bottom-grid"], [class*="card-grid"], [class*="section-grid"], [class*="two-col"],
  [class*="twoCol"], [class*="split"], [class*="columns"] {
    display:grid !important; grid-template-columns:minmax(0,1fr) !important;
    width:100% !important; max-width:100% !important; min-width:0 !important; overflow-x:hidden !important;
  }

  .cc-card, .cc-panel, .cc-tile, .cc-index-card, .cc-glance-card, .cc-pressure-card,
  .cc-allocation-card, .cc-exposure-card, .cc-table-card, .cc-donut-stage, .cc-donut-legend,
  .cc-scroll-y, .cc-scroll-x, [class*="allocation"], [class*="exposure"] {
    width:100% !important; max-width:100% !important; min-width:0 !important;
  }

  .cc-allocation-card, [class*="allocation"] { order:1; }
  .cc-exposure-card, [class*="exposure"] { order:2; }

  .cc-index-card, .cc-index-card.home, .cc-index-card.deep, .cc-index-dashboard-fit {
    height:auto !important; min-height:0 !important; max-height:none !important;
    overflow:visible !important; padding-bottom:22px !important;
  }
  .cc-index-card .cc-index-chart {
    height:250px !important; min-height:250px !important; max-height:none !important; overflow:visible !important;
  }
  .cc-index-card svg { max-width:100% !important; overflow:visible !important; }
  .cc-index-metrics {
    display:grid !important; grid-template-columns:repeat(2,minmax(0,1fr)) !important;
    gap:12px !important; width:100% !important; max-width:100% !important; overflow:visible !important;
  }
  .cc-index-metrics > div { min-width:0 !important; width:100% !important; }
  .cc-index-note, .cc-index-warning {
    margin-top:14px !important; max-width:100% !important; overflow-wrap:anywhere !important; line-height:1.35 !important;
  }

  .cc-scroll-x, .cc-table-wrap, .cc-table-scroll {
    overflow-x:auto !important; -webkit-overflow-scrolling:touch; max-width:100% !important;
  }
  table { width:100% !important; max-width:100% !important; table-layout:fixed !important; }
  th, td { min-width:0 !important; max-width:46vw !important; overflow:hidden !important; text-overflow:ellipsis !important; white-space:nowrap !important; }

  footer, .cc-footer, [class*="footer"] { max-width:100% !important; overflow-x:hidden !important; }
  footer p, .cc-footer p, [class*="footer"] p { line-height:1.35 !important; margin-bottom:10px !important; }
  footer nav, .cc-footer nav, .cc-legal, .legal, [class*="legal"] {
    display:flex !important; flex-wrap:wrap !important; justify-content:center !important; align-items:center !important;
    gap:8px 12px !important; max-width:100% !important; line-height:1.4 !important;
    white-space:normal !important; overflow-wrap:anywhere !important; text-align:center !important;
  }
}` } />{children}        <script defer src="/copycat_local_viewer_time.js"></script>
              <script src="/copycat_top_metrics_tight_asset_flush_v1.js" defer></script>
<script src="/copycat_compact_footer_v1.js" defer></script>
              <script src="/copycat_layer_footer_fix_v2.js" defer></script>
              <script src="/copycat_restore_index_only_v1.js" defer></script>
              <script src="/copycat_menu_layer_hotfix_v1.js" defer></script>
      </body>
    </html>
  )
}
