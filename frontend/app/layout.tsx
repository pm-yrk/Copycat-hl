import './styles.css'

export const metadata = {
  title: 'Copycat',
  description: 'Hyperliquid smart-wallet intelligence',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body>{children}        <script defer src="/copycat_local_viewer_time.js"></script>
              <script defer src="/copycat_rows_only_v1.js"></script>
      </body>
    </html>
  )
}
