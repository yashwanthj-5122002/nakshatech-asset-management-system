const managementEmails = new Set([
  'vinod@nakshatech.com',
  'chethan@nakshatech.com',
])

export function canAccessBDAI(
  user: { role: string; email?: string | null } | null | undefined
): boolean {
  if (!user) return false

 if (
  user.role === 'bd' ||
  user.role === 'bd_employee'
) return true

  return (
    user.role === 'management' &&
    managementEmails.has(
      (user.email ?? '').trim().toLowerCase()
    )
  )
}