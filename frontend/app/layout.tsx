import './styles.css'

export const metadata = {
  title: 'Copycat',
  description: 'Hyperliquid smart-wallet intelligence',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body>{children}        <script defer src="/copycat_local_viewer_time.js"></script>
              <script src="/copycat_top_metrics_tight_asset_flush_v1.js" defer></script>
              <script src="/copycat_index_metric_rows_lift_v1.js" defer></script>
              <script src="/copycat_compact_footer_v1.js" defer></script>
              <script src="/copycat_layer_footer_fix_v2.js" defer></script>
              <script src="/copycat_restore_index_only_v1.js" defer></script>
      </body>
    </html>
  )
}
