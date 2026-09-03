import './styles.css'

export const metadata = {
  title: 'Copycat',
  description: 'Hyperliquid smart-wallet intelligence',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <head>
        <link rel="stylesheet" href="/copycat_mobile_source_layout_v3.css" />
      </head>
      <body>{children}</body>
    </html>
  )
}
