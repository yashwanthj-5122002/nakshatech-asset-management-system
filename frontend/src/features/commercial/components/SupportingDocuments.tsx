import { FileText, Paperclip, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DOC_TYPES, deleteAttachment, docTypeLabel, listRevisionDocuments, openAttachment, type AttachmentRow, type PendingDocument } from '../commercial-api'
import '../commercial-workflow.css'

/** Files chosen on the form; they are uploaded to Revision 1 right after the project is saved. */
export function PendingDocumentsPicker({ docs, onChange, disabled = false }: { docs: PendingDocument[]; onChange: (docs: PendingDocument[]) => void; disabled?: boolean }) {
  const [docType, setDocType] = useState('QUOTATION')
  return <div className="cw-docs">
    <div className="cw-docs-add">
      <label className="operations-field"><span>Document type</span><select value={docType} disabled={disabled} onChange={e => setDocType(e.target.value)}>{DOC_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}</select></label>
      <label className="operations-field"><span>Attach file (PDF, JPG, PNG, WebP · max 15 MB)</span>
        <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" disabled={disabled} onChange={e => {
          const file = e.target.files?.[0]
          if (file) onChange([...docs, { file, doc_type: docType }])
          e.target.value = ''
        }} />
      </label>
    </div>
    {docs.length > 0 && <ul className="cw-doc-list">{docs.map((doc, index) => <li key={`${doc.file.name}-${index}`}>
      <Paperclip size={14} /><span><strong>{doc.file.name}</strong> <small>{docTypeLabel(doc.doc_type)} · {(doc.file.size / 1024).toFixed(0)} KB</small></span>
      <button type="button" className="cw-icon-button" aria-label={`Remove ${doc.file.name}`} disabled={disabled} onClick={() => onChange(docs.filter((_, i) => i !== index))}><X size={14} /></button>
    </li>)}</ul>}
    {docs.length === 0 && <small className="cw-muted">Optional: quotation, PO / WO or commercial approval. Files are stored securely and are visible only to BD, Finance and Management.</small>}
  </div>
}

/** Documents already stored against a revision (secure download; delete only while the revision is still editable). */
export function StoredDocumentsList({ projectId, revisionId, canDelete = false, refreshKey = 0 }: { projectId: number; revisionId: number; canDelete?: boolean; refreshKey?: number }) {
  const [rows, setRows] = useState<AttachmentRow[]>([])
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let cancelled = false
    setError('')
    void listRevisionDocuments(projectId, revisionId)
      .then(data => { if (!cancelled) setRows(data) })
      .catch(err => { if (!cancelled) { setRows([]); setError(err instanceof Error ? err.message : 'Unable to load documents') } })
    return () => { cancelled = true }
  }, [projectId, revisionId, refreshKey, tick])
  if (error) return <div className="cw-muted">{error}</div>
  if (!rows.length) return <div className="cw-muted">No supporting documents attached.</div>
  return <ul className="cw-doc-list">{rows.map(row => <li key={row.id}>
    <FileText size={14} /><span><button type="button" className="cw-link" onClick={() => void openAttachment(row.id).catch(err => setError(err instanceof Error ? err.message : 'Unable to open document'))}>{row.original_filename}</button> <small>{docTypeLabel(row.doc_type)} · {(row.file_size / 1024).toFixed(0)} KB</small></span>
    {canDelete && <button type="button" className="cw-icon-button" aria-label={`Delete ${row.original_filename}`} onClick={() => void deleteAttachment(row.id).then(() => setTick(v => v + 1)).catch(err => setError(err instanceof Error ? err.message : 'Unable to delete'))}><Trash2 size={14} /></button>}
  </li>)}</ul>
}
