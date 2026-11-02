// import { Building2, MapPin, ShieldCheck } from 'lucide-react'
// import { type FormEvent, useEffect, useState } from 'react'
// import { Navigate, useNavigate } from 'react-router-dom'
// import { useAuth } from '../../../context/AuthContext'
// import { roleHomePath } from '../../../lib/roles'
// import type { Branch } from '../../../types'
// import { AuthFlowShell } from '../components/AuthFlowShell'

// export function BranchSelectionPage() {
//   const navigate = useNavigate()
//   const { user, needsBranchSelection, loadBranches, selectBranch, logout } = useAuth()
//   const [branches, setBranches] = useState<Branch[]>([])
//   const [selected, setSelected] = useState('')
//   const [error, setError] = useState('')
//   const [loading, setLoading] = useState(false)

//   useEffect(() => {
//     void loadBranches().then(items => {
//       setBranches(items)
//       if (items[0]) setSelected(String(items[0].id))
//     }).catch(err => setError(err instanceof Error ? err.message : 'Could not load branches'))
//   }, [])

//   if (!user) return <Navigate to="/login" replace />
//   if (!needsBranchSelection && user.selected_branch_id) return <Navigate to={roleHomePath(user.role)} replace />

//   async function submit(event: FormEvent) {
//     event.preventDefault()
//     if (!selected) return
//     setLoading(true); setError('')
//     try {
//       const result = await selectBranch(Number(selected))

//       const selectedRole = result.user?.role ?? user?.role

//       if (!selectedRole) {
//         throw new Error('Could not determine the user role after branch selection')
//       }

//       navigate(roleHomePath(selectedRole), { replace: true })
//     } catch (err) {
//       setError(err instanceof Error ? err.message : 'Could not select branch')
//     } finally {
//       setLoading(false)
//     }

//   return (
//     <AuthFlowShell eyebrow="BRANCH CONTEXT" title={`Welcome, ${user.full_name}`} description="Select the office or project branch where you are working or where the issue occurred. Every support ticket will carry this branch information." backLabel="Sign out and use another account" onBack={() => { logout(); navigate('/login', { replace: true }) }}>
//       <form className="auth-flow-form" onSubmit={submit}>
//         <div className="branch-selection-grid">
//           {branches.map(branch => <button type="button" key={branch.id} className={`branch-selection-card ${selected === String(branch.id) ? 'selected' : ''}`} onClick={() => setSelected(String(branch.id))}>
//             <Building2 size={25} />
//             <div><strong>{branch.name}</strong><span>{branch.code}</span>{branch.address && <small><MapPin size={13} />{branch.address}</small>}</div>
//             {selected === String(branch.id) && <ShieldCheck size={20} />}
//           </button>)}
//         </div>
//         {error && <div className="error-message">{error}</div>}
//         <button className="final-login-submit" disabled={loading || !selected}><span>{loading ? 'Opening branch...' : 'Continue to Workspace'}</span><i>→</i></button>
//       </form>
//     </AuthFlowShell>
//   )
// }
import { Building2, MapPin, ShieldCheck } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../../../context/AuthContext'
import { roleHomePath } from '../../../lib/roles'
import type { Branch } from '../../../types'
import { AuthFlowShell } from '../components/AuthFlowShell'

export function BranchSelectionPage() {
  const navigate = useNavigate()
  const {
    user,
    needsBranchSelection,
    loadBranches,
    selectBranch,
    logout,
  } = useAuth()

  const [branches, setBranches] = useState<Branch[]>([])
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const autoSelectionStarted = useRef(false)
  const isEmployee = String(user?.role).toLowerCase() === 'employee'
/*  useEffect(() => {
  //  void loadBranches()
      .then(items => {
        setBranches(items)

        if (items[0]) {
          setSelected(String(items[0].id))
        }
      })
      .catch(err => {
        setError(
          err instanceof Error
            ? err.message
            : 'Could not load branches',
        )
      })
  }, [])*/
  useEffect(() => {
  if (!user || autoSelectionStarted.current) return
  autoSelectionStarted.current = true

  async function openWorkspace() {
    setLoading(true)
    setError('')

    try {
      const items = await loadBranches()
      setBranches(items)

      if (items[0]) {
        setSelected(String(items[0].id))
      }

      // Preserve the selection screen for other roles.
      if (!isEmployee) return

      if (!needsBranchSelection && user?.selected_branch_id) {
        navigate(roleHomePath(user.role), { replace: true })
        return
      }

      // Prefer the employee's existing branch, then the sole
      // available branch, then Head Office.
      const branch =
        items.find(item => item.id === user?.selected_branch_id) ??
        (items.length === 1 ? items[0] : undefined) ??
        items.find(item => item.code.toUpperCase() === 'HO')

      if (!branch) {
        throw new Error(
          'No default branch is available. Please select your branch below.'
        )
      }

      const result = await selectBranch(branch.id)
      const role = result.user?.role ?? user?.role

      if (!role || result.branch_selection_required) {
        throw new Error('Could not complete branch selection. Please try again.')
      }

      navigate(roleHomePath(role), { replace: true })
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not open your dashboard'
      )
    } finally {
      setLoading(false)
    }
  }

  void openWorkspace()
}, [])

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (!needsBranchSelection && user.selected_branch_id) {
    return <Navigate to={roleHomePath(user.role)} replace />
  }

  async function submit(event: FormEvent) {
    event.preventDefault()

    if (!selected) {
      return
    }

    setLoading(true)
    setError('')

    try {
      const result = await selectBranch(Number(selected))
      const selectedRole = result.user?.role ?? user?.role

      if (!selectedRole) {
        throw new Error(
          'Could not determine the user role after branch selection',
        )
      }

      navigate(roleHomePath(selectedRole), { replace: true })
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not select branch',
      )
    } finally {
      setLoading(false)
    }
  }
if (isEmployee && !error) {
  return (
    <main role="status" style={{ padding: '32px' }}>
      Opening your dashboard...
    </main>
  )
}
  return (
    <AuthFlowShell
      eyebrow="BRANCH CONTEXT"
      title={`Welcome, ${user.full_name}`}
      description="Select the office or project branch where you are working or where the issue occurred. Every support ticket will carry this branch information."
      backLabel="Sign out and use another account"
      onBack={() => {
        logout()
        navigate('/login', { replace: true })
      }}
    >
      <form className="auth-flow-form" onSubmit={submit}>
        <div className="branch-selection-grid">
          {branches.map(branch => (
            <button
              type="button"
              key={branch.id}
              className={`branch-selection-card ${
                selected === String(branch.id) ? 'selected' : ''
              }`}
              onClick={() => setSelected(String(branch.id))}
            >
              <Building2 size={25} />

              <div>
                <strong>{branch.name}</strong>
                <span>{branch.code}</span>

                {branch.address && (
                  <small>
                    <MapPin size={13} />
                    {branch.address}
                  </small>
                )}
              </div>

              {selected === String(branch.id) && (
                <ShieldCheck size={20} />
              )}
            </button>
          ))}
        </div>

        {error && (
          <div className="error-message">
            {error}
          </div>
        )}

        <button
          className="final-login-submit"
          disabled={loading || !selected}
        >
          <span>
            {loading
              ? 'Opening branch...'
              : 'Continue to Workspace'}
          </span>
          <i>→</i>
        </button>
      </form>
    </AuthFlowShell>
  )
}
