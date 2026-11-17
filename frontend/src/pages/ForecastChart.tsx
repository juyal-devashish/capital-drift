// Reserve balance: the years already seen (one line) and the forecast (median line with the
// 10th-90th percentile band), drawn as inline SVG. Below zero is shaded: a modelled shortfall.
import type { ForecastData } from "../types";
import { usdShort } from "../format";

const W = 720;
const H = 240;
const PAD = { l: 56, r: 12, t: 12, b: 28 };

export function ForecastChart({ f }: { f: ForecastData }) {
  const points = [
    ...f.history.map((h) => ({ year: h.year, lo: h.balance, mid: h.balance, hi: h.balance })),
    ...f.years.map((y) => ({ year: y.year, lo: y.p10, mid: y.p50, hi: y.p90 })),
  ];
  const years = points.map((p) => p.year);
  const vals = points.flatMap((p) => [p.lo, p.hi]).concat(0);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const x = (year: number) => PAD.l + ((year - years[0]) / Math.max(years[years.length - 1] - years[0], 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + ((max - v) / span) * (H - PAD.t - PAD.b);
  const line = (pts: { year: number; v: number }[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.year).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");

  const fc = points.filter((p) => p.year >= f.as_of);
  const band = `${line(fc.map((p) => ({ year: p.year, v: p.hi })))} ${fc
    .slice()
    .reverse()
    .map((p) => `L${x(p.year).toFixed(1)},${y(p.lo).toFixed(1)}`)
    .join(" ")} Z`;
  // Top, zero and bottom: zero is the line that matters.
  const ticks = [...new Set([max, 0, min].map((v) => Math.round(v)))];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="forecast-chart" role="img" aria-label={`Reserve balance, ${years[0]} to ${years[years.length - 1]}`}>
      {min < 0 && <rect x={PAD.l} y={y(0)} width={W - PAD.l - PAD.r} height={H - PAD.b - y(0)} className="fc-short" />}
      {ticks.map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="fc-grid" />
          <text x={PAD.l - 6} y={y(v) + 4} textAnchor="end" className="fc-label">
            {v < 0 ? `-${usdShort(-v)}` : usdShort(v)}
          </text>
        </g>
      ))}
      <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} className="fc-zero" />
      <line x1={x(f.as_of)} x2={x(f.as_of)} y1={PAD.t} y2={H - PAD.b} className="fc-today" />
      <path d={band} className="fc-band" />
      <path d={line(points.filter((p) => p.year <= f.as_of).map((p) => ({ year: p.year, v: p.mid })))} className="fc-history" />
      <path d={line(fc.map((p) => ({ year: p.year, v: p.mid })))} className="fc-median" />
      {years
        .filter((yr) => yr % 2 === 0)
        .map((yr) => (
          <text key={yr} x={x(yr)} y={H - 8} textAnchor="middle" className="fc-label">
            {yr}
          </text>
        ))}
    </svg>
  );
}
