import './styles.css'

export const metadata = { title: 'Hyper Wallet Tracker', description: 'Smart-wallet market intelligence' }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>
}
