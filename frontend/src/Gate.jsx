import { useEffect, useRef, useState } from "react";
import { getJSON, scan, saveManualDecision } from "./api.js";

const SAMPLE_MS = 500;        // ~2 frames/second (slower if OCR takes longer: one request at a time)
const COOLDOWN_MS = 10000;    // same plate won't re-trigger for 10 s
const AUTO_HIDE_MS = 6000;    // live modes: result screen hides itself
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function grabFrame(video) {
  const scale = Math.min(1, 1280 / video.videoWidth);
  const c = document.createElement("canvas");
  c.width = Math.round(video.videoWidth * scale);
  c.height = Math.round(video.videoHeight * scale);
  c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
  return new Promise((res) => c.toBlob(res, "image/jpeg", 0.85));
}

function ResultScreen({ r, onClose, onDecision }) {
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [decisionMessage, setDecisionMessage] = useState("");
  const [manualPlate, setManualPlate] = useState(r.plate || "");
  useEffect(() => setManualPlate(r.plate || ""), [r.plate]);
  async function decide(granted) {
    setDecisionBusy(true); setDecisionMessage("");
    try { const d = await saveManualDecision({ plate: manualPlate, permission_granted: granted, confidence: r.confidence }); setDecisionMessage(d.message); onDecision({ ...r, plate: manualPlate, status: d.status, vehicle_status: d.vehicle_status, manual_permission_required: false, manual_decision: granted ? "GRANTED" : "DENIED" }); }
    catch (e) { setDecisionMessage(e.message); } finally { setDecisionBusy(false); }
  }
  const title = {
    GRANTED: "ACCESS GRANTED",
    UNREGISTERED: "UNREGISTERED",
    CHECK_MANUALLY: "CHECK MANUALLY",
    NO_PLATE: "NO PLATE READ",
  }[r.status];
  return (
    <div className={`result ${r.status}`} onClick={() => { if (!r.manual_permission_required) onClose(); }}>
      <div className="result-title">{title}</div>
      {r.plate && <div className="result-plate">{r.plate}</div>}
      {r.crop_b64 && <img className="result-crop" src={`data:image/jpeg;base64,${r.crop_b64}`} alt="plate crop" />}
      {r.status === "GRANTED" && r.vehicle_type === "VISITOR" && r.visitor && (
        <div className="result-who">
          {r.visitor.name}
          <span>{r.visitor.num_visitors} visitor{r.visitor.num_visitors > 1 ? "s" : ""}</span>
        </div>
      )}
      {r.status === "UNREGISTERED" && !r.manual_decision && <div className="result-sub">No matching visitor registration or staff/college vehicle record. Security must verify and decide.</div>}
      {r.status === "GRANTED" && r.vehicle_type && r.vehicle_type !== "VISITOR" && <div className="result-sub">{r.vehicle_type === "COLLEGE" ? "College vehicle" : r.vehicle_type === "STAFF" ? "Staff vehicle" : "Vehicle"}: {r.fleet_vehicle?.owner_name || r.plate}{r.fleet_vehicle?.department ? ` · ${r.fleet_vehicle.department}` : ""}. {r.manual_decision === "GRANTED" ? "Guard permission recorded." : "Entry recorded in the appropriate vehicle log."}</div>}
      {r.status === "GRANTED" && r.manual_decision === "GRANTED" && <div className="result-sub">Guard granted permission. Vehicle status: <b>{r.vehicle_status || "updated"}</b>. The passage was recorded in the appropriate vehicle log.</div>}
      {r.status === "GRANTED" && r.vehicle_status && <div className="result-sub">Current vehicle status: <b>{r.vehicle_status}</b></div>}
      {r.status === "UNREGISTERED" && r.manual_decision === "DENIED" && <div className="result-sub">Guard denied permission. No vehicle-log entry was created.</div>}
      {r.manual_permission_required && <div className="manual-decision" onClick={e=>e.stopPropagation()}><b>Was permission granted by security?</b><p>Verify the vehicle and driver before deciding. Granted vehicles are added to the appropriate log and their campus status is updated.</p>{(!r.plate || r.status === "CHECK_MANUALLY") && <label className="manual-plate-label">{r.plate ? "Confirm or correct the detected number plate" : "Enter the number plate manually"}<input value={manualPlate} onChange={e=>setManualPlate(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))} placeholder="e.g. TN37AB1234" minLength={6} maxLength={20} required /></label>}<div className="manual-buttons"><button disabled={decisionBusy || manualPlate.replace(/[^A-Z0-9]/gi, "").length < 6} onClick={()=>decide(true)}>Yes — grant entry</button><button className="deny-button" disabled={decisionBusy || manualPlate.replace(/[^A-Z0-9]/gi, "").length < 6} onClick={()=>decide(false)}>No — deny entry</button></div>{decisionMessage && <p className="decision-message">{decisionMessage}</p>}</div>}
      {r.status === "CHECK_MANUALLY" && (
        <div className="result-sub">
          Close to <b className="mono">{r.near_match.vehicle_number}</b> ({r.near_match.name},{" "}
          {r.near_match.num_visitors} visitor{r.near_match.num_visitors > 1 ? "s" : ""}). Compare the plate by eye.
        </div>
      )}
      {r.status === "NO_PLATE" && <div className="result-sub">Plate could not be read. Enter the plate manually below, verify permission, and record the decision.</div>}
      <div className="result-foot">
        {r.plate ? `OCR confidence ${r.confidence} · ` : ""}{r.manual_permission_required ? "Make a security decision before closing" : "tap anywhere to dismiss"}
      </div>
    </div>
  );
}

export default function Gate() {
  const [mode, setMode] = useState("upload");
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);
  const [videoUrl, setVideoUrl] = useState(null);

  const videoRef = useRef(null);
  const loopId = useRef(0);
  const cooldown = useRef(new Map()); // plate -> {t, conf}
  const hideTimer = useRef(null);
  const shownPlate = useRef(null);

  const refreshLog = () => getJSON("/scans?limit=8").then(setLog).catch(() => {});
  useEffect(() => { refreshLog(); }, []);

  function show(r, autoHide) {
    shownPlate.current = r.plate;
    setResult(r);
    clearTimeout(hideTimer.current);
    if (autoHide) hideTimer.current = setTimeout(() => { setResult(null); shownPlate.current = null; }, AUTO_HIDE_MS);
  }
  const close = () => { clearTimeout(hideTimer.current); setResult(null); shownPlate.current = null; };

  // Live (webcam/video) result handling: cooldown + keep the most confident read.
  function handleLive(r) {
    if (!r.plate) return;
    const now = Date.now();
    const prev = cooldown.current.get(r.plate);
    if (prev && now - prev.t < COOLDOWN_MS) {
      if (r.confidence > prev.conf) {
        cooldown.current.set(r.plate, { t: prev.t, conf: r.confidence });
        if (shownPlate.current === r.plate) setResult(r); // better crop, same screen, timer unchanged
      }
      return;
    }
    cooldown.current.set(r.plate, { t: now, conf: r.confidence });
    show(r, true);
    refreshLog();
  }

  async function runLoop() {
    const me = ++loopId.current;
    while (loopId.current === me) {
      const v = videoRef.current;
      if (!v || v.readyState < 2 || v.paused || v.ended || !v.videoWidth) {
        if (v?.ended) setStatus("Video ended. Press play to run again.");
        await sleep(200);
        continue;
      }
      const t0 = performance.now();
      try {
        const r = await scan(await grabFrame(v));
        if (loopId.current !== me) break;
        setStatus(`Scanning… last frame ${Math.round(performance.now() - t0)} ms · ${r.plate ? `read ${r.plate} (${r.confidence})` : "no plate in frame"}`);
        handleLive(r);
      } catch (e) {
        setStatus(`Backend error: ${e.message}`);
        await sleep(1000);
      }
      const wait = SAMPLE_MS - (performance.now() - t0);
      if (wait > 0) await sleep(wait);
    }
  }
  const stopLoop = () => { loopId.current++; };

  // Webcam lifecycle
  useEffect(() => {
    if (mode !== "webcam") return;
    let stream;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "environment" },
          audio: false,
        });
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setStatus("Camera on. Point it at a number plate.");
        runLoop();
      } catch (e) {
        setStatus(`Camera unavailable: ${e.message}. Webcam needs http://localhost or https.`);
      }
    })();
    return () => { stopLoop(); stream?.getTracks().forEach((t) => t.stop()); };
  }, [mode]);

  // Video-file lifecycle
  useEffect(() => {
    if (mode !== "video" || !videoUrl) return;
    setStatus("Playing video…");
    runLoop();
    return () => stopLoop();
  }, [mode, videoUrl]);

  useEffect(() => () => { stopLoop(); clearTimeout(hideTimer.current); }, []);

  function switchMode(m) {
    close();
    setStatus("");
    cooldown.current.clear();
    if (videoUrl) { URL.revokeObjectURL(videoUrl); setVideoUrl(null); }
    setMode(m);
  }

  async function onUpload(e) {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    setStatus("Reading plate…");
    const t0 = performance.now();
    try {
      const r = await scan(f);
      setStatus(`Done in ${Math.round(performance.now() - t0)} ms`);
      show(r, false);
      refreshLog();
    } catch (err) {
      setStatus(`Backend error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  function onVideoFile(e) {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    cooldown.current.clear();
    setVideoUrl(URL.createObjectURL(f));
  }

  return (
    <div className="gate">
      <div className="tabs">
        {[["upload", "Upload image"], ["webcam", "Webcam"], ["video", "Video file"]].map(([m, label]) => (
          <button key={m} className={mode === m ? "on" : ""} onClick={() => switchMode(m)}>{label}</button>
        ))}
      </div>

      <div className="card stage">
        {mode === "upload" && (
          <label className="drop">
            <input type="file" accept="image/*" onChange={onUpload} disabled={busy} hidden />
            <b>{busy ? "Reading plate…" : "Choose a photo of the vehicle"}</b>
            <span className="muted">JPG or PNG, plate clearly visible</span>
          </label>
        )}
        {mode === "webcam" && <video key="cam" ref={videoRef} muted playsInline className="feed" />}
        {mode === "video" && (
          <>
            {!videoUrl && (
              <label className="drop">
                <input type="file" accept="video/*" onChange={onVideoFile} hidden />
                <b>Choose a pre-recorded video</b>
                <span className="muted">Frames are sampled about twice a second</span>
              </label>
            )}
            {videoUrl && (
              <>
                <video key={videoUrl} ref={videoRef} src={videoUrl} muted playsInline controls autoPlay className="feed" />
                <label className="link">
                  <input type="file" accept="video/*" onChange={onVideoFile} hidden />
                  Choose another video
                </label>
              </>
            )}
          </>
        )}
        {status && <p className="muted status">{status}</p>}
      </div>

      <div className="card">
        <h2>Recent scans</h2>
        <ScanTable rows={log} />
      </div>

      {result && <ResultScreen r={result} onClose={close} onDecision={(updated)=>{setResult(updated);refreshLog();}} />}
    </div>
  );
}

export function ScanTable({ rows }) {
  if (!rows.length) return <p className="muted">No scans yet.</p>;
  return (
    <table>
      <thead><tr><th>Time (IST)</th><th>Plate</th><th>Result</th><th>Vehicle status</th><th>Visitor</th><th>Conf.</th></tr></thead>
      <tbody>
        {rows.map((s, i) => (
          <tr key={i}>
            <td>{s.scanned_at.slice(11)}</td>
            <td className="mono">{s.plate}</td>
            <td><span className={`pill ${s.status}`}>{s.status.replace("_", " ")}</span></td>
            <td>{s.vehicle_status || "—"}</td>
            <td>{s.visitor_name || "—"}</td>
            <td>{s.confidence}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
