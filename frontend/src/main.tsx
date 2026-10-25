import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import "./styles.css";

const api = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
type Point = { date: string; spread?: number; volatility?: number; correlation?: number };
type Issue = { id: number; issue_type: string; severity: string; details: string; observed_at: string };

function App() {
  const [spread, setSpread] = useState<Point[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [window, setWindow] = useState(60);
  const [status, setStatus] = useState("Loading market data...");
  const [prices, setPrices] = useState<Record<string, number>>({});

  useEffect(() => {
    const end = new Date().toISOString().slice(0, 10);
    const start = new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10);
    Promise.all([
      fetch(`${api}/spreads/2s10s?start=${start}&end=${end}`).then((r) => r.json()),
      fetch(`${api}/data-quality/issues`).then((r) => r.json()),
    ]).then(([spreads, quality]) => {
      setSpread(spreads);
      setIssues(quality);
      setStatus("Connected");
    }).catch(() => setStatus("API unavailable - start the backend to load data."));
  }, []);
  useEffect(() => {
    const socket = new WebSocket(api.replace(/^http/, "ws") + "/ws/prices");
    socket.onmessage = (event) => {
      const update = JSON.parse(event.data);
      setPrices((current) => ({ ...current, [update.symbol]: update.price }));
    };
    return () => socket.close();
  }, []);

  return <main>
    <header><h1>Fixed Income & Equity Market Monitor</h1><p aria-live="polite">{status}</p></header>
    <section className="controls"><label>Analytics window <select value={window} onChange={(e) => setWindow(Number(e.target.value))}>{[20, 60, 120].map((value) => <option key={value}>{value}</option>)}</select> trading days</label></section>
    <section className="tiles" aria-label="Live prices">{["SPY", "QQQ", "VTI", "AGG", "TLT"].map((symbol) => <article key={symbol}><h2>{symbol}</h2><strong className={prices[symbol] ? "price flash" : "price"}>{prices[symbol]?.toFixed(2) ?? "Waiting for stream"}</strong></article>)}</section>
    <section className="chart"><h2>2s10s Treasury spread</h2><ResponsiveContainer width="100%" height={300}><LineChart data={spread}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" /><YAxis /><Tooltip /><Line type="monotone" dataKey="spread" stroke="#2563eb" dot={false} /></LineChart></ResponsiveContainer></section>
    <section className="chart"><h2>Analytics ({window}-day)</h2><p>Rolling volatility and equity/10Y-yield correlation become available after ingestion completes.</p></section>
    <section><h2>Data quality</h2>{issues.length ? <ul>{issues.map((issue) => <li key={issue.id}><strong>{issue.severity}</strong>: {issue.issue_type} - {issue.details}</li>)}</ul> : <p>No open data-quality issues.</p>}</section>
  </main>;
}
createRoot(document.getElementById("root")!).render(<App />);
