import { useEffect, useMemo, useState } from 'react'

export function useClientPagination<T>(rows: T[], pageSize = 25) {
  const [page, setPage] = useState(1)
  const total = rows.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const currentPage = Math.min(Math.max(1, page), pageCount)
  const pageRows = useMemo(
    () => rows.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [rows, currentPage, pageSize],
  )

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [page, pageCount])

  return {
    page: currentPage,
    setPage,
    pageCount,
    pageRows,
    total,
    pageSize,
    rangeStart: total ? (currentPage - 1) * pageSize + 1 : 0,
    rangeEnd: total ? Math.min(currentPage * pageSize, total) : 0,
  }
}
