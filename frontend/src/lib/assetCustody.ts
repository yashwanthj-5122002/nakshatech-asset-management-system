import type { Asset } from '../types'

const ASSIGNED_STATUSES = new Set(['assigned', 'in_use', 'wfh', 'field_deployment', 'issued', 'permanently_issued'])
export const CUSTODY_ACTIONS = new Set(['handover', 'transfer', 'return'])

function normalizedAssetStatus(asset: Asset | null) {
  return (asset?.status || '').trim().toLowerCase().replaceAll('-', '_').replaceAll(' ', '_')
}

export function isAssignedAsset(asset: Asset | null) {
  return ASSIGNED_STATUSES.has(normalizedAssetStatus(asset))
}

export function hasRecordedCustodian(asset: Asset | null) {
  return isAssignedAsset(asset) && !!asset?.used_by?.trim()
}

export function canHandoverAsset(asset: Asset | null) {
  if (!asset) return false
  return normalizedAssetStatus(asset) === 'available' && !asset.used_by?.trim()
}

export function defaultCustodyAction(asset: Asset) {
  if (hasRecordedCustodian(asset)) return 'transfer'
  if (canHandoverAsset(asset)) return 'handover'
  return 'other'
}

export function custodyActionAllowed(asset: Asset | null, action: string) {
  if (!asset || !CUSTODY_ACTIONS.has(action)) return true
  if (action === 'handover') return canHandoverAsset(asset)
  if (action === 'transfer' || action === 'return') return hasRecordedCustodian(asset)
  return true
}

export function custodyGuidance(asset: Asset | null) {
  if (!asset) return 'Search and select an Asset Register record before using Handover, Transfer or Return.'
  const statusLabel = (asset.status || 'unknown').replaceAll('_', ' ')
  if (hasRecordedCustodian(asset)) {
    return `Assigned to ${asset.used_by}. Use Transfer to move custody to another employee, or Return to move custody back to IT / Company. Handover is disabled while the asset is assigned.`
  }
  if (isAssignedAsset(asset)) {
    return `Status is ${statusLabel}, but no current employee is recorded. Correct the Asset Register / Data Quality record before Transfer or Return so the previous custodian cannot be guessed.`
  }
  if (asset.used_by?.trim()) {
    return `Status is ${statusLabel}, but ${asset.used_by} is still recorded as the employee. Correct this inconsistent Asset Register / Data Quality record before changing custody.`
  }
  if (canHandoverAsset(asset)) {
    return `This asset is ${statusLabel} and unassigned. Handover is the only live custody action. Transfer and Return are disabled until a custodian is assigned.`
  }
  return `Status is ${statusLabel}. Live Handover, Transfer and Return are disabled until the asset is returned to an assignable lifecycle state.`
}
