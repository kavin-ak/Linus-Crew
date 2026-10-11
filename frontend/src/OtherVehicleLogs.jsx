import { useEffect, useState } from "react";
import { getJSON } from "./api.js";

export default function OtherVehicleLogs() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function load() {
    setLoading(true);
    try { setRows(await getJSON("/other-vehicle-logs?limit=200")); setError(""); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);
  return <div className="card">
    <h2>Other vehicle log <button className="small" onClick={load} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button></h2>
    <p className="muted">Visitor vehicles registered for a visit and unknown vehicles checked by security. Staff and college fleet vehicles are shown in their separate log.</p>
    {error && <div className="notice err">{error}</div>}
    {rows.length ? <div className="table-wrap"><table><thead><tr><th>Time (IST)</th><th>Plate</th><th>Vehicle class</th><th>Result</th><th>Vehicle status</th><th>Visitor</th><th>Guard</th><th>Details</th></tr></thead><tbody>
      {rows.map(row => <tr key={row.id}><td>{row.scanned_at}</td><td className="mono"><b>{row.plate}</b></td><td>{row.vehicle_type === "VISITOR" ? "Registered visitor" : "Other / unknown"}</td><td><span className={`pill ${row.status}`}>{row.status.replaceAll("_", " ")}</span></td><td>{row.vehicle_status || "—"}</td><td>{row.visitor_name || "—"}</td><td>{row.guard_username || "—"}</td><td>{row.details || "—"}</td></tr>)}
    </tbody></table></div> : !error && <p className="muted empty">No other vehicle scans have been recorded yet.</p>}
  </div>;
}
