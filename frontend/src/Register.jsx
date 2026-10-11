import { useState } from "react";
import { PLATE_RE, cleanPlate, register, todayIST, getJSON } from "./api.js";

const blank = () => ({
  name: "", vehicle_number: "", mobile: "", address: "", num_visitors: 1, visit_date: todayIST(),
});

function validate(f) {
  const e = {};
  if (f.name.trim().length < 2) e.name = "Enter your full name";
  if (!PLATE_RE.test(cleanPlate(f.vehicle_number))) e.vehicle_number = "Format like TN37AB1234";
  if (!/^\d{10}$/.test(f.mobile.replace(/[\s-]/g, "").replace(/^\+91/, ""))) e.mobile = "10-digit mobile number";
  if (f.address.trim().length < 3) e.address = "Enter your address";
  const n = Number(f.num_visitors);
  if (!Number.isInteger(n) || n < 1 || n > 10) e.num_visitors = "Between 1 and 10";
  if (!f.visit_date || f.visit_date < todayIST()) e.visit_date = "Date cannot be in the past";
  return e;
}

export default function Register() {
  const [f, setF] = useState(blank);
  const [errs, setErrs] = useState({});
  const [msg, setMsg] = useState(null); // {ok, text}
  const [busy, setBusy] = useState(false);
  const [reference, setReference] = useState("");
  const [statusResult, setStatusResult] = useState(null);
  const [statusError, setStatusError] = useState("");

  const set = (k) => (ev) => setF({ ...f, [k]: ev.target.value });

  async function submit(ev) {
    ev.preventDefault();
    const e = validate(f);
    setErrs(e);
    setMsg(null);
    if (Object.keys(e).length) return;
    setBusy(true);
    try {
      const d = await register({ ...f, num_visitors: Number(f.num_visitors) });
      const r = d.registration;
      setMsg({ ok: true, text: `Registration saved for ${r.vehicle_number} on ${r.visit_date}. Security will check this registration during the gate scan.`, reference: r.reference });
      setF(blank());
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  }

  async function checkStatus(e) {
    e.preventDefault(); setStatusError(""); setStatusResult(null);
    if (!reference.trim()) { setStatusError("Enter the private reference from your confirmation."); return; }
    try { setStatusResult(await getJSON("/visitor/status/" + encodeURIComponent(reference.trim()))); }
    catch (err) { setStatusError(err.message); }
  }

  const field = (k, label, input) => (
    <label className={errs[k] ? "bad" : ""}>
      <span>{label}</span>
      {input}
      {errs[k] && <small>{errs[k]}</small>}
    </label>
  );

  return (
    <div className="card narrow">
      <h1>Visitor registration</h1>
      <p className="muted">Register your visit and vehicle. Security will verify your number plate against this registration when you arrive.</p>
      <form onSubmit={submit} noValidate>
        {field("name", "Name", <input value={f.name} onChange={set("name")} autoComplete="name" />)}
        {field("vehicle_number", "Vehicle number",
          <input value={f.vehicle_number} onChange={set("vehicle_number")} placeholder="TN37AB1234"
                 className="mono" style={{ textTransform: "uppercase" }} />)}
        {field("mobile", "Mobile number",
          <input value={f.mobile} onChange={set("mobile")} inputMode="numeric" placeholder="10 digits" autoComplete="tel" />)}
        {field("address", "Address", <textarea rows={2} value={f.address} onChange={set("address")} />)}
        <div className="row">
          {field("num_visitors", "Number of visitors",
            <input type="number" min={1} max={10} value={f.num_visitors} onChange={set("num_visitors")} />)}
          {field("visit_date", "Visit date",
            <input type="date" min={todayIST()} value={f.visit_date} onChange={set("visit_date")} />)}
        </div>
        <button disabled={busy}>{busy ? "Registering…" : "Register visit"}</button>
      </form>
      {msg && <div className={`notice ${msg.ok ? "ok" : "err"}`}><p>{msg.text}</p>{msg.reference && <p><b>Your private reference:</b> <code>{msg.reference}</code></p>}{msg.reference && <p className="muted">Save this reference to check your request status. Do not share it publicly.</p>}</div>}
      <div className="status-check">
        <h2>Check a registration</h2>
        <p className="muted">Use the private reference from your confirmation to view your saved registration details.</p>
        <form onSubmit={checkStatus}>
          <label>Registration reference<input value={reference} onChange={e=>setReference(e.target.value)} placeholder="Paste your private reference" /></label>
          <button type="submit" className="secondary-button">View registration</button>
        </form>
        {statusError && <div className="notice err">{statusError}</div>}
        {statusResult && <div className="notice ok"><b>Registration saved</b><p>{statusResult.vehicle_number} · Visit date: {statusResult.visit_date}</p><p className="muted">Security will compare this vehicle number with the number plate detected at the gate. Registration alone does not guarantee entry; the plate and visit date must match.</p></div>}
      </div>
    </div>
  );
}
