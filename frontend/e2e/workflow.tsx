import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { apiFetch } from '../src/lib/api'
import { ItemStageActivityControls, type ActivityItem } from '../src/features/operations/components/ItemStageActivityControls'
import { ImportedAllocationPanel } from '../src/features/operations/components/ProjectAllocationPanel'

type Role = 'prod' | 'qc' | 'qa' | 'tl'
type Fixture = { projectId: number; packageId: number; itemId: number; actors: Record<Role, { id: number; token: string }> }

function Workflow() {
  const [fixture, setFixture] = useState<Fixture | null>(null)
  const [role, setRole] = useState<Role>('prod')
  const [item, setItem] = useState<ActivityItem | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const draft = new URLSearchParams(location.search).get('draft') === 'true'
    fetch(`http://127.0.0.1:38111/__test__/fixture?draft=${draft}`, { method: 'POST' })
      .then(response => { if (!response.ok) throw new Error('Fixture creation failed'); return response.json() })
      .then(value => { localStorage.setItem('asset_token', value.actors.prod.token); setFixture(value) })
      .catch(e => setError(String(e)))
  }, [])
  async function refresh() {
    if (!fixture) return
    try {
      const response = await apiFetch<{ items: ActivityItem[] }>(`/operations/workflow/ortho/work-packages/${fixture.packageId}/items`)
      setItem(response.items.find(row => row.work_package_item_id === fixture.itemId) || null)
    } catch (e) { setError(String(e)) }
  }
  useEffect(() => { void refresh() }, [fixture, role])
  if (!fixture) return <p>{error || 'Preparing isolated fixture…'}</p>
  return <main>
    <h1>Production workflow</h1>
    <label>Acting role<select aria-label="Acting role" value={role} onChange={event => {
      const next = event.target.value as Role
      localStorage.setItem('asset_token', fixture.actors[next].token); setItem(null); setRole(next)
    }}><option value="prod">Production</option><option value="qc">QC</option><option value="qa">QA</option><option value="tl">Team Lead</option></select></label>
    {error && <p role="alert">{error}</p>}
    {role === 'tl' && <>
      <ImportedAllocationPanel projectId={fixture.projectId} onAssigned={() => void refresh()} />
      <button onClick={async () => { await apiFetch(`/operations/workflow/ortho/work-packages/${fixture.packageId}/ready-for-delivery`, { method: 'POST' }); await refresh() }}>Mark Ready</button>
    </>}
    {item && <section aria-label="Current file">
      <output aria-label="Production quantity">{item.production_quantity}</output>
      <output aria-label="Delivery status">{item.delivery_status}</output>
      <ItemStageActivityControls item={item} myUserId={fixture.actors[role].id} canDeliver={role === 'tl'} onChanged={() => void refresh()} />
    </section>}
  </main>
}
createRoot(document.getElementById('root')!).render(<Workflow />)
