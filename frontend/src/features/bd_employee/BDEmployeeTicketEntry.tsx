import { useEffect, useState } from 'react'
import { TicketCreatePage } from '../employee_portal/pages/TicketCreatePage'
import { useAuth } from '../../context/AuthContext'
import type { Branch } from '../../types'

/** Reuse the official ticket page; select only an authorized branch in this workspace. */
export function BDEmployeeTicketEntry() {
  const { user, loadBranches, selectBranch } = useAuth()
  const [branches, setBranches] = useState<Branch[]>([])
  const [choice, setChoice] = useState('')
  const [busy, setBusy] = useState(!user?.selected_branch_id)
  const [error, setError] = useState('')

  useEffect(() => {
    if (user?.selected_branch_id) return
    let active = true
    const initialize = async () => {
      try {
        const allowed = await loadBranches()
        if (!active) return
        setBranches(allowed)
        const assigned = allowed.find(branch =>
          branch.name.trim().toLowerCase() === (user?.branch || '').trim().toLowerCase(),
        )
        const first = allowed.length === 1 ? allowed[0] : undefined
        const preferred = assigned ?? first
        if (!preferred) {
          setChoice('')
          return
        }
        setChoice(String(preferred.id))
        await selectBranch(preferred.id)
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : 'Cannot select an authorized branch')
      } finally {
        if (active) setBusy(false)
      }
    }
    void initialize()
    return () => { active = false }
    // Only run on mount; the selected branch is written to shared auth context.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (user?.selected_branch_id) return <TicketCreatePage />
  const choose = async () => {
    if (!choice) return
    setBusy(true)
    setError('')
    try { await selectBranch(Number(choice)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Branch selection failed') }
    finally { setBusy(false) }
  }
  return <section className="panel-card" style={{ padding: 24, maxWidth: 720 }}>
    <h2>Branch for this support ticket</h2>
    <p>Choose your authorized branch to continue with the standard ticket form.</p>
    {error && <p className="error-message" role="alert">{error}</p>}
    {!busy && branches.length === 0 && <p>No authorized branch is available for this account. Contact your ERP administrator.</p>}
    {branches.length > 1 && <label>Branch
      <select value={choice} onChange={e => setChoice(e.target.value)}>
        <option value="">Choose branch</option>
        {branches.map(branch => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
      </select>
    </label>}
    <div style={{ marginTop: 16 }}>
      <button type="button" className="primary-button" disabled={busy || !choice} onClick={() => void choose()}>
        {busy ? 'Opening ticket form...' : 'Continue to ticket form'}
      </button>
    </div>
  </section>
}
