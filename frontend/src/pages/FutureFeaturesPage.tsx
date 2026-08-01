import { BellRing, Bot, Boxes, QrCode, ShieldCheck, Smartphone, Workflow } from 'lucide-react'
import { DashboardHeader } from '../components/DashboardHeader'
import type { AppIcon } from '../components/DroneIcon'

const modules: Array<{ icon: AppIcon; title: string; text: string }> = [
  { icon: QrCode, title: 'QR / Barcode Scanning', text: 'Scan an asset to open its profile, assignment and history.' },
  { icon: BellRing, title: 'Notifications', text: 'Warranty, maintenance, return and approval alerts.' },
  { icon: Workflow, title: 'Advanced Approvals', text: 'Configurable multi-level approval flows by cost and branch.' },
  { icon: Smartphone, title: 'PWA / Mobile Mode', text: 'Installable field application with offline forms.' },
  { icon: Boxes, title: 'Stores & Procurement', text: 'Purchase requests, stock, vendor and goods-received records.' },
  { icon: Bot, title: 'AI Assistance', text: 'Natural-language search and maintenance-summary generation.' },
  { icon: ShieldCheck, title: 'Enterprise SSO', text: 'Microsoft or Google Workspace authentication.' },
]

export function FutureFeaturesPage() {
  return (
    <>
      <DashboardHeader eyebrow="EXTENSIBLE ARCHITECTURE" title="Future Feature Modules" description="The project is separated by modules so these additions can be introduced without rewriting the welcome, authentication or current IT workflows." />
      <section className="module-grid">
        {modules.map(({ icon: Icon, title, text }) => <article className="module-card" key={title}><Icon /><h3>{title}</h3><p>{text}</p></article>)}
      </section>
    </>
  )
}
