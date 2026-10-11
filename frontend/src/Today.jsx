import { useEffect, useState } from "react";
import { getJSON, todayIST } from "./api.js";
import { ScanTable } from "./Gate.jsx";

export default function Today({ dashboard = false }) {
  const [regs, setRegs] = useState([]); const [scans, setScans] = useState([]); const [stats, setStats] = useState(null);
  const [err, setErr] = useState(""); const [filter, setFilter] = useState("ALL"); const [search, setSearch] = useState("");
  const load = () => {
    const jobs = [getJSON("/registrations"), getJSON("/scans?limit=50")];
    if (dashboard) jobs.push(getJSON("/dashboard/stats"));
    return Promise.all(jobs).then(([r,s,st])=>{setRegs(r);setScans(s);if(st)setStats(st);setErr("");}).catch(e=>setErr(e.message));
  };
  useEffect(() => { load(); }, [dashboard]);
  const today = todayIST(); const todays = regs.filter(r=>r.visit_date===today); const upcoming=regs.filter(r=>r.visit_date>today);
  const visible = regs.filter(r => `${r.name} ${r.vehicle_number} ${r.mobile || ""}`.toLowerCase().includes(search.toLowerCase()));
  const table = (rows) => rows.length ? <div className="table-wrap"><table><thead><tr><th>Plate</th><th>Visitor</th><th>Mobile</th><th>Visitors</th><th>Visit date</th><th>Registration</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td className="mono"><b>{r.vehicle_number}</b></td><td>{r.name}</td><td>{r.mobile || "—"}</td><td>{r.num_visitors}</td><td>{r.visit_date}</td><td><span className="pill REGISTERED">Registered</span></td></tr>)}</tbody></table></div> : <p className="muted empty">No matching registrations.</p>;
  return <>
    {err && <div className="notice err">{err}</div>}
    {dashboard && <><div className="stats-grid">{[["Registrations today",stats?.registrations_today],["Upcoming registrations",stats?.upcoming_registrations],["Vehicles scanned",stats?.scanned_today],["Access granted",stats?.granted],["Unregistered vehicles",stats?.unregistered],["Manual checks",stats?.manual_check]].map(([label,value])=><div className="stat-card" key={label}><span>{label}</span><strong>{value ?? "—"}</strong></div>)}</div><div className="card dashboard-actions"><div><h2>Gate operations</h2><p className="muted">Registrations are stored automatically. Match each arriving vehicle against today's records.</p></div><a className="button-link" href="#/guard/scan">Open ANPR scanner →</a><a className="button-link secondary-link" href="#/guard/registrations">View registrations →</a></div></>}
    {!dashboard && <div className="card"><h2>All registrations <button className="small" onClick={load}>Refresh</button></h2><div className="filters"><input aria-label="Search registrations" placeholder="Search name, plate, mobile…" value={search} onChange={e=>setSearch(e.target.value)}/><select value={filter} onChange={e=>setFilter(e.target.value)}><option value="ALL">All dates</option><option value="TODAY">Today</option><option value="UPCOMING">Upcoming</option></select></div>{table(visible.filter(r => filter === "TODAY" ? r.visit_date === today : filter === "UPCOMING" ? r.visit_date > today : true))}</div>}
    {dashboard && <div className="card"><h2>Today's registrations <button className="small" onClick={load}>Refresh</button></h2>{table(todays)}</div>}
    {dashboard && <div className="card"><h2>Upcoming visits</h2>{table(upcoming)}</div>}
    <div className="card"><h2>Recent gate scan history <button className="small" onClick={load}>Refresh</button></h2><ScanTable rows={scans}/></div>
  </>;
}
