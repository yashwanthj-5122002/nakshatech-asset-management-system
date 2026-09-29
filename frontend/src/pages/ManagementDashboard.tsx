import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Boxes,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  DollarSign,
  Eye,
  FileBarChart,
  FolderKanban,
  HardDrive,
  History,
  IndianRupee,
  KeyRound,
  Layers,
  PieChart,
  RefreshCcw,
  RotateCcw,
  Repeat2,
  ShieldCheck,
  TrendingUp,
  Users,
  Wallet,
  Wrench,
  X,
} from 'lucide-react'
import { DroneIcon as Drone } from '../components/DroneIcon'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { useAuth } from '../context/AuthContext'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import type { LifecycleDashboardSummary } from '../features/operations/lifecycle-types'
import '../management-auth.css'
import '../management-control.css'

/* ────────────────────────── Types ────────────────────────── */

type ExecutiveDashboardData = {
  month: string | null
  control_center: {
    primary_assets: number
    assigned_assets: number
    available_assets: number
    repair_assets: number
    replacement_pending_assets: number
    active_it_work: number
    active_replacements: number
    pending_approvals: number
    pending_purchase_requests: number
    approved_purchase_value: number
    open_critical_tickets: number
    sla_warnings: number
    sla_breaches: number
  }
  purchase_summary: {
    total: number
    pending_approval: number
    approved: number
    sent_back: number
    rejected: number
    purchase_completed: number
    approved_purchase_value: number
  }
  risk_tickets: Array<{
    id: number
    ticket_code: string
    title: string
    priority: string
    status: string
    sla_breached: boolean
  }>
  business: {
    month: string
    viewer: string
    totals: { total: number; released: number; pending: number; currency: string }
    by_department: Array<{ key: string; label: string; total: number; released: number; pending: number; project_count: number }>
    by_project_manager: Array<{ key: string; label: string; total: number; released: number; pending: number; project_count: number }>
    by_client: Array<{ key: string; label: string; total: number; released: number; pending: number; project_count: number }>
    rows: Array<{
      project_id: number
      project_code: string
      project_name: string
      client_name: string | null
      amount_total: number
      amount_released: number
      amount_pending: number
      status: string
    }>
  } | null
  commercial: {
    summary_inr: {
      approved_estimate_base_inr: number
      billed_net_inr: number
      payments_realized_inr: number
      employee_cost_inr: number
      vendor_cost_inr: number
      total_direct_cost_inr: number
      margin_inr: number
      fx_gain_loss_inr: number
    }
    projects: Array<{
      project_id: number
      project_code: string
      billed_net_inr: number
      payments_realized_inr: number
      total_direct_cost_inr: number
      margin_inr: number
    }>
    monthly: Array<{
      month: string
      billing_inr: number
      payments_inr: number
      total_cost_inr: number
      margin_inr: number
    }>
  } | null
  lifecycle: {
    summary: LifecycleDashboardSummary
    projects: Array<{
      id: number
      project_code: string
      project_name: string
      workflow_status: string
      has_overdue_invoice: boolean
    }>
    department_overview?: Record<string, Record<string, number>>
  } | null
  finance: {
    total_claims: number
    total_requested_amount: number
    pending_admin_count: number
    pending_finance_count: number
    approved_count: number
    paid_count: number
    paid_amount: number
    outstanding_amount: number
    rejected_count: number
    by_type: Array<{ key: string; label: string; amount: number; count: number }>
    by_category: Array<{ key: string; label: string; amount: number; count: number }>
  } | null
}

/* ────────────────────────── Helpers ────────────────────────── */

function formatINR(value: number): string {
  if (Math.abs(value) >= 10_000_000) return `₹${(value / 10_000_000).toFixed(2)} Cr`
  if (Math.abs(value) >= 100_000) return `₹${(value / 100_000).toFixed(2)} L`
  if (Math.abs(value) >= 1_000) return `₹${(value / 1_000).toFixed(1)}K`
  return `₹${value.toLocaleString('en-IN')}`
}

function pct(value: number, total: number): number {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

/* ────────────────────────── Mini Chart Components ────────────────────────── */

const CHART_COLORS = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6']

function DonutChart({ segments, size = 140, label }: { segments: { value: number; color: string; label: string }[]; size?: number; label?: string }) {
  const total = segments.reduce((s, seg) => s + seg.value, 0)
  if (total === 0) return <div className="exec-chart-empty">No data</div>
  const radius = (size - 20) / 2
  const cx = size / 2
  const cy = size / 2
  let cumulative = 0
  const paths = segments.filter(s => s.value > 0).map((seg) => {
    const startAngle = (cumulative / total) * 360
    cumulative += seg.value
    const endAngle = (cumulative / total) * 360
    const largeArc = endAngle - startAngle > 180 ? 1 : 0
    const startRad = ((startAngle - 90) * Math.PI) / 180
    const endRad = ((endAngle - 90) * Math.PI) / 180
    const x1 = cx + radius * Math.cos(startRad)
    const y1 = cy + radius * Math.sin(startRad)
    const x2 = cx + radius * Math.cos(endRad)
    const y2 = cy + radius * Math.sin(endRad)
    const innerRadius = radius * 0.6
    const x3 = cx + innerRadius * Math.cos(endRad)
    const y3 = cy + innerRadius * Math.sin(endRad)
    const x4 = cx + innerRadius * Math.cos(startRad)
    const y4 = cy + innerRadius * Math.sin(startRad)
    return (
      <path
        key={seg.label}
        d={`M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${x4} ${y4} Z`}
        fill={seg.color}
        opacity={0.85}
      >
        <title>{`${seg.label}: ${seg.value} (${pct(seg.value, total)}%)`}</title>
      </path>
    )
  })
  return (
    <div className="exec-donut-wrap">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {paths}
        {label && <text x={cx} y={cy + 5} textAnchor="middle" fill="currentColor" fontSize="13" fontWeight="600">{label}</text>}
      </svg>
      <div className="exec-donut-legend">
        {segments.filter(s => s.value > 0).map(seg => (
          <span key={seg.label}><span className="exec-legend-dot" style={{ background: seg.color }} /> {seg.label}: {seg.value}</span>
        ))}
      </div>
    </div>
  )
}

function BarChart({ bars, height = 180 }: { bars: { label: string; value: number; color?: string }[]; height?: number }) {
  const max = Math.max(...bars.map(b => b.value), 1)
  return (
    <div className="exec-bar-chart" style={{ height }}>
      {bars.map((bar, i) => (
        <div key={bar.label} className="exec-bar-col">
          <div className="exec-bar-value">{formatINR(bar.value)}</div>
          <div className="exec-bar-track" style={{ height: height - 50 }}>
            <div
              className="exec-bar-fill"
              style={{
                height: `${pct(bar.value, max)}%`,
                background: bar.color || CHART_COLORS[i % CHART_COLORS.length],
              }}
              title={`${bar.label}: ${formatINR(bar.value)}`}
            />
          </div>
          <div className="exec-bar-label">{bar.label}</div>
        </div>
      ))}
    </div>
  )
}

function ProgressBar({ value, total, color = '#6366f1', label }: { value: number; total: number; color?: string; label?: string }) {
  const percentage = pct(value, total)
  return (
    <div className="exec-progress-row">
      {label && <span className="exec-progress-label">{label}</span>}
      <div className="exec-progress-track">
        <div className="exec-progress-fill" style={{ width: `${percentage}%`, background: color }} />
      </div>
      <span className="exec-progress-pct">{percentage}%</span>
    </div>
  )
}

function MiniTrendChart({ data, height = 100 }: { data: { label: string; value: number }[]; height?: number }) {
  if (!data.length) return null
  const max = Math.max(...data.map(d => d.value), 1)
  const width = Math.max(data.length * 60, 300)
  const padding = 30
  const chartWidth = width - padding * 2
  const chartHeight = height - 30
  const points = data.map((d, i) => ({
    x: padding + (i / Math.max(data.length - 1, 1)) * chartWidth,
    y: 10 + chartHeight - (d.value / max) * chartHeight,
  }))
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${chartHeight + 10} L ${points[0].x} ${chartHeight + 10} Z`

  return (
    <div className="exec-trend-chart" style={{ overflowX: 'auto' }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#trendGrad)" />
        <path d={linePath} fill="none" stroke="#6366f1" strokeWidth="2.5" strokeLinejoin="round" />
        {points.map((p, i) => (
          <g key={data[i].label}>
            <circle cx={p.x} cy={p.y} r="3.5" fill="#6366f1" />
            <text x={p.x} y={height - 4} textAnchor="middle" fill="currentColor" fontSize="10" opacity="0.65">{data[i].label}</text>
            <title>{`${data[i].label}: ${formatINR(data[i].value)}`}</title>
          </g>
        ))}
      </svg>
    </div>
  )
}

/* ────────────────────────── Main Component ────────────────────────── */

export function ManagementDashboard() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { selectedMonth } = useITMonthUrl()
  const [data, setData] = useState<ExecutiveDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showPasswordDialog, setShowPasswordDialog] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

  function loadDashboard() {
    setError('')
    setLoading(true)
    void apiFetch<ExecutiveDashboardData>(`/management/executive-dashboard?month=${encodeURIComponent(selectedMonth)}`)
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load dashboard'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadDashboard() }, [selectedMonth])

  function closePasswordDialog() {
    if (changingPassword) return
    setShowPasswordDialog(false)
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setPasswordError('')
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    setChangingPassword(true)
    setPasswordError('')
    try {
      const result = await apiFetch<{ message: string }>('/auth/management/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      })
      sessionStorage.setItem('management_password_changed', result.message)
      logout()
      navigate('/login', { replace: true })
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Password change failed')
    } finally {
      setChangingPassword(false)
    }
  }

  const cc = data?.control_center
  const biz = data?.business
  const comm = data?.commercial
  const lifecycle = data?.lifecycle
  const fin = data?.finance

  // Lifecycle status segments for donut chart
  const lifecycleSegments = lifecycle ? [
    { value: lifecycle.summary.awaiting_feedback, color: '#f59e0b', label: 'Awaiting Feedback' },
    { value: lifecycle.summary.rework, color: '#ef4444', label: 'Rework' },
    { value: lifecycle.summary.ready_for_billing, color: '#10b981', label: 'Ready for Billing' },
    { value: lifecycle.summary.payment_pending, color: '#6366f1', label: 'Payment Pending' },
    { value: lifecycle.summary.overdue, color: '#dc2626', label: 'Overdue' },
    { value: lifecycle.summary.closed, color: '#64748b', label: 'Closed' },
  ] : []

  // Monthly trend data for revenue
  const monthlyTrend = comm?.monthly?.slice(-8).map(m => ({
    label: m.month.substring(5),
    value: m.billing_inr,
  })) ?? []

  // Monthly margin trend
  const marginTrend = comm?.monthly?.slice(-8).map(m => ({
    label: m.month.substring(5),
    value: m.margin_inr,
  })) ?? []

  // Top projects by billing
  const topProjects = (comm?.projects ?? [])
    .filter(p => p.billed_net_inr > 0)
    .sort((a, b) => b.billed_net_inr - a.billed_net_inr)
    .slice(0, 6)

  return (
    <>
      <DashboardHeader
        variant="ops"
        icon={Activity}
        eyebrow="EXECUTIVE COMMAND CENTER"
        title="Management Dashboard"
        description={`Business overview for ${monthLabel(selectedMonth)}. Revenue, projects, billing, lifecycle and operations at a glance.`}
        actions={<>
          <button className="secondary-button" type="button" onClick={loadDashboard}><RefreshCcw size={17} /> Refresh</button>
          {user?.role === 'management' && (
            <button className="management-change-password-button" type="button" onClick={() => setShowPasswordDialog(true)}>
              <KeyRound size={18} />
              <span>Change Password</span>
            </button>
          )}
        </>}
        summary={(
          <>
            <StatCard icon={IndianRupee} label="Total Revenue" value={biz ? formatINR(biz.totals.total) : '—'} tone="green" note="Business total this month" />
            <StatCard icon={TrendingUp} label="Net Margin" value={comm ? formatINR(comm.summary_inr.margin_inr) : '—'} tone={comm && comm.summary_inr.margin_inr >= 0 ? 'green' : 'red'} note="Billing minus direct costs" />
            <StatCard icon={FolderKanban} label="Active Projects" value={lifecycle?.summary.active_projects ?? '—'} tone="blue" note="Currently in pipeline" />
          </>
        )}
        meta={(
          <>
            <span className="nk-meta-chip"><Activity size={14} /> Executive Command Center</span>
            <span className="nk-meta-chip"><CalendarDays size={14} /> {monthLabel(selectedMonth)}</span>
            <span className="nk-meta-chip"><Eye size={14} /> Real-time business view</span>
          </>
        )}
      />

      {error && <div className="error-message">{error}</div>}
      {loading && <div className="exec-loading">Loading executive dashboard…</div>}

      {!loading && data && <>
        {/* ═══════════ SECTION 1: CRITICAL ALERTS ═══════════ */}
        <section className="exec-section">
          <h3 className="exec-section-title"><AlertTriangle size={18} /> Critical Alerts</h3>
          <div className="stats-grid management-control-kpis">
            <StatCard icon={ClipboardCheck} label="Pending Purchase Approvals" value={cc?.pending_purchase_requests ?? 0} tone="purple" note="Awaiting decision" />
            <StatCard icon={AlertTriangle} label="SLA Breaches" value={cc?.sla_breaches ?? 0} tone="red" note="Service commitments missed" />
            <StatCard icon={ShieldCheck} label="Critical Tickets" value={cc?.open_critical_tickets ?? 0} tone="red" note="Open P1 tickets" />
            <StatCard icon={Clock3} label="SLA Warnings" value={cc?.sla_warnings ?? 0} tone="orange" note="At risk of breach" />
          </div>
        </section>

        {/* ═══════════ SECTION 2: REVENUE & FINANCIAL OVERVIEW ═══════════ */}
        <section className="exec-section">
          <h3 className="exec-section-title"><IndianRupee size={18} /> Revenue & Financial Overview</h3>
          <div className="exec-grid-2">
            {/* Revenue KPIs */}
            <div className="exec-card">
              <h4 className="exec-card-title"><DollarSign size={16} /> Revenue Summary</h4>
              <div className="exec-kpi-grid">
                <div className="exec-kpi">
                  <span className="exec-kpi-label">Total Revenue</span>
                  <span className="exec-kpi-value text-green">{biz ? formatINR(biz.totals.total) : '—'}</span>
                </div>
                <div className="exec-kpi">
                  <span className="exec-kpi-label">Released</span>
                  <span className="exec-kpi-value text-blue">{biz ? formatINR(biz.totals.released) : '—'}</span>
                </div>
                <div className="exec-kpi">
                  <span className="exec-kpi-label">Pending</span>
                  <span className="exec-kpi-value text-orange">{biz ? formatINR(biz.totals.pending) : '—'}</span>
                </div>
                <div className="exec-kpi">
                  <span className="exec-kpi-label">Collection Rate</span>
                  <span className="exec-kpi-value text-purple">{biz && biz.totals.total > 0 ? `${pct(biz.totals.released, biz.totals.total)}%` : '—'}</span>
                </div>
              </div>
              {biz && biz.totals.total > 0 && (
                <ProgressBar value={biz.totals.released} total={biz.totals.total} color="#10b981" label="Collection Progress" />
              )}
            </div>

            {/* Commercial Summary */}
            <div className="exec-card">
              <h4 className="exec-card-title"><BarChart3 size={16} /> Billing & Margins</h4>
              <div className="exec-kpi-grid">
                <div className="exec-kpi">
                  <span className="exec-kpi-label">Billed (Net)</span>
                  <span className="exec-kpi-value text-blue">{comm ? formatINR(comm.summary_inr.billed_net_inr) : '—'}</span>
                </div>
                <div className="exec-kpi">
                  <span className="exec-kpi-label">Payments Realized</span>
                  <span className="exec-kpi-value text-green">{comm ? formatINR(comm.summary_inr.payments_realized_inr) : '—'}</span>
                </div>
                <div className="exec-kpi">
                  <span className="exec-kpi-label">Total Direct Cost</span>
                  <span className="exec-kpi-value text-red">{comm ? formatINR(comm.summary_inr.total_direct_cost_inr) : '—'}</span>
                </div>
                <div className="exec-kpi">
                  <span className="exec-kpi-label">Net Margin</span>
                  <span className={`exec-kpi-value ${comm && comm.summary_inr.margin_inr >= 0 ? 'text-green' : 'text-red'}`}>
                    {comm ? formatINR(comm.summary_inr.margin_inr) : '—'}
                  </span>
                </div>
              </div>
              {comm && comm.summary_inr.billed_net_inr > 0 && (
                <ProgressBar
                  value={comm.summary_inr.payments_realized_inr}
                  total={comm.summary_inr.billed_net_inr}
                  color="#06b6d4"
                  label="Payment Realization"
                />
              )}
            </div>
          </div>
        </section>

        {/* ═══════════ SECTION 3: BILLING TREND + TOP PROJECTS ═══════════ */}
        {comm && (monthlyTrend.length > 0 || topProjects.length > 0) && (
          <section className="exec-section">
            <h3 className="exec-section-title"><TrendingUp size={18} /> Billing Trends & Top Projects</h3>
            <div className="exec-grid-2">
              {monthlyTrend.length > 1 && (
                <div className="exec-card">
                  <h4 className="exec-card-title"><TrendingUp size={16} /> Monthly Billing Trend</h4>
                  <MiniTrendChart data={monthlyTrend} height={120} />
                </div>
              )}
              {topProjects.length > 0 && (
                <div className="exec-card">
                  <h4 className="exec-card-title"><BarChart3 size={16} /> Top Projects by Billing</h4>
                  <BarChart
                    bars={topProjects.map((p, i) => ({
                      label: p.project_code,
                      value: p.billed_net_inr,
                      color: CHART_COLORS[i % CHART_COLORS.length],
                    }))}
                    height={160}
                  />
                </div>
              )}
            </div>
          </section>
        )}

        {/* ═══════════ SECTION 4: PROJECT LIFECYCLE ═══════════ */}
        {lifecycle && (
          <section className="exec-section">
            <h3 className="exec-section-title"><Layers size={18} /> Project Lifecycle Status</h3>
            <div className="exec-grid-2">
              <div className="exec-card">
                <h4 className="exec-card-title"><PieChart size={16} /> Status Distribution</h4>
                <DonutChart segments={lifecycleSegments} size={160} label={`${lifecycle.summary.total_projects}`} />
              </div>
              <div className="exec-card">
                <h4 className="exec-card-title"><FolderKanban size={16} /> Lifecycle KPIs</h4>
                <div className="stats-grid management-control-kpis" style={{ margin: 0 }}>
                  <StatCard icon={FolderKanban} label="Total Projects" value={lifecycle.summary.total_projects} tone="blue" />
                  <StatCard icon={Activity} label="Active" value={lifecycle.summary.active_projects} tone="green" />
                  <StatCard icon={CheckCircle2} label="Completed" value={lifecycle.summary.completed_projects} tone="green" />
                  <StatCard icon={Clock3} label="Awaiting Feedback" value={lifecycle.summary.awaiting_feedback} tone="orange" />
                  <StatCard icon={RotateCcw} label="In Rework" value={lifecycle.summary.rework} tone="red" />
                  <StatCard icon={Wallet} label="Ready for Billing" value={lifecycle.summary.ready_for_billing} tone="green" />
                  <StatCard icon={IndianRupee} label="Payment Pending" value={lifecycle.summary.payment_pending} tone="purple" />
                  <StatCard icon={AlertTriangle} label="Overdue Invoices" value={lifecycle.summary.overdue} tone="red" />
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ═══════════ SECTION 5: REVENUE BY DEPARTMENT / CLIENT ═══════════ */}
        {biz && (biz.by_department.length > 0 || biz.by_client.length > 0) && (
          <section className="exec-section">
            <h3 className="exec-section-title"><Users size={18} /> Revenue Breakdown</h3>
            <div className="exec-grid-2">
              {biz.by_department.length > 0 && (
                <div className="exec-card">
                  <h4 className="exec-card-title"><Layers size={16} /> By Department</h4>
                  <div className="exec-breakdown-list">
                    {biz.by_department.slice(0, 8).map(dept => (
                      <div key={dept.key} className="exec-breakdown-row">
                        <span className="exec-breakdown-name">{dept.label}</span>
                        <span className="exec-breakdown-count">{dept.project_count} projects</span>
                        <span className="exec-breakdown-amount">{formatINR(dept.total)}</span>
                        <ProgressBar value={dept.released} total={dept.total} color="#6366f1" />
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {biz.by_client.length > 0 && (
                <div className="exec-card">
                  <h4 className="exec-card-title"><Users size={16} /> By Client (Top 8)</h4>
                  <div className="exec-breakdown-list">
                    {biz.by_client.slice(0, 8).map(client => (
                      <div key={client.key} className="exec-breakdown-row">
                        <span className="exec-breakdown-name">{client.label}</span>
                        <span className="exec-breakdown-count">{client.project_count} projects</span>
                        <span className="exec-breakdown-amount">{formatINR(client.total)}</span>
                        <ProgressBar value={client.released} total={client.total} color="#06b6d4" />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ═══════════ SECTION 6: EXPENSE CLAIMS & MARGIN ═══════════ */}
        {(fin || comm) && (
          <section className="exec-section">
            <h3 className="exec-section-title"><Wallet size={18} /> Expenses & Cost Control</h3>
            <div className="exec-grid-2">
              {fin && (
                <div className="exec-card">
                  <h4 className="exec-card-title"><Wallet size={16} /> Expense Claims</h4>
                  <div className="exec-kpi-grid">
                    <div className="exec-kpi">
                      <span className="exec-kpi-label">Total Claims</span>
                      <span className="exec-kpi-value">{fin.total_claims}</span>
                    </div>
                    <div className="exec-kpi">
                      <span className="exec-kpi-label">Requested Amount</span>
                      <span className="exec-kpi-value text-orange">{formatINR(fin.total_requested_amount)}</span>
                    </div>
                    <div className="exec-kpi">
                      <span className="exec-kpi-label">Paid</span>
                      <span className="exec-kpi-value text-green">{formatINR(fin.paid_amount)}</span>
                    </div>
                    <div className="exec-kpi">
                      <span className="exec-kpi-label">Outstanding</span>
                      <span className="exec-kpi-value text-red">{formatINR(fin.outstanding_amount)}</span>
                    </div>
                  </div>
                  <div className="exec-claim-status-row">
                    <span className="exec-chip tone-orange">{fin.pending_admin_count} Pending Admin</span>
                    <span className="exec-chip tone-purple">{fin.pending_finance_count} Pending Finance</span>
                    <span className="exec-chip tone-green">{fin.approved_count} Approved</span>
                    <span className="exec-chip tone-red">{fin.rejected_count} Rejected</span>
                  </div>
                </div>
              )}
              {comm && marginTrend.length > 1 && (
                <div className="exec-card">
                  <h4 className="exec-card-title"><TrendingUp size={16} /> Margin Trend</h4>
                  <MiniTrendChart data={marginTrend} height={120} />
                  <div className="exec-cost-split">
                    <div className="exec-cost-item">
                      <span>Employee Cost</span>
                      <strong>{formatINR(comm.summary_inr.employee_cost_inr)}</strong>
                    </div>
                    <div className="exec-cost-item">
                      <span>Vendor Cost</span>
                      <strong>{formatINR(comm.summary_inr.vendor_cost_inr)}</strong>
                    </div>
                    <div className="exec-cost-item">
                      <span>FX Gain/Loss</span>
                      <strong className={comm.summary_inr.fx_gain_loss_inr >= 0 ? 'text-green' : 'text-red'}>
                        {formatINR(comm.summary_inr.fx_gain_loss_inr)}
                      </strong>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ═══════════ SECTION 7: DEPARTMENT OVERVIEW ═══════════ */}
        {lifecycle?.department_overview && (
          <section className="exec-section">
            <h3 className="exec-section-title"><Boxes size={18} /> Department Overview</h3>
            <div className="exec-dept-grid">
              {Object.entries(lifecycle.department_overview).map(([dept, metrics]) => (
                <div key={dept} className="exec-dept-card">
                  <h4>{dept.replace(/_/g, ' ').toUpperCase()}</h4>
                  <div className="exec-dept-metrics">
                    {Object.entries(metrics).map(([key, val]) => (
                      <div key={key} className="exec-dept-metric">
                        <span className="exec-dept-metric-label">{key.replace(/_/g, ' ')}</span>
                        <span className="exec-dept-metric-value">{val}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ═══════════ SECTION 8: PURCHASE & IT (SECONDARY) ═══════════ */}
        <section className="exec-section">
          <h3 className="exec-section-title"><ShieldCheck size={18} /> Procurement & IT Assets</h3>
          <div className="stats-grid management-control-kpis">
            <StatCard icon={HardDrive} label="IT Assets" value={cc?.primary_assets ?? '—'} />
            <StatCard icon={Boxes} label="Assigned" value={cc?.assigned_assets ?? '—'} tone="blue" />
            <StatCard icon={Boxes} label="Available" value={cc?.available_assets ?? '—'} tone="green" />
            <StatCard icon={Wrench} label="Under Repair" value={cc?.repair_assets ?? '—'} tone="orange" />
            <StatCard icon={Repeat2} label="Replacement Pending" value={cc?.replacement_pending_assets ?? '—'} tone="orange" />
            <StatCard icon={IndianRupee} label="Approved Purchase Value" value={cc ? `₹${(cc.approved_purchase_value ?? 0).toLocaleString('en-IN')}` : '—'} tone="green" />
          </div>
        </section>

        {/* ═══════════ QUICK ACCESS CARDS ═══════════ */}
        <section className="management-cards">
          {user?.role === 'management' && <Link to="/management/approvals"><ClipboardCheck /><div><span className="section-kicker">ONLY PERMISSION QUEUE</span><h2>Purchase Approval Centre</h2><p>{cc?.pending_purchase_requests ?? 0} Purchase Request(s) waiting for Management permission.</p></div><ArrowRight /></Link>}
          <Link to="/management/project-360"><FolderKanban /><div><span className="section-kicker">PROJECT LIFECYCLE</span><h2>Project 360 · Feedback & Billing</h2><p>{lifecycle ? `${lifecycle.summary.awaiting_feedback} awaiting feedback · ${lifecycle.summary.rework} in rework · ${lifecycle.summary.overdue} overdue.` : 'Full Project 360, deemed acceptance authorization, change request decisions and PM chat.'}</p></div><ArrowRight /></Link>
          <Link to="/commercial-analytics"><BarChart3 /><div><span className="section-kicker">COMMERCIAL INTELLIGENCE</span><h2>Commercial Analytics</h2><p>Project-level billing, costs, margins, and variance analysis.</p></div><ArrowRight /></Link>
          <Link to="/business-total-sell"><TrendingUp /><div><span className="section-kicker">BUSINESS TRACKING</span><h2>Business & Total Sell</h2><p>Monthly revenue, department and client breakdowns, collection tracking.</p></div><ArrowRight /></Link>
          <Link to="/finance-dashboard"><Wallet /><div><span className="section-kicker">FINANCE OPERATIONS</span><h2>Finance Dashboard</h2><p>Expense claims, settlements, reimbursements and payment approvals.</p></div><ArrowRight /></Link>
          <Link to="/assets"><HardDrive /><div><span className="section-kicker">ASSET REGISTER</span><h2>View IT Assets</h2><p>Inspect asset tag, employee, workstation, department, device details.</p></div><ArrowRight /></Link>
          <Link to="/it"><Boxes /><div><span className="section-kicker">IT OVERVIEW</span><h2>IT Dashboard</h2><p>{cc?.repair_assets ?? 0} under repair · {cc?.replacement_pending_assets ?? 0} replacement pending.</p></div><ArrowRight /></Link>
          <Link to="/tickets"><AlertTriangle /><div><span className="section-kicker">SERVICE RISK</span><h2>Critical Tickets & SLA</h2><p>{cc?.open_critical_tickets ?? 0} critical open · {cc?.sla_warnings ?? 0} SLA warnings · {cc?.sla_breaches ?? 0} breaches.</p></div><ArrowRight /></Link>
          <Link to="/it/recent-changes"><History /><div><span className="section-kicker">AUDIT TRAIL</span><h2>Recent Changes</h2><p>Review asset, custody, replacement, purchase and operational history.</p></div><ArrowRight /></Link>
          <Link to="/drone"><Drone /><div><span className="section-kicker">DRONE OVERVIEW</span><h2>Drone Dashboard</h2><p>Fleet deployment, pilot, projects, battery and last known location.</p></div><ArrowRight /></Link>
          <Link to="/reports"><FileBarChart /><div><span className="section-kicker">REPORTING</span><h2>Download Reports</h2><p>Operational Excel reports plus the Management purchase-control workbook.</p></div><ArrowRight /></Link>
        </section>
      </>}

      {/* Password Change Dialog */}
      {showPasswordDialog && user?.role === 'management' && (
        <div className="management-password-overlay" role="presentation" onMouseDown={event => {
          if (event.target === event.currentTarget) closePasswordDialog()
        }}>
          <section className="management-password-dialog" role="dialog" aria-modal="true" aria-labelledby="management-password-title">
            <header>
              <div>
                <span>MANAGEMENT SECURITY</span>
                <h2 id="management-password-title">Change Password</h2>
                <p>Changing the password signs this Management account out of all active sessions.</p>
              </div>
              <button type="button" onClick={closePasswordDialog} aria-label="Close password dialog"><X size={20} /></button>
            </header>
            <form onSubmit={changePassword}>
              <label><span>Current Password</span><input type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} autoComplete="current-password" required autoFocus /></label>
              <label><span>New Password</span><input type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} autoComplete="new-password" minLength={10} required /></label>
              <label><span>Confirm New Password</span><input type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} autoComplete="new-password" minLength={10} required /></label>
              <p className="management-password-rules">At least 10 characters with uppercase, lowercase, number, and special character.</p>
              {passwordError && <div className="error-message" role="alert">{passwordError}</div>}
              <div className="management-password-dialog-actions">
                <button type="button" onClick={closePasswordDialog} disabled={changingPassword}>Cancel</button>
                <button type="submit" disabled={changingPassword}>{changingPassword ? 'Changing...' : 'Change Password'}</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  )
}
