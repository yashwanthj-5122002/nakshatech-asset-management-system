// Shared, UI-only popup for department corrections. Transfer permissions stay in the existing backend.
import { X } from 'lucide-react'
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type Props = {
  title: string
  description: string
  busy: boolean
  onClose: () => void
  children: ReactNode
  error?: string
}

export function DepartmentChangeDialog({ title, description, busy, onClose, children, error }: Props) {
  const headingId = useId()
  const dialogRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLElement>('select:not(:disabled), input:not(:disabled), textarea:not(:disabled), button:not(:disabled)')?.focus()
    })
    return () => {
      window.cancelAnimationFrame(frame)
      document.body.style.overflow = previousOverflow
      previousFocus?.focus()
    }
  }, [])

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      if (!busy) onClose()
      return
    }
    if (event.key !== 'Tab') return
    const elements = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not(:disabled), select:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]'
    ) ?? []).filter(element => element.getClientRects().length > 0)
    if (!elements.length) { event.preventDefault(); return }
    const first = elements[0]
    const last = elements[elements.length - 1]
    if (event.shiftKey && (document.activeElement === first || !dialogRef.current?.contains(document.activeElement))) {
      event.preventDefault(); last.focus()
    } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.current?.contains(document.activeElement))) {
      event.preventDefault(); first.focus()
    }
  }

  return createPortal(
    <div role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget && !busy) onClose()
    }} style={{
      position: 'fixed', inset: 0, zIndex: 12000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '16px', background: 'rgba(10, 24, 43, 0.60)',
    }}>
      <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={headingId}
        onKeyDown={handleKeyDown} style={{
          width: 'min(100%, 630px)', maxHeight: 'min(90dvh, 780px)', overflowY: 'auto',
          boxSizing: 'border-box', background: '#fff', color: '#183651',
          borderRadius: 14, padding: 24, boxShadow: '0 22px 70px rgba(10, 24, 43, 0.28)',
        }}>
        <header style={{display:'flex', alignItems:'flex-start', justifyContent:'space-between', gap:16, marginBottom:18}}>
          <div>
            <span style={{display:'block', fontSize:11, fontWeight:700, letterSpacing:'0.06em', color:'#4b6a86', marginBottom:6}}>BEFORE WORK STARTS ONLY</span>
            <h2 id={headingId} style={{margin:'0 0 7px', fontSize:21, lineHeight:1.25}}>{title}</h2>
            <p style={{margin:0, fontSize:13, lineHeight:1.55, color:'#51647a'}}>{description}</p>
          </div>
          <button type="button" aria-label="Close Change Department popup" onClick={onClose} disabled={busy}
            style={{display:'grid', placeItems:'center', width:34, height:34, flexShrink:0, cursor:busy?'not-allowed':'pointer', background:'#f1f5f9', border:'1px solid #dce5ee', borderRadius:8, color:'#254864'}}>
            <X size={17}/>
          </button>
        </header>
        {error && <div role="alert" style={{padding:'10px 12px', marginBottom:14, borderRadius:8, border:'1px solid #fecaca', color:'#991b1b', background:'#fff1f2', fontSize:13}}>{error}</div>}
        {children}
      </section>
    </div>, document.body
  )
}
