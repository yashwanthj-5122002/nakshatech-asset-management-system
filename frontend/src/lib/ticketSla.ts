import type { SupportTicketSummary } from '../types'
import { formatDuration, parseServerDateTime } from './dateTime'

export type TicketSlaVisualState = 'not_applicable' | 'on_track' | 'warning' | 'breached' | 'met'

export interface TicketSlaDisplay {
  state: TicketSlaVisualState
  label: string
  value: string
}

function compactSeconds(seconds: number): string {
  const totalMinutes = Math.max(0, Math.floor(Math.abs(seconds) / 60))
  if (totalMinutes < 1) return '<1m'
  if (totalMinutes < 60) return `${totalMinutes}m`
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours < 24) return `${hours}h ${minutes}m`
  const days = Math.floor(hours / 24)
  return `${days}d ${hours % 24}h`
}

export function ticketSlaDisplay(ticket: SupportTicketSummary, nowMs = Date.now()): TicketSlaDisplay {
  if (!ticket.sla_target_minutes || !ticket.sla_due_at) {
    return { state: 'not_applicable', label: 'No SLA', value: 'Not assigned' }
  }

  const dueAt = parseServerDateTime(ticket.sla_due_at)
  const warningAt = parseServerDateTime(ticket.sla_warning_at)
  const firstResponseAt = parseServerDateTime(ticket.sla_first_response_at)
  if (!dueAt) return { state: 'not_applicable', label: 'No SLA', value: 'Not assigned' }

  if (firstResponseAt) {
    const lateSeconds = Math.floor((firstResponseAt.getTime() - dueAt.getTime()) / 1000)
    if (lateSeconds > 0 || ticket.sla_breached) {
      return { state: 'breached', label: 'Breached', value: `${compactSeconds(lateSeconds)} late` }
    }
    return { state: 'met', label: 'Met', value: `responded in ${formatDuration(ticket.created_at, ticket.sla_first_response_at)}` }
  }

  const remainingSeconds = Math.floor((dueAt.getTime() - nowMs) / 1000)
  if (remainingSeconds <= 0) {
    return { state: 'breached', label: 'Breached', value: `${compactSeconds(remainingSeconds)} overdue` }
  }
  if ((warningAt && nowMs >= warningAt.getTime()) || ticket.sla_warning) {
    return { state: 'warning', label: 'Warning', value: `${compactSeconds(remainingSeconds)} remaining` }
  }
  return { state: 'on_track', label: 'On track', value: `${compactSeconds(remainingSeconds)} remaining` }
}
