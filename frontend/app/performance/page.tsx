import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import PerformanceIndex from '../../components/PerformanceIndex'

export default function PerformancePage() {
  return <><Nav /><main className="cc-dashboard-shell cc-performance-page"><LineBackdrop variant="dashboard" />
    <section className="cc-performance-hero">
      <p className="eyebrow live">Live model performance</p>
      <h1>Copycat Index</h1>
      <p>Rules-based performance of following Copycat portfolio targets from the moment they are published, compared with BTC, ETH and the S&P 500.</p>
    </section>
    <PerformanceIndex variant="dashboard" />
  </main></>
}
