import { ArrowRight, BriefcaseBusiness, CheckCircle2, Link2, RefreshCcw, Send, Truck } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { DashboardHeader } from '../../../components/DashboardHeader'
import { StatCard } from '../../../components/StatCard'
import { apiFetch } from '../../../lib/api'
import '../operations.css'

type ClientOption = { id:number; client_code:string; client_name:string; is_active:boolean }
type ProjectOption = { id:number; project_code:string; project_name:string; client_name?:string|null; project_status:string }
type Opportunity = {
  id:number; opportunity_code:string; title:string; client_name?:string|null; requirement:string; priority:string; stage:string;
  expected_value?:number|null; linked_project?:ProjectOption|null; production_progress?:{progress_percent:number; total_packages:number; delivered_packages:number; stage_counts:Record<string,number>; total_hours:number}|null;
  updated_at:string; client_feedback?:string|null; technical_sample_notes?:string|null
}
type BDDashboard = {
  viewer_mode:'editor'|'read_only'; summary:{total:number;active:number;accepted:number;linked:number;delivery_ready:number;delivered:number};
  opportunities:Opportunity[]; clients:ClientOption[]; project_master:ProjectOption[]
}

type ClientMode = 'new' | 'existing'
const stages = ['opportunity','technical_sample','client_review','revision','accepted','finance_handoff','closed']
const workflow = [
  ['1','Prospect / Opportunity','BD records the new client requirement'],
  ['2','Technical Sample','BD coordinates sample output'],
  ['3','Client Review','Client reviews the sample'],
  ['4','Accepted','Client confirms the work'],
  ['5','Finance Handoff','Finance creates Client ID + Project ID'],
  ['6','Ortho Production','Project moves to the Ortho PM'],
]

function label(value:string){ return value.replaceAll('_',' ').replace(/\b\w/g, c=>c.toUpperCase()) }

export function BDDashboardPage(){
  const [data,setData]=useState<BDDashboard|null>(null)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [busy,setBusy]=useState(false)
  const [title,setTitle]=useState('')
  const [clientMode,setClientMode]=useState<ClientMode>('new')
  const [prospectName,setProspectName]=useState('')
  const [clientId,setClientId]=useState('')
  const [requirement,setRequirement]=useState('')
  const [priority,setPriority]=useState('medium')
  const [projectChoice,setProjectChoice]=useState<Record<number,string>>({})

  function load(){
    setError('')
    void apiFetch<BDDashboard>('/operations/bd/dashboard').then(setData).catch(err=>setError(err instanceof Error?err.message:'Unable to load BD dashboard'))
  }
  useEffect(load,[])
  const editor=data?.viewer_mode==='editor'
  const active=useMemo(()=>data?.opportunities.filter(item=>!['delivered','closed'].includes(item.stage))??[],[data])

  async function createOpportunity(event:FormEvent){
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    if(clientMode==='new'&&!prospectName.trim()){setBusy(false);setError('Enter the new prospect / company name.');return}
    if(clientMode==='existing'&&!clientId){setBusy(false);setError('Select an existing Client Master record.');return}
    try{
      await apiFetch('/operations/bd/opportunities',{method:'POST',body:JSON.stringify({
        title,
        client_id:clientMode==='existing'?Number(clientId):null,
        client_name:clientMode==='new'?prospectName.trim():null,
        requirement,
        priority,
        service_type:'ortho_lidar',
      })})
      setTitle('');setProspectName('');setClientId('');setRequirement('');setPriority('medium');setNotice('Opportunity created. New prospects stay in BD until client acceptance; Finance creates the official Client ID and Project ID after handoff.');load()
    }catch(err){setError(err instanceof Error?err.message:'Unable to create opportunity')}finally{setBusy(false)}
  }

  async function changeStage(item:Opportunity,stage:string){
    const comments=window.prompt(`Move ${item.opportunity_code} to ${label(stage)}. Optional comments:`,'')??''
    setBusy(true);setError('');setNotice('')
    try{await apiFetch(`/operations/bd/opportunities/${item.id}/stage`,{method:'PATCH',body:JSON.stringify({stage,comments})});setNotice(`${item.opportunity_code} moved to ${label(stage)}.`);load()}
    catch(err){setError(err instanceof Error?err.message:'Unable to change stage')}finally{setBusy(false)}
  }

  async function linkProject(item:Opportunity){
    const raw=projectChoice[item.id]
    if(!raw){setError('Select a Finance Project ID first.');return}
    setBusy(true);setError('');setNotice('')
    try{await apiFetch(`/operations/bd/opportunities/${item.id}/link-project`,{method:'POST',body:JSON.stringify({project_id:Number(raw),comments:'Linked from BD Dashboard after Finance created the official project'})});setNotice(`${item.opportunity_code} linked to Finance Project Master.`);load()}
    catch(err){setError(err instanceof Error?err.message:'Unable to link project')}finally{setBusy(false)}
  }

  return <div className="operations-page">
    <DashboardHeader eyebrow="BUSINESS DEVELOPMENT · CLIENT BRIDGE" title="BD Dashboard" description="New prospect → sample → client approval → Finance creates official Client ID + Project ID → Ortho PM production → final delivery." actions={<button className="operations-button secondary" onClick={load}><RefreshCcw size={16}/> Refresh</button>}/>
    {data?.viewer_mode==='read_only'&&<div className="operations-readonly">Read-only oversight: BD owns prospect/client workflow changes; Production/QC/QA remain controlled by the Ortho Project Manager.</div>}
    {notice&&<div className="success-message">{notice}</div>}{error&&<div className="error-message">{error}</div>}

    <section className="operations-panel operations-workflow-overview">
      <header><div><span className="operations-kicker">END-TO-END FLOW</span><h2>BD → Finance → Ortho</h2><p>A new BD prospect does not need to exist in Finance Client Master yet.</p></div></header>
      <div className="operations-flow-row">{workflow.map(([step,name,detail])=><div className="operations-flow-step" key={step}><span>{step}</span><strong>{name}</strong><small>{detail}</small></div>)}</div>
    </section>

    <section className="stats-grid">
      <StatCard icon={BriefcaseBusiness} label="Active Opportunities" value={data?.summary.active??'—'} />
      <StatCard icon={CheckCircle2} label="Client Accepted / Handoff" value={data?.summary.accepted??'—'} tone="green" />
      <StatCard icon={Link2} label="Finance Projects Linked" value={data?.summary.linked??'—'} tone="purple" />
      <StatCard icon={Send} label="Delivery Ready" value={data?.summary.delivery_ready??'—'} tone="orange" />
      <StatCard icon={Truck} label="Delivered" value={data?.summary.delivered??'—'} tone="green" />
    </section>

    {editor&&<section className="operations-panel"><header><div><span className="operations-kicker">STEP 1 · NEW CLIENT WORK</span><h2>Create Opportunity</h2><p>Choose <strong>New Prospect</strong> when BD found a client that Finance has not created yet. Choose <strong>Existing Client</strong> only when the client already exists in Client Master.</p></div></header><form className="operations-form-grid" onSubmit={createOpportunity}>
      <label className="operations-field"><span>Opportunity Title</span><input value={title} onChange={e=>setTitle(e.target.value)} required minLength={3} placeholder="Example: ABC City Ortho Mapping"/></label>
      <label className="operations-field"><span>Client Type</span><select value={clientMode} onChange={e=>setClientMode(e.target.value as ClientMode)}><option value="new">New Prospect — not in Finance yet</option><option value="existing">Existing Client — already in Client Master</option></select></label>
      {clientMode==='new'?<label className="operations-field"><span>Prospect / Company Name</span><input value={prospectName} onChange={e=>setProspectName(e.target.value)} required placeholder="Example: ABC Municipal Corporation"/></label>:<label className="operations-field"><span>Existing Client Master</span><select value={clientId} onChange={e=>setClientId(e.target.value)} required><option value="">Select existing client</option>{data?.clients.filter(c=>c.is_active).map(c=><option key={c.id} value={c.id}>{c.client_code} · {c.client_name}</option>)}</select></label>}
      <label className="operations-field"><span>Priority</span><select value={priority} onChange={e=>setPriority(e.target.value)}><option>low</option><option>medium</option><option>high</option><option>urgent</option></select></label>
      <label className="operations-field operations-span-2"><span>Requirement / Scope Received</span><textarea value={requirement} onChange={e=>setRequirement(e.target.value)} required minLength={5} placeholder="Example: 5 cm orthomosaic, DTM, contour and final delivery requirement"/></label>
      <div className="operations-note operations-span-2"><strong>Important:</strong> Do not create a Finance Client ID at this stage for a brand-new prospect. Move the opportunity through Sample → Client Review → Accepted → Finance Handoff first.</div>
      <div className="operations-actions operations-span-2"><button className="operations-button" disabled={busy}>Create Opportunity</button></div>
    </form></section>}

    <section className="operations-panel"><header><div><span className="operations-kicker">LIVE BUSINESS PIPELINE</span><h2>Opportunities & Production Status</h2><p>{active.length} currently active.</p></div></header>
      {!data?<div className="operations-empty">Loading BD workflow…</div>:data.opportunities.length===0?<div className="operations-empty">No BD opportunities yet.</div>:<div className="operations-table-wrap"><table className="operations-table"><thead><tr><th>Opportunity</th><th>Prospect / Client & Requirement</th><th>BD Stage</th><th>Official Finance Project ID</th><th>Ortho Progress</th><th>Status</th></tr></thead><tbody>{data.opportunities.map(item=><tr key={item.id}>
        <td><strong>{item.opportunity_code}</strong><small>{item.title}</small><small>{item.priority.toUpperCase()}</small></td>
        <td><strong>{item.client_name||'Prospect name not recorded'}</strong><small>{item.requirement}</small></td>
        <td><span className={`operations-status ${item.stage==='delivered'?'success':item.stage==='revision'?'warning':''}`}>{label(item.stage)}</span>{editor&&stages.includes(item.stage)&&<select value={item.stage} disabled={busy} onChange={e=>void changeStage(item,e.target.value)} style={{display:'block',marginTop:7}}>{stages.map(stage=><option key={stage} value={stage}>{label(stage)}</option>)}</select>}</td>
        <td>{item.linked_project?<><strong>{item.linked_project.project_code}</strong><small>{item.linked_project.project_name}</small></>:editor&&['accepted','finance_handoff'].includes(item.stage)?<div className="operations-actions"><select value={projectChoice[item.id]||''} onChange={e=>setProjectChoice(current=>({...current,[item.id]:e.target.value}))}><option value="">Select project created by Finance</option>{data.project_master.map(p=><option key={p.id} value={p.id}>{p.project_code} · {p.project_name} · {p.project_status}</option>)}</select><button className="operations-button secondary" type="button" onClick={()=>void linkProject(item)} disabled={busy}>Link</button></div>:<small>Finance project becomes selectable after client acceptance / handoff.</small>}</td>
        <td>{item.production_progress?<><strong>{item.production_progress.progress_percent}%</strong><div className="operations-progress"><span style={{width:`${Math.min(100,item.production_progress.progress_percent)}%`}}/></div><small>{item.production_progress.delivered_packages}/{item.production_progress.total_packages} packages delivered · {item.production_progress.total_hours} h</small></>:<small>No Ortho production yet</small>}</td>
        <td>{item.linked_project?<span className="operations-status">Live <ArrowRight size={12}/></span>:<small>BD / Finance workflow</small>}</td>
      </tr>)}</tbody></table></div>}
    </section>
  </div>
}
