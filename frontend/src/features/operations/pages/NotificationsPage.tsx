import { Bell, CheckCheck, RefreshCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { apiFetch } from '../../../lib/api'
import '../operations.css'

type Notification={id:number;event_type:string;category:string;title:string;message:string;target_url?:string|null;is_read:boolean;created_at:string}

export function NotificationsPage(){
  const navigate=useNavigate();const [rows,setRows]=useState<Notification[]>([]);const [error,setError]=useState('');const [busy,setBusy]=useState(false)
  function load(){setError('');void apiFetch<Notification[]>('/notifications/global?limit=100').then(setRows).catch(err=>setError(err instanceof Error?err.message:'Unable to load notifications'))}
  useEffect(load,[])
  async function open(row:Notification){try{if(!row.is_read)await apiFetch(`/notifications/global/${row.id}/read`,{method:'POST'});if(row.target_url?.startsWith('/')&&!row.target_url.startsWith('//'))navigate(row.target_url);else load()}catch(err){setError(err instanceof Error?err.message:'Unable to update notification')}}
  async function readAll(){setBusy(true);setError('');try{await apiFetch('/notifications/global/read-all',{method:'POST'});load()}catch(err){setError(err instanceof Error?err.message:'Unable to mark notifications read')}finally{setBusy(false)}}
  return <div className="operations-page"><DashboardHeader eyebrow="WORKFLOW COMMUNICATIONS" title="Notifications" description="Finance decisions, assignments, work transitions and closure updates for your account." actions={<><button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button><button className="operations-button" disabled={busy||!rows.some(row=>!row.is_read)} onClick={()=>void readAll()}><CheckCheck size={16}/> Mark All Read</button></>}/>{error&&<div className="operations-alert error">{error}</div>}<section className="operations-panel"><div className="operations-notification-list">{rows.map(row=><button key={row.id} className={row.is_read?'read':''} onClick={()=>void open(row)}><Bell size={17}/><div><strong>{row.title}</strong><p>{row.message}</p><small>{row.category.toUpperCase()} · {new Date(row.created_at).toLocaleString('en-IN')}</small></div>{!row.is_read&&<span/>}</button>)}</div>{!rows.length&&<div className="operations-empty">No notifications yet.</div>}</section></div>
}
