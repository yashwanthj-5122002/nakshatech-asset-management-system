import type { TicketStatus } from '../../types'

export type TicketProgressState = 'not_started' | 'ongoing' | 'completed'

export function ticketProgressFromStatus(status: TicketStatus): TicketProgressState {
  if (status === 'resolved' || status === 'closed') return 'completed'
  if (status === 'assigned' || status === 'in_progress' || status === 'waiting_for_employee') return 'ongoing'
  return 'not_started'
}

export function ticketProgressLabel(status: TicketStatus): string {
  const progress = ticketProgressFromStatus(status)
  if (progress === 'completed') return 'Completed'
  if (progress === 'ongoing') return 'Issue Accepted / Ongoing'
  return 'Not Started'
}

export function ticketProgressShortLabel(status: TicketStatus): string {
  const progress = ticketProgressFromStatus(status)
  if (progress === 'completed') return 'Completed'
  if (progress === 'ongoing') return 'Ongoing'
  return 'Not Started'
}
