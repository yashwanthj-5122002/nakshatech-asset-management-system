import { ChevronLeft, ChevronRight, Plus, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import type { DroneAssetListResponse } from '../../../types'

const PAGE_SIZE = 25
const statuses = ['', 'available', 'deployed_to_project', 'assigned_to_employee', 'pending_verification', 'sent_for_service', 'under_maintenance', 'under_calibration', 'missing', 'damaged', 'retired']

export function DroneAssetsPage() {
  const [data, setData] = useState<DroneAssetListResponse>({ items: [], total: 0, offset: 0, limit: PAGE_SIZE })
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setLoading(true); setError('')
      const params = new URLSearchParams({ offset: String(page * PAGE_SIZE), limit: String(PAGE_SIZE) })
      if (search.trim()) params.set('search', search.trim())
      if (category) params.set('category', category)
      if (status) params.set('status', status)
      try { setData(await apiFetch<DroneAssetListResponse>(`/drone/assets?${params}`)) }
      catch (err) { setError(err instanceof Error ? err.message : 'Unable to load assets') }
      finally { setLoading(false) }
    }, 300)
    return () => window.clearTimeout(timer)
  }, [search, category, status, page])

  const categories = useMemo(() => Array.from(new Set(data.items.map(item => item.category))).sort(), [data.items])
  const totalPages = Math.max(Math.ceil(data.total / PAGE_SIZE), 1)

  return (
    <>
      <DashboardHeader eyebrow="PERMANENT MASTER" title="Drone & Survey Asset Register" description="New drones, DGPS equipment, batteries, cameras, controllers, HDDs and future equipment are created once and tracked permanently." actions={<Link className="primary-button" to="/drone/assets/new"><Plus size={17} /> Add Asset</Link>} />
      <section className="panel drone-assets-panel">
        <div className="table-toolbar drone-toolbar">
          <label className="search-field"><Search size={17} /><input value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} placeholder="Search asset tag, imported ID, serial, model, employee…" /></label>
          <select value={category} onChange={event => { setCategory(event.target.value); setPage(0) }}><option value="">All categories</option>{categories.map(item => <option key={item}>{item}</option>)}</select>
          <select value={status} onChange={event => { setStatus(event.target.value); setPage(0) }}>{statuses.map(item => <option key={item || 'all'} value={item}>{item ? item.replaceAll('_', ' ') : 'All statuses'}</option>)}</select>
          <span className="count-chip" aria-label={`${data.total} assets`}>{data.total} assets</span>
        </div>
        {error && <div className="error-message">{error}</div>}
        {loading ? <div className="loading-state compact-loading">Loading Drone assets…</div> : (
          <div className="table-wrap">
            <table className="data-table drone-master-table">
              <thead><tr><th>Asset Tag</th><th>Equipment</th><th>Serial / Imported ID</th><th>Quantity</th><th>Custody</th><th>Status</th><th>Source</th><th /></tr></thead>
              <tbody>
                {data.items.map(asset => <tr key={asset.id}>
                  <td><strong>{asset.asset_tag}</strong><small>{asset.category}</small></td>
                  <td><strong>{asset.asset_name}</strong><small>{[asset.manufacturer, asset.model_number].filter(Boolean).join(' · ') || 'Details not recorded'}</small></td>
                  <td><span>{asset.serial_number || asset.raw_serial_number || 'Not recorded'}</span><small>{asset.imported_equipment_id || 'No imported ID'}</small></td>
                  <td><strong>{asset.quantity} {asset.unit_of_measure || ''}</strong><small>{!asset.is_serialized ? `${asset.available_quantity ?? asset.quantity} available · ${asset.allocated_quantity || 0} allocated` : 'Serialized item'}</small></td>
                  <td><span>{asset.current_project || asset.current_custodian || 'Office / available'}</span><small>{asset.parent_kit || asset.current_location || ''}</small></td>
                  <td><span className={`status ${asset.current_status}`}>{asset.current_status.replaceAll('_', ' ')}</span></td>
                  <td><span>{asset.source_sheet || 'Manual'}</span><small>{asset.source_row ? `Row ${asset.source_row}` : ''}</small></td>
                  <td><Link className="text-button" to={`/drone/assets/${asset.id}`}>Open</Link></td>
                </tr>)}
              </tbody>
            </table>
            {data.items.length === 0 && <div className="empty-state">No Drone/Survey assets match the selected filters.</div>}
          </div>
        )}
        <div className="pagination-bar"><button className="secondary-button" disabled={page === 0} onClick={() => setPage(value => Math.max(value - 1, 0))}><ChevronLeft size={16} /> Previous</button><span>Page {page + 1} of {totalPages}</span><button className="secondary-button" disabled={page + 1 >= totalPages} onClick={() => setPage(value => value + 1)}>Next <ChevronRight size={16} /></button></div>
      </section>
    </>
  )
}
