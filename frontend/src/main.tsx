import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import "./styles.css";

const api = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const tenors = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"];
type CurvePoint = { tenor: string; value: number | null };
type Point = { date: string; spread?: number; volatility?: number; correlation?: number };
type Issue = { id: number; issue_type: string; severity: string; details: string };
type State<T> = { data: T; loading: boolean; error: string | null };
const initial = <T,>(data: T): State<T> => ({ data, loading: true, error: null });

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${api}${path}`);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

function ChartState({ loading, error, children }: { loading: boolean; error: string | null; children: React.ReactNode }) {
  if (loading) return <p className="status">Loading chart...</p>;
  if (error) return <p className="error">{error}</p>;
  return <>{children}</>;
}

function App() {
  const [curve, setCurve] = useState<State<CurvePoint[][]>>(initial([]));
  const [spread, setSpread] = useState<State<Point[]>>(initial([]));
  const [volatility, setVolatility] = useState<State<Point[]>>(initial([]));
  const [correlation, setCorrelation] = useState<State<Point[]>>(initial([]));
  const [issues, setIssues] = useState<State<Issue[]>>(initial([]));
  const [analyticsWindow, setAnalyticsWindow] = useState(60);
  const [symbol, setSymbol] = useState("SPY");
  const [curveIndex, setCurveIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [prices, setPrices] = useState<Record<string, { value: number; direction: string }>>({});

  const end = useMemo(() => new Date(), []);
  const start = useMemo(() => new Date(end.getTime() - 60 * 86400000), [end]);
  const range = useMemo(() => {
    const dates: string[] = [];
    for (let current = new Date(start); current <= end; current.setDate(current.getDate() + 1)) {
      dates.push(current.toISOString().slice(0, 10));
    }
    return dates;
  }, [start, end]);

  useEffect(() => {
    Promise.all(range.map((day) => get<CurvePoint[]>(`/yields/curve?date=${day}`)))
      .then((data) => setCurve({ data, loading: false, error: null }))
      .catch((error: Error) => setCurve({ data: [], loading: false, error: error.message }));
    get<Point[]>(`/spreads/2s10s?start=${range[0]}&end=${range.at(-1)}`)
      .then((data) => setSpread({ data, loading: false, error: null }))
      .catch((error: Error) => setSpread({ data: [], loading: false, error: error.message }));
    get<Issue[]>("/data-quality/issues")
      .then((data) => setIssues({ data, loading: false, error: null }))
      .catch((error: Error) => setIssues({ data: [], loading: false, error: error.message }));
  }, [range]);

  useEffect(() => {
    setVolatility(initial([]));
    setCorrelation(initial([]));
    get<Point[]>(`/analytics/volatility?symbol=${symbol}&window=${analyticsWindow}`)
      .then((data) => setVolatility({ data, loading: false, error: null }))
      .catch((error: Error) => setVolatility({ data: [], loading: false, error: error.message }));
    get<Point[]>(`/analytics/correlation?symbol=${symbol}&window=${analyticsWindow}`)
      .then((data) => setCorrelation({ data, loading: false, error: null }))
      .catch((error: Error) => setCorrelation({ data: [], loading: false, error: error.message }));
  }, [symbol, analyticsWindow]);

  useEffect(() => {
    if (!playing) return;
    const timer = globalThis.setInterval(() => setCurveIndex((index) => (index + 1) % Math.max(curve.data.length, 1)), 800);
    return () => globalThis.clearInterval(timer);
  }, [playing, curve.data.length]);

  useEffect(() => {
    const socket = new WebSocket(api.replace(/^http/, "ws") + "/ws/prices");
    socket.onmessage = (event) => {
      const update = JSON.parse(event.data) as { symbol: string; price: number };
      setPrices((current) => {
        const previous = current[update.symbol]?.value;
        return { ...current, [update.symbol]: { value: update.price, direction: previous === undefined ? "" : update.price >= previous ? "up" : "down" } };
      });
    };
    return () => socket.close();
  }, []);

  const displayedCurve = (curve.data[curveIndex] ?? []).sort((a, b) => tenors.indexOf(a.tenor) - tenors.indexOf(b.tenor));
  return <main>
    <header><div><h1>Fixed Income & Equity Market Monitor</h1><p>US Treasury curve and ETF risk monitor</p></div></header>
    <section className="tiles" aria-label="Live prices">{["SPY", "QQQ", "VTI", "AGG", "TLT"].map((ticker) => <article key={ticker}><h2>{ticker}</h2><strong className={`price ${prices[ticker]?.direction}`}>{prices[ticker]?.value?.toFixed(2) ?? "Waiting"}</strong></article>)}</section>
    <section className="chart"><div className="chart-title"><h2>Yield curve</h2><button onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</button></div>
      <input aria-label="Yield curve date" type="range" min="0" max={Math.max(curve.data.length - 1, 0)} value={curveIndex} onChange={(event) => setCurveIndex(Number(event.target.value))} />
      <p>{range[curveIndex] ?? "No observation date"}</p><ChartState {...curve}><ResponsiveContainer width="100%" height={300}><LineChart data={displayedCurve}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="tenor" /><YAxis /><Tooltip /><Line dataKey="value" stroke="#2563eb" dot /></LineChart></ResponsiveContainer></ChartState></section>
    <section className="chart"><h2>2s10s Treasury spread</h2><ChartState {...spread}><ResponsiveContainer width="100%" height={300}><LineChart data={spread.data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" /><YAxis /><Tooltip /><ReferenceLine y={0} stroke="#475569" /><Line dataKey="spread" stroke="#7c3aed" dot={false} /></LineChart></ResponsiveContainer></ChartState></section>
    <section className="controls"><label>Symbol <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>{["SPY", "QQQ", "VTI", "AGG", "TLT"].map((ticker) => <option key={ticker}>{ticker}</option>)}</select></label><label>Window <select value={analyticsWindow} onChange={(event) => setAnalyticsWindow(Number(event.target.value))}>{[20, 60, 120].map((value) => <option key={value}>{value}</option>)}</select> days</label></section>
    <section className="chart"><h2>Rolling annualized volatility</h2><ChartState {...volatility}><ResponsiveContainer width="100%" height={300}><LineChart data={volatility.data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" /><YAxis /><Tooltip /><Line dataKey="volatility" stroke="#dc2626" dot={false} /></LineChart></ResponsiveContainer></ChartState></section>
    <section className="chart"><h2>Equity / 10Y yield-change correlation</h2><ChartState {...correlation}><ResponsiveContainer width="100%" height={300}><LineChart data={correlation.data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" /><YAxis domain={[-1, 1]} /><Tooltip /><ReferenceLine y={0} stroke="#475569" /><Line dataKey="correlation" stroke="#059669" dot={false} /></LineChart></ResponsiveContainer></ChartState></section>
    <section><h2>Data quality</h2><ChartState {...issues}>{issues.data.length ? <ul>{issues.data.map((issue) => <li key={issue.id}><strong>{issue.severity}</strong>: {issue.issue_type} — {issue.details}</li>)}</ul> : <p>No open issues.</p>}</ChartState></section>
  </main>;
}
createRoot(document.getElementById("root")!).render(<App />);
