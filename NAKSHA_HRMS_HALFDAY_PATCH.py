#!/usr/bin/env python3
"""NakshaTech ERP safe frontend HALF-DAY patch installer.

Only changes: frontend/src/features/hrms/HRMSPages.tsx.
Does not implement the server endpoints, database migrations or leave accounting.

Usage (from project root):
    python NAKSHA_HRMS_HALFDAY_PATCH.py --check
    python NAKSHA_HRMS_HALFDAY_PATCH.py --preview
    python NAKSHA_HRMS_HALFDAY_PATCH.py --apply-frontend

Requires the known HRMSPages.tsx layout. Fails without modifying files if
an expected anchor is different. Backups are stored outside the repo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import os
from pathlib import Path
import sys
import tempfile

FRONTEND_REL = Path("frontend/src/features/hrms/HRMSPages.tsx")
NEEDED_ROUTES = (
    "PUT /hrms/me/leave/{id} (pending-only edit)",
    "POST /hrms/me/leave/{id}/request-cancellation",
    "POST /hrms/hr/leave/{id}/cancellation-decision",
)


def sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def scan_backend(root: Path) -> None:
    # A static, advisory inventory. It cannot prove API behavior or permissions.
    pyroot = root / "backend" / "app"
    if not pyroot.is_dir():
        print("BACKEND: backend/app missing. Full feature cannot be validated.")
        return
    fragments = {
        "pending edit": "/me/leave/{",
        "cancellation request": "/request-cancellation",
        "HR cancellation decision": "/cancellation-decision",
        "half-day persistence": "half_day_session",
        "monthly accounting": "approved_chargeable_days",
    }
    files = list(pyroot.rglob("*.py"))
    texts = []
    for f in files:
        try:
            texts.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    joined = "\n".join(texts)
    for title, needle in fragments.items():
        print(f"BACKEND CHECK: {title}: {'reference found (not verified)' if needle in joined else 'NOT FOUND'}")
    print("NOTE: Backend checks do NOT validate permissions, schema, migrations, or leave balances.")
    print("This patch deliberately leaves ALL backend and database files unchanged.")


def transform(src: str) -> str:
    t = src

    def rep(old: str, new: str, count: int = 1) -> None:
        nonlocal t
        n = t.count(old)
        if n != count:
            raise ValueError(f"Unexpected HRMSPages.tsx layout: expected {count} occurrence(s), got {n}: {old[:100]!r}")
        t = t.replace(old, new, count)

    changes = [
        ('type Leave = { id: number; user_id: number; leave_type: string; from_date: string; to_date: string; requested_calendar_days: number; reason: string; status: string; decision_note: string | null; employee_name?: string }', "type Leave = { id: number; user_id: number; leave_type: string; from_date: string; to_date: string; requested_calendar_days: number; reason: string; status: string; decision_note: string | null; employee_name?: string; duration?: 'full_day' | 'half_day'; half_day_session?: 'morning' | 'afternoon' | null; office_time?: string | null; cancellation_status?: 'pending' | 'approved' | 'rejected' | null }", 1),
        ('type HROverview = { date: string; employees: HREmployee[]; pending_leaves: Leave[]; pending_explanations: Explanation[]; notice: string }', 'type HROverview = { date: string; employees: HREmployee[]; pending_leaves: Leave[]; pending_explanations: Explanation[]; pending_cancellations?: Leave[]; notice: string }', 1),
        ("const LEAVE_OPTIONS = ['paid', 'casual', 'sick', 'earned', 'unpaid'] as const", "const LEAVE_OPTIONS = ['paid', 'casual', 'sick', 'earned', 'unpaid'] as const\n// Leave category and duration are separate: 0.5 day is not a new payroll category.\ntype LeaveForm = { leave_type: string; from_date: string; to_date: string; duration: 'full_day' | 'half_day'; half_day_session: 'morning' | 'afternoon'; office_time: string; reason: string }\nconst newLeaveForm = (): LeaveForm => ({ leave_type: 'casual', from_date: todayIST(), to_date: todayIST(), duration: 'full_day', half_day_session: 'morning', office_time: '', reason: '' })\nconst leaveDays = (item: Leave) => item.duration === 'half_day' ? 0.5 : item.requested_calendar_days\nconst leaveSession = (item: Leave) => item.duration === 'half_day' ? `Half day · ${item.half_day_session === 'afternoon' ? 'Afternoon' : 'Morning'}` : 'Full day'\nconst officeTimeLabel = (item: Leave) => item.duration === 'half_day' && item.office_time ? ` · ${item.half_day_session === 'morning' ? 'Return' : 'Exit'} ${item.office_time}` : ''\n// A monthly summary never combines half-day requests across different months.\nfunction halfDayMonthlyTotals(leaves: Leave[]) {\n  const totals = new Map<string, number>()\n  for (const item of leaves) {\n    if (item.duration !== 'half_day' || item.status !== 'approved' || item.cancellation_status === 'approved') continue\n    const month = item.from_date.slice(0, 7)\n    totals.set(month, (totals.get(month) ?? 0) + 1)\n  }\n  return [...totals.entries()].sort(([a], [b]) => b.localeCompare(a)).map(([month, count]) => ({ month, count, days: count * 0.5 }))\n}", 1),
        ("  const [form, setForm] = useState({ leave_type: 'casual', from_date: todayIST(), to_date: todayIST(), reason: '' })", '  const [form, setForm] = useState<LeaveForm>(newLeaveForm)\n  const [editingId, setEditingId] = useState<number | null>(null)', 1),
        ("  async function apply(event: FormEvent) {\n    event.preventDefault(); setBusy(true); setNotice(''); setError('')\n    try {\n      await apiFetch('/hrms/me/leave', { method: 'POST', body: JSON.stringify(form) })\n      setNotice('Leave application submitted to HR for review.')\n      setApplicationTab('pending')\n      setForm(current => ({ ...current, reason: '' }))\n      await load()\n    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }\n  }\n  async function withdraw(id: number) {\n    if (!window.confirm('Withdraw this pending leave application?')) return\n    try { await apiFetch(`/hrms/me/leave/${id}/cancel`, { method: 'POST' }); await load() }\n    catch (err) { setError(errorText(err)) }\n  }\n", "  async function apply(event: FormEvent) {\n    event.preventDefault(); setNotice(''); setError('')\n    if (form.duration === 'half_day' && (!form.office_time || form.from_date !== form.to_date)) {\n      setError('Half-day leave requires one date and an expected office exit/return time.')\n      return\n    }\n    setBusy(true)\n    try {\n      const payload = {\n        leave_type: form.leave_type,\n        from_date: form.from_date,\n        to_date: form.duration === 'half_day' ? form.from_date : form.to_date,\n        reason: form.reason,\n        duration: form.duration,\n        half_day_session: form.duration === 'half_day' ? form.half_day_session : null,\n        office_time: form.duration === 'half_day' ? form.office_time : null,\n      }\n      if (editingId === null) {\n        await apiFetch('/hrms/me/leave', { method: 'POST', body: JSON.stringify(payload) })\n        setNotice('Leave application submitted to HR for review.')\n      } else {\n        await apiFetch(`/hrms/me/leave/${editingId}`, { method: 'PUT', body: JSON.stringify(payload) })\n        setNotice('Pending leave application updated. HR will review the latest version.')\n      }\n      setEditingId(null)\n      setForm(newLeaveForm())\n      setApplicationTab('pending')\n      await load()\n    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }\n  }\n  function editPending(item: Leave) {\n    if (item.status !== 'pending') return\n    setEditingId(item.id)\n    setForm({\n      leave_type: item.leave_type,\n      from_date: item.from_date,\n      to_date: item.duration === 'half_day' ? item.from_date : item.to_date,\n      duration: item.duration === 'half_day' ? 'half_day' : 'full_day',\n      half_day_session: item.half_day_session === 'afternoon' ? 'afternoon' : 'morning',\n      office_time: item.office_time ?? '',\n      reason: item.reason,\n    })\n    setApplicationTab('apply')\n    setError(''); setNotice('')\n  }\n  function stopEditing() { setEditingId(null); setForm(newLeaveForm()); setError('') }\n  async function withdraw(id: number) {\n    if (!window.confirm('Withdraw this pending leave application?')) return\n    setBusy(true); setError('')\n    try {\n      await apiFetch(`/hrms/me/leave/${id}/cancel`, { method: 'POST' })\n      setNotice('Pending leave application withdrawn.')\n      await load()\n    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }\n  }\n  async function requestApprovedCancellation(id: number) {\n    const reason = window.prompt('Reason for requesting cancellation of an APPROVED leave (HR must approve):', '')\n    if (reason === null) return\n    if (reason.trim().length < 5) { setError('Please provide at least five characters as the cancellation reason.'); return }\n    setBusy(true); setError(''); setNotice('')\n    try {\n      await apiFetch(`/hrms/me/leave/${id}/request-cancellation`, { method: 'POST', body: JSON.stringify({ reason: reason.trim() }) })\n      setNotice('Cancellation request sent to HR. The original leave remains approved until HR accepts the cancellation.')\n      await load()\n    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }\n  }\n", 1),
        ('  const filtered = useMemo(() => [...requests].sort((a, b) => b.from_date.localeCompare(a.from_date)), [requests])', '  const filtered = useMemo(() => [...requests].sort((a, b) => b.from_date.localeCompare(a.from_date)), [requests])\n  const monthlyHalfDays = useMemo(() => halfDayMonthlyTotals(requests), [requests])', 1),
        ('      <div className="hrms-row"><div><p className="hrms-section-eyebrow">EMPLOYEE LEAVE DESK</p><h2>Apply for leave</h2></div><Link className="hrms-secondary hrms-inline-action" to="/hrms/leave/balance">View balance</Link></div>', '      <div className="hrms-row"><div><p className="hrms-section-eyebrow">EMPLOYEE LEAVE DESK</p><h2>{editingId === null ? \'Apply for leave\' : `Edit pending leave #${editingId}`}</h2></div><Link className="hrms-secondary hrms-inline-action" to="/hrms/leave/balance">View balance</Link></div>', 1),
        ('        <label>Leave type<select required value={form.leave_type} onChange={e => setForm({ ...form, leave_type: e.target.value })}>{LEAVE_OPTIONS.map(t => <option key={t} value={t}>{statusName(t)}</option>)}</select></label>\n        <label>From date<input type="date" required value={form.from_date} onChange={e => setForm({ ...form, from_date: e.target.value })}/></label>\n        <label>To date<input type="date" required min={form.from_date} value={form.to_date} onChange={e => setForm({ ...form, to_date: e.target.value })}/></label>\n        <label>Available paid leave<input readOnly value={balance?.balances.find(b => b.leave_type === \'paid\')?.remaining_provisional ?? \'Awaiting HR policy\'}/></label>', '        <label>Leave type<select required value={form.leave_type} onChange={e => setForm({ ...form, leave_type: e.target.value })}>{LEAVE_OPTIONS.map(t => <option key={t} value={t}>{statusName(t)}</option>)}</select></label>\n        <label>Leave duration<select required value={form.duration} onChange={e => {\n          const duration = e.target.value as LeaveForm[\'duration\']\n          setForm(current => ({ ...current, duration, to_date: duration === \'half_day\' ? current.from_date : current.to_date }))\n        }}><option value="full_day">Full day</option><option value="half_day">Half day (0.5)</option></select></label>\n        <label>From date<input type="date" required value={form.from_date} onChange={e => setForm({ ...form, from_date: e.target.value, to_date: form.duration === \'half_day\' ? e.target.value : form.to_date })}/></label>\n        <label>To date<input type="date" required disabled={form.duration === \'half_day\'} min={form.from_date} value={form.duration === \'half_day\' ? form.from_date : form.to_date} onChange={e => setForm({ ...form, to_date: e.target.value })}/></label>\n        {form.duration === \'half_day\' && <>\n          <label>Half-day session<select value={form.half_day_session} onChange={e => setForm({ ...form, half_day_session: e.target.value as LeaveForm[\'half_day_session\'], office_time: \'\' })} required>\n            <option value="morning">Morning to noon (first half)</option><option value="afternoon">Noon to end of day (second half)</option>\n          </select></label>\n          <label>{form.half_day_session === \'morning\' ? \'Expected office return time\' : \'Expected office leaving time\'}<input type="time" required value={form.office_time} onChange={e => setForm({ ...form, office_time: e.target.value })}/></label>\n          <p className="hrms-muted hrms-form-wide">This is a planned time supplied with the request. Actual check-in/out remains recorded separately by attendance.</p>\n        </>}\n        <label>Available paid leave<input readOnly value={balance?.balances.find(b => b.leave_type === \'paid\')?.remaining_provisional ?? \'Awaiting HR policy\'}/></label>', 1),
        ('        <button disabled={busy} className="hrms-primary">{busy ? \'Submitting...\' : \'Submit leave request\'}</button>', '        <button disabled={busy} className="hrms-primary">{busy ? \'Saving...\' : editingId === null ? \'Submit leave request\' : \'Save pending changes\'}</button>\n        {editingId !== null && <button type="button" className="hrms-secondary" disabled={busy} onClick={stopEditing}>Cancel edit</button>}', 1),
        ('      {applicationTab !== \'apply\' && <div className="hrms-table-wrap"><table><thead><tr><th>Dates</th><th>Type</th><th>Status</th><th>HR note</th><th>Action</th></tr></thead>\n        <tbody>{filtered.filter(x => applicationTab === \'pending\' ? x.status === \'pending\' : x.status !== \'pending\').map(item => <tr key={item.id}><td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}</td><td><Badge status={item.status}/></td><td>{item.decision_note || \'—\'}</td><td>{item.status === \'pending\' && <button className="hrms-small" onClick={() => void withdraw(item.id)}>Withdraw</button>}</td></tr>)}</tbody></table>\n        {!filtered.some(x => applicationTab === \'pending\' ? x.status === \'pending\' : x.status !== \'pending\') && <div className="hrms-empty">No {applicationTab} applications.</div>}\n      </div>}', '      {applicationTab !== \'apply\' && <>\n        {applicationTab === \'history\' && <section aria-label="Monthly approved half-day summary" className="hrms-panel">\n          <h3>Approved half-day totals by month</h3>\n          <p className="hrms-muted">Two approved half-days in the same month = one day. Different months remain separate. Requests are not merged or deleted.</p>\n          {monthlyHalfDays.length ? <div className="hrms-grid">{monthlyHalfDays.map(m => <article className="hrms-metric" key={m.month}><span>{m.month}</span><strong>{m.days} {m.days === 1 ? \'day\' : \'days\'}</strong><small>{m.count} approved half-day requests</small></article>)}</div> : <p className="hrms-muted">No approved half-day leave recorded.</p>}\n        </section>}\n        <div className="hrms-table-wrap"><table><thead><tr><th>Dates</th><th>Type</th><th>Duration / session</th><th>Status</th><th>HR note</th><th>Action</th></tr></thead>\n          <tbody>{filtered.filter(x => applicationTab === \'pending\' ? x.status === \'pending\' : x.status !== \'pending\').map(item => <tr key={item.id}>\n            <td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}</td>\n            <td>{leaveSession(item)} · {leaveDays(item)} day{leaveDays(item) === 1 ? \'\' : \'s\'}{officeTimeLabel(item)}</td>\n            <td><Badge status={item.status}/>{item.cancellation_status === \'pending\' && <small> · Cancellation awaiting HR</small>}{item.cancellation_status === \'rejected\' && <small> · Cancellation declined</small>}</td>\n            <td>{item.decision_note || \'—\'}</td>\n            <td><div className="hrms-actions">\n              {item.status === \'pending\' && <><button type="button" disabled={busy} className="hrms-small" onClick={() => editPending(item)}>Edit</button><button type="button" disabled={busy} className="hrms-small" onClick={() => void withdraw(item.id)}>Withdraw</button></>}\n              {item.status === \'approved\' && !item.cancellation_status && <button type="button" disabled={busy} className="hrms-small" onClick={() => void requestApprovedCancellation(item.id)}>Request cancellation</button>}\n            </div></td>\n          </tr>)}</tbody></table>\n          {!filtered.some(x => applicationTab === \'pending\' ? x.status === \'pending\' : x.status !== \'pending\') && <div className="hrms-empty">No {applicationTab} applications.</div>}\n        </div>\n      </>}', 1),
        ("        {leaves.filter(l => l.status !== 'cancelled' && l.status !== 'rejected' && l.from_date <= day && l.to_date >= day).map(l => <span key={l.id} className={`hrms-calendar-event ${l.status}`}>{statusName(l.leave_type)} · {l.status}</span>)}", "        {leaves.filter(l => l.status !== 'cancelled' && l.status !== 'rejected' && l.from_date <= day && l.to_date >= day).map(l => <span key={l.id} className={`hrms-calendar-event ${l.status}`}>{statusName(l.leave_type)} · {leaveSession(l)} · {l.status}</span>)}", 1),
        ('      <tbody>{filtered.map(item => <tr key={item.id}><td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}</td><td>{item.requested_calendar_days}</td><td><Badge status={item.status}/></td><td>{item.decision_note || \'—\'}</td><td>{item.status === \'pending\' && <button className="hrms-small" onClick={() => void withdraw(item.id)}>Withdraw</button>}</td></tr>)}</tbody></table>', '      <tbody>{filtered.map(item => <tr key={item.id}><td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}{item.duration === \'half_day\' ? ` · ${leaveSession(item)}${officeTimeLabel(item)}` : \'\'}</td><td>{leaveDays(item)}</td><td><Badge status={item.status}/>{item.cancellation_status === \'pending\' && <small> · Cancellation awaiting HR</small>}</td><td>{item.decision_note || \'—\'}</td><td>{item.status === \'pending\' && <button className="hrms-small" onClick={() => void withdraw(item.id)}>Withdraw</button>}</td></tr>)}</tbody></table>', 1),
        ("  async function decide(kind: 'leave' | 'absence', id: number, status: 'approved' | 'rejected') {\n    setBusy(true); setError(''); setNotice('')\n    try { const note = window.prompt('Optional HR decision note:', '') ; if (note === null) return\n      await apiFetch(`/hrms/hr/${kind}/${id}/decision`, { method: 'POST', body: JSON.stringify({ status, note }) })\n      setNotice(`Request ${status}.`); await Promise.all([load(), loadAlerts()])\n      if (selectedEmployee !== null) await openHistory(selectedEmployee, historyYear)\n    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }\n  }", "  async function decide(kind: 'leave' | 'absence', id: number, status: 'approved' | 'rejected') {\n    setBusy(true); setError(''); setNotice('')\n    try { const note = window.prompt('Optional HR decision note:', '') ; if (note === null) return\n      await apiFetch(`/hrms/hr/${kind}/${id}/decision`, { method: 'POST', body: JSON.stringify({ status, note }) })\n      setNotice(`Request ${status}.`); await Promise.all([load(), loadAlerts()])\n      if (selectedEmployee !== null) await openHistory(selectedEmployee, historyYear)\n    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }\n  }\n  async function decideCancellation(id: number, status: 'approved' | 'rejected') {\n    const note = window.prompt(`Reason for ${status === 'approved' ? 'approving' : 'rejecting'} this cancellation:`, '')\n    if (note === null) return\n    setBusy(true); setError(''); setNotice('')\n    try {\n      await apiFetch(`/hrms/hr/leave/${id}/cancellation-decision`, { method: 'POST', body: JSON.stringify({ status, note }) })\n      setNotice(status === 'approved' ? 'Leave cancellation approved. Leave balance will be recalculated.' : 'Cancellation rejected. Original leave remains approved.')\n      await Promise.all([load(), loadAlerts()])\n      if (selectedEmployee !== null) await openHistory(selectedEmployee, historyYear)\n    } catch (err) { setError(errorText(err)) } finally { setBusy(false) }\n  }", 1),
        ('        <p className="hrms-muted">* The leave history table records requested calendar days. Available leave is based on HR-configured working weekdays and HR-verified company holidays, not payroll postings.</p>', '        <p className="hrms-muted">* Full-day leave uses the existing HR policy; half-day leave counts as 0.5 day per approved request. Office times are planned, not verified attendance punches.</p>\n        {halfDayMonthlyTotals(history.requests).length > 0 && <div className="hrms-grid">{halfDayMonthlyTotals(history.requests).map(m => <article className="hrms-metric" key={m.month}><span>{m.month} approved half-days</span><strong>{m.days} day{m.days === 1 ? \'\' : \'s\'}</strong><small>{m.count} half-day requests in this month</small></article>)}</div>}', 1),
        ("<tbody>{history.requests.map(item => <tr key={item.id}><td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}</td><td>{item.requested_calendar_days}</td><td>{item.reason}</td><td><Badge status={item.status}/></td><td>{item.decision_note ?? '—'}</td></tr>)}</tbody>", "<tbody>{history.requests.map(item => <tr key={item.id}><td>{item.from_date} → {item.to_date}</td><td>{statusName(item.leave_type)}{item.duration === 'half_day' ? ` · ${leaveSession(item)}${officeTimeLabel(item)}` : ''}</td><td>{leaveDays(item)}</td><td>{item.reason}</td><td><Badge status={item.status}/>{item.cancellation_status === 'pending' && <small> · Cancellation awaiting HR</small>}</td><td>{item.decision_note ?? '—'}</td></tr>)}</tbody>", 1),
        ('<tbody>{data?.pending_leaves.map(x => <tr key={x.id}><td><button type="button" className="hrms-employee-link" onClick={() => void openHistory(x.user_id, historyYear)}>{x.employee_name}</button></td><td>{x.from_date} → {x.to_date}<small>{x.requested_calendar_days} provisional calendar days</small></td><td>{statusName(x.leave_type)}</td><td>{x.reason}</td><td><div className="hrms-actions"><button disabled={busy} onClick={() => void decide(\'leave\', x.id, \'approved\')} className="hrms-small">Approve</button><button disabled={busy} onClick={() => void decide(\'leave\', x.id, \'rejected\')} className="hrms-small">Reject</button></div></td></tr>)}</tbody>', '<tbody>{data?.pending_leaves.map(x => <tr key={x.id}><td><button type="button" className="hrms-employee-link" onClick={() => void openHistory(x.user_id, historyYear)}>{x.employee_name}</button></td><td>{x.from_date} → {x.to_date}<small>{leaveDays(x)} provisional day(s){x.duration === \'half_day\' ? ` · ${leaveSession(x)}${officeTimeLabel(x)}` : \'\'}</small></td><td>{statusName(x.leave_type)}</td><td>{x.reason}</td><td><div className="hrms-actions"><button disabled={busy} onClick={() => void decide(\'leave\', x.id, \'approved\')} className="hrms-small">Approve</button><button disabled={busy} onClick={() => void decide(\'leave\', x.id, \'rejected\')} className="hrms-small">Reject</button></div></td></tr>)}</tbody>', 1),
        ('      {!data?.pending_leaves.length && <p>No pending leave applications.</p>}</div></section>', '      {!data?.pending_leaves.length && <p>No pending leave applications.</p>}</div></section>\n    {Boolean(data?.pending_cancellations?.length) && <section className="hrms-panel" aria-label="Approved leave cancellation requests">\n      <h2>Approved leave cancellation requests</h2>\n      <p className="hrms-muted">The original leave remains approved and charged until HR accepts cancellation. Approval restores its leave entitlement through backend recalculation.</p>\n      <div className="hrms-table-wrap"><table><thead><tr><th>Employee</th><th>Leave dates</th><th>Duration</th><th>Decision</th></tr></thead><tbody>\n        {data?.pending_cancellations?.map(item => <tr key={item.id}><td>{item.employee_name ?? `User ${item.user_id}`}</td><td>{item.from_date} → {item.to_date}</td><td>{leaveSession(item)} · {leaveDays(item)} day(s){officeTimeLabel(item)}</td>\n          <td><div className="hrms-actions"><button type="button" disabled={busy} className="hrms-small" onClick={() => void decideCancellation(item.id, \'approved\')}>Accept cancellation</button><button type="button" disabled={busy} className="hrms-small" onClick={() => void decideCancellation(item.id, \'rejected\')}>Reject cancellation</button></div></td></tr>)}\n      </tbody></table></div>\n    </section>}', 1),
    ]
    for old, new, count in changes:
        rep(old, new, count)
    return t


def main() -> int:
    p = argparse.ArgumentParser(description="Safe frontend-only HRMS half-day patch")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Inspect files only; do not modify")
    mode.add_argument("--preview", action="store_true", help="Write a preview to the OS temp directory only")
    mode.add_argument("--apply-frontend", action="store_true", help="Patch frontend with an external backup (backend unchanged)")
    args = p.parse_args()
    root = Path.cwd().resolve()
    dest = root / FRONTEND_REL
    if not (root / 'frontend' / 'package.json').is_file():
        print('REFUSED: run from ERP project root; frontend/package.json is missing.', file=sys.stderr)
        return 2
    if not dest.is_file():
        print(f'REFUSED: cannot find {dest}', file=sys.stderr)
        return 2
    src = dest.read_text(encoding='utf-8-sig')
    print('TARGET:', dest)
    print('CURRENT SHA256:', sha256(src))
    if 'function halfDayMonthlyTotals(' in src and 'decideCancellation(' in src:
        print('ALREADY PATCHED: frontend features detected, no changes made.')
        scan_backend(root)
        return 0
    try:
        result = transform(src)
    except ValueError as exc:
        print('REFUSED: source differs from the supplied HRMSPages.tsx. No files modified.', file=sys.stderr)
        print(exc, file=sys.stderr)
        scan_backend(root)
        return 3
    if result == src:
        print('UNCHANGED')
        return 0
    print('PATCHED SHA256:', sha256(result))
    print('DIFF PREVIEW (first 35 noncontext lines):')
    diff = difflib.unified_diff(src.splitlines(), result.splitlines(), fromfile='current', tofile='patched', lineterm='')
    shown = 0
    for line in diff:
        if line.startswith(('+++','---','@@')) or line.startswith(('+','-')):
            print(line[:180])
            shown += 1
            if shown >= 35:
                break
    print('')
    scan_backend(root)
    print('CRITICAL: Without backend API updates, half-day submissions may not persist correctly.')
    print('This file adds FRONTEND CONTROLS ONLY. It is NOT a complete working server patch.')
    if args.check:
        print('CHECK COMPLETE: No files changed.')
        return 0
    if args.preview:
        outfile = Path(tempfile.gettempdir()) / 'NAKSHA_HRMSPages_halfday_preview.tsx'
        outfile.write_text(result, encoding='utf-8')
        print('PREVIEW WRITTEN:', outfile)
        print('Original project files unchanged.')
        return 0
    # Existing source might be part of a colleague's current work. We never silently overwrite mismatched anchors.
    backup_dir = (Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'NakshaTech' / 'hrms-patch-backups')
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = backup_dir / f'HRMSPages_before_halfday_{timestamp}_{sha256(src)[:8]}.tsx'
    backup.write_text(src, encoding='utf-8')
    print('BACKUP:', backup)
    # Atomic replace of exactly one frontend file. Never touch backend or DB.
    tmp = dest.with_name(dest.name + '.naksha-writing')
    try:
        tmp.write_text(result, encoding='utf-8')
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink()
    print('FRONTEND PATCH APPLIED:', dest)
    print('NEXT: cd frontend && npm.cmd run build')
    print('DO NOT use new leave actions until backend APIs and migration are implemented and tested.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
