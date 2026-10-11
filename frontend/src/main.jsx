import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import Register from "./Register.jsx";
import Gate from "./Gate.jsx";
import Today from "./Today.jsx";
import Fleet from "./Fleet.jsx";
import OtherVehicleLogs from "./OtherVehicleLogs.jsx";
import { getToken, setToken, login, logout } from "./api.js";
import "./styles.css";

function GuardLogin() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault(); setError(""); setBusy(true);
    try { const d = await login(username.trim(), password); setToken(d.access_token); location.hash = "#/guard/dashboard"; }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="card narrow auth-card"><p className="eyebrow">AUTHORIZED PERSONNEL ONLY</p><h1>Security guard sign in</h1><p className="muted">Sign in to access gate operations and visitor records.</p><form onSubmit={submit}><label>Username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required /></label><button disabled={busy}>{busy ? "Signing in…" : "Sign in securely"}</button></form>{error && <div className="notice err">{error}</div>}<p className="muted">Guard accounts are created by the system administrator.</p></div>;
}

function GuardPortal({ page, navigate }) {
  const [valid, setValid] = useState(false);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    let active = true;
    fetch((import.meta.env.VITE_API || "http://localhost:8000") + "/auth/me", { headers: { Authorization: `Bearer ${getToken() || ""}` } })
      .then(r => { if (!r.ok) throw new Error("Login required"); return r.json(); })
      .then(() => { if (active) setValid(true); })
      .catch(() => { setToken(null); if (active) { setValid(false); location.hash = "#/guard/login"; } })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, []);
  if (checking) return <main><div className="card">Checking guard session…</div></main>;
  if (!valid) return null;
  const title = page === "scan" ? "Gate scanner" : page === "registrations" ? "Visitor registrations" : page === "fleet" ? "Staff & college vehicles" : page === "other-log" ? "Other vehicle log" : "Security dashboard";
  return <><nav className="guard-nav"><a className="brand" href="#/guard/dashboard">CAMPUS GATE <span>SECURITY</span></a><a href="#/guard/dashboard" className={page === "dashboard" ? "on" : ""}>Dashboard</a><a href="#/guard/scan" className={page === "scan" ? "on" : ""}>ANPR scanner</a><a href="#/guard/registrations" className={page === "registrations" ? "on" : ""}>Registrations & history</a><a href="#/guard/fleet" className={page === "fleet" ? "on" : ""}>Staff & college vehicles</a><a href="#/guard/other-log" className={page === "other-log" ? "on" : ""}>Other vehicle log</a><button className="nav-logout" onClick={async()=>{try{await logout()}catch{}setToken(null);location.hash="#/guard/login"}}>Log out</button></nav><main><div className="page-heading"><p className="eyebrow">SECURE GATE OPERATIONS</p><h1>{title}</h1><p className="muted">Authorized security workspace · India Standard Time</p></div>{page === "scan" ? <Gate/> : page === "fleet" ? <Fleet/> : page === "other-log" ? <OtherVehicleLogs/> : <Today dashboard={page === "dashboard"} />}</main></>;
}

function App() {
  const read = () => location.hash.replace(/^#\/?/, "") || "visitor/register";
  const [route, setRoute] = useState(read);
  useEffect(() => { const on = () => setRoute(read()); addEventListener("hashchange", on); return () => removeEventListener("hashchange", on); }, []);
  const parts = route.split("/");
  if (parts[0] === "guard") {
    if (parts[1] === "login") return <><nav><a className="brand" href="#/visitor/register">CAMPUS GATE</a><a href="#/visitor/register">Visitor registration</a></nav><main><GuardLogin/></main></>;
    return <GuardPortal page={parts[1] || "dashboard"} navigate={setRoute}/>;
  }
  return <><nav className="visitor-nav"><a className="brand" href="#/visitor/register">CAMPUS GATE</a><span className="nav-spacer"/><a className={route === "visitor/register" ? "on" : ""} href="#/visitor/register">Visitor registration</a><a href="#/guard/login">Security staff</a></nav><main><div className="page-heading"><p className="eyebrow">CAMPUS VISITOR SERVICES</p><h1>Plan your visit</h1><p className="muted">Submit your vehicle and visit details before arriving at the gate.</p></div><Register/></main></>;
}
createRoot(document.getElementById("root")).render(<App />);
