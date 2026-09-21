import { apiBlob, apiFetch } from '../../lib/api'

export type AttachmentRow = {
  id: number
  owner_type: string
  owner_id: number
  doc_type: string
  original_filename: string
  mime_type: string
  file_size: number
  created_at: string
}

export type PendingDocument = { file: File; doc_type: string }

export const DOC_TYPES: Array<{ value: string; label: string }> = [
  { value: 'QUOTATION', label: 'Quotation' },
  { value: 'PO', label: 'Purchase Order (PO)' },
  { value: 'WO', label: 'Work Order (WO)' },
  { value: 'APPROVAL', label: 'Commercial approval' },
  { value: 'OTHER', label: 'Other supporting document' },
]

export function docTypeLabel(value: string): string {
  return DOC_TYPES.find(item => item.value === value)?.label ?? value
}

/** Uploads to the existing secure attachment endpoint. Returns the names that failed instead of throwing on the first one. */
export async function uploadRevisionDocuments(projectId: number, revisionId: number, docs: PendingDocument[]): Promise<string[]> {
  const failed: string[] = []
  for (const doc of docs) {
    const body = new FormData()
    body.append('owner_type', 'ESTIMATE_REVISION')
    body.append('owner_id', String(revisionId))
    body.append('doc_type', doc.doc_type)
    body.append('file', doc.file)
    try {
      await apiFetch(`/commercial/projects/${projectId}/attachments`, { method: 'POST', body })
    } catch {
      failed.push(doc.file.name)
    }
  }
  return failed
}

export function listRevisionDocuments(projectId: number, revisionId: number): Promise<AttachmentRow[]> {
  return apiFetch<AttachmentRow[]>(`/commercial/projects/${projectId}/attachments?owner_type=ESTIMATE_REVISION&owner_id=${revisionId}`)
}

export async function openAttachment(attachmentId: number): Promise<void> {
  const blob = await apiBlob(`/commercial/attachments/${attachmentId}/content`)
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export function deleteAttachment(attachmentId: number): Promise<void> {
  return apiFetch<void>(`/commercial/attachments/${attachmentId}`, { method: 'DELETE' })
}
