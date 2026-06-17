import './styles.css'

export const metadata = { title: 'copycat.hl', description: 'Smart-wallet market intelligence for Hyperliquid traders' }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>
}
