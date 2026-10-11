import { useEffect, useState } from "react";
import { addFleetVehicle, deleteFleetVehicle, getJSON } from "./api.js";

export default function Fleet() {
  const [vehicles, setVehicles] = useState([]); const [logs, setLogs] = useState([]);
  const [form, setForm] = useState({ plate: "", category: "STAFF", owner_name: "", department: "", notes: "" });
  const [error, setError] = useState(""); const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  async function load() { try { const [v,l] = await Promise.all([getJSON("/fleet/vehicles"), getJSON("/fleet/logs?limit=100")]); setVehicles(v); setLogs(l); setError(""); } catch(e) { setError(e.message); } }
  useEffect(() => { load(); }, []);
  function change(e) { setForm({ ...form, [e.target.name]: e.target.value }); }
  async function submit(e) { e.preventDefault(); setBusy(true); setError(""); setMessage(""); try { await addFleetVehicle({ ...form, plate: form.plate.toUpperCase().replace(/[^A-Z0-9]/g, ""), department: form.department || null, notes: form.notes || null }); setMessage("Vehicle added to the staff/college database."); setForm({ plate:"", category:"STAFF", owner_name:"", department:"", notes:"" }); await load(); } catch(e) { setError(e.message); } finally { setBusy(false); } }
  async function remove(id) { if (!confirm("Remove this plate from the registered staff/college vehicle database? Existing logs will remain.")) return; try { await deleteFleetVehicle(id); await load(); } catch(e) { setError(e.message); } }
  return <>
    <div className="card"><h2>Register staff or college vehicle</h2><p className="muted">These plates are stored in the separate <code>fleet.db</code>. Exact matches are automatically added to the dedicated vehicle log.</p>
      <form onSubmit={submit} className="fleet-form"><div className="row"><label>Number plate<input name="plate" value={form.plate} onChange={change} placeholder="TN37AB1234" required minLength={6} maxLength={20}/></label><label>Vehicle category<select name="category" value={form.category} onChange={change}><option value="STAFF">Staff vehicle</option><option value="COLLEGE">College vehicle</option></select></label></div>
      <div className="row"><label>Staff name / vehicle name<input name="owner_name" value={form.owner_name} onChange={change} placeholder="Name or college bus" required/></label><label>Department (optional)<input name="department" value={form.department} onChange={change} placeholder="e.g. Administration"/></label></div>
      <label>Notes (optional)<input name="notes" value={form.notes} onChange={change} placeholder="Vehicle model, purpose, etc."/></label><button disabled={busy}>{busy ? "Saving…" : "Add vehicle"}</button></form>
      {error && <div className="notice err">{error}</div>}{message && <div className="notice ok">{message}</div>}
    </div>
    <div className="card"><h2>Registered staff & college vehicles <button className="small" onClick={load}>Refresh</button></h2>{vehicles.length ? <div className="table-wrap"><table><thead><tr><th>Plate</th><th>Type</th><th>Name / vehicle</th><th>Department</th><th>Current status</th><th>Action</th></tr></thead><tbody>{vehicles.map(v=><tr key={v.id}><td className="mono"><b>{v.plate}</b></td><td>{v.category}</td><td>{v.owner_name}</td><td>{v.department || "—"}</td><td><b>{v.vehicle_status || "OUTSIDE CAMPUS"}</b></td><td><button className="small deny-button" onClick={()=>remove(v.id)}>Remove</button></td></tr>)}</tbody></table></div> : <p className="muted">No staff or college vehicles registered yet.</p>}</div>
    <div className="card"><h2>Dedicated vehicle entry log <button className="small" onClick={load}>Refresh</button></h2><p className="muted">Only staff and college vehicles appear here. Visitor and unknown-vehicle decisions are recorded in the separate Other vehicle log.</p>{logs.length ? <div className="table-wrap"><table><thead><tr><th>Time (IST)</th><th>Plate</th><th>Category</th><th>Name / vehicle</th><th>Permission</th><th>Vehicle status</th><th>Guard</th></tr></thead><tbody>{logs.map(l=><tr key={l.id}><td>{l.entered_at}</td><td className="mono"><b>{l.plate}</b></td><td>{l.category}</td><td>{l.owner_name || "Manual entry"}</td><td><span className="pill GRANTED">{l.permission.replaceAll("_", " ")}</span></td><td><b>{l.vehicle_status || "INSIDE CAMPUS"}</b></td><td>{l.guard_username}</td></tr>)}</tbody></table></div> : <p className="muted">No vehicle entries logged yet.</p>}</div>
  </>;
}
