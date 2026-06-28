import './styles.css'

export const metadata = {
  title: 'Copycat',
  description: 'Hyperliquid smart-wallet intelligence',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body>{children}        <script defer src="/copycat_visual_layout_v1.js"></script>
              <script defer src="/copycat_visual_layout_v2.js"></script>
              <script defer src="/copycat_visual_layout_v3.js"></script>
              <script defer src="/copycat_visual_layout_v4.js"></script>
              <script defer src="/copycat_visual_layout_v5.js"></script>
              <script defer src="/copycat_visual_layout_v6.js"></script>
              <script defer src="/copycat_visual_layout_v7.js"></script>
              <script defer src="/copycat_visual_layout_v8.js"></script>
      </body>
    </html>
  )
}
