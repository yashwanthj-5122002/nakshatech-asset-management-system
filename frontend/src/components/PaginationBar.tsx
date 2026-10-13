type PaginationBarProps = {
  page: number
  pageCount: number
  total: number
  rangeStart: number
  rangeEnd: number
  onPageChange: (page: number) => void
  label?: string
}

export function PaginationBar({ page, pageCount, total, rangeStart, rangeEnd, onPageChange, label }: PaginationBarProps) {
  if (total === 0) return null
  return (
    <div className="pagination-bar">
      <button className="secondary-button" type="button" disabled={page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))}>Previous</button>
      <span>{label ? `${label} · ` : ''}Showing {rangeStart}–{rangeEnd} of {total} · Page {page} of {pageCount}</span>
      <button className="secondary-button" type="button" disabled={page >= pageCount} onClick={() => onPageChange(Math.min(pageCount, page + 1))}>Next</button>
    </div>
  )
}
