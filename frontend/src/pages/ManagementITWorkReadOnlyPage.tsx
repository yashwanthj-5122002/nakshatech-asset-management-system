import { CheckCircle2, Clock3, Eye, PlayCircle, Wrench } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../components/DashboardHeader'
import { StatCard } from '../components/StatCard'
import { useITMonthUrl } from '../context/ITMonthContext'
import { apiFetch } from '../lib/api'
import { monthLabel } from '../lib/itMonth'
import type { WorkRecord } from '../types'

function effectiveMonth(record: WorkRecord) {
  return record.reporting_month || record.created_at?.slice(0, 7) || ''
}

export function ManagementITWorkReadOnlyPage() {
  const { selectedMonth } = useITMonthUrl()
  const [records, setRecords] = useState<WorkRecord[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setError('')
    void apiFetch<WorkRecord[]>('/work-records?module=it')
      .then(setRecords)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load IT work records'))
  }, [selectedMonth])

  const visibleRecords = useMemo(
    () => records.filter(record => effectiveMonth(record) === selectedMonth),
    [records, selectedMonth],
  )

  const counts = useMemo(() => ({
    total: visibleRecords.length,
    open: visibleRecords.filter(record => record.status === 'open').length,
    inProgress: visibleRecords.filter(record => record.status === 'in_progress').length,
    completed: visibleRecords.filter(record => ['completed', 'closed'].includes(record.status)).length,
  }), [visibleRecords])

  return (
    <>
      <DashboardHeader
        eyebrow="MANAGEMENT · READ-ONLY"
        title="IT Work Records"
        description={`Management visibility for ${monthLabel(selectedMonth)}. IT controls operational work and completion; no Management approval is required here.`}
      />
      {error && <div className="error-message">{error}</div>}
      <div className="approval-note"><Eye size={16} /> Read-only oversight. Management can inspect work details, status, technician, asset, dates, resolution and cost, but cannot create, edit, complete, return or approve IT Work.</div>

      <section className="stats-grid management-control-kpis">
        <StatCard icon={Wrench} label="Total Work Records" value={counts.total} />
        <StatCard icon={Clock3} label="Open" value={counts.open} tone="orange" />
        <StatCard icon={PlayCircle} label="In Progress" value={counts.inProgress} tone="blue" />
        <StatCard icon={CheckCircle2} label="Completed" value={counts.completed} tone="green" />
      </section>

      <section className="panel">
        <div className="panel-heading"><div><span className="section-kicker">OPERATIONAL HISTORY</span><h2>IT Work</h2></div><span className="count-chip">{visibleRecords.length}</span></div>
        <div className="table-wrap">
          <table className="asset-table">
            <thead><tr><th>Work Code</th><th>Title</th><th>Asset</th><th>Type</th><th>Priority</th><th>Technician</th><th>Status</th><th>Resolution / Issue</th><th>Cost</th></tr></thead>
            <tbody>
              {visibleRecords.map(record => (
                <tr key={record.id}>
                  <td><strong>{record.work_code}</strong></td>
                  <td>{record.title}</td>
                  <td>{record.asset_code || '—'}</td>
                  <td>{record.work_type}</td>
                  <td>{record.priority}</td>
                  <td>{record.technician || record.assigned_to || '—'}</td>
                  <td><span className={`status ${record.status}`}>{record.status.replaceAll('_', ' ')}</span></td>
                  <td>{record.resolution || record.issue_description || '—'}</td>
                  <td>{record.cost == null ? '—' : `₹${Number(record.cost).toLocaleString('en-IN')}`}</td>
                </tr>
              ))}
              {!visibleRecords.length && <tr><td colSpan={9}><div className="empty-state">No IT work records found for {monthLabel(selectedMonth)}.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
