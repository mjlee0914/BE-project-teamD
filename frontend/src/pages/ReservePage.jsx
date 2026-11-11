// 예매하기 : 축제 정보 + 회차(잔여 수량) + 예매 폼
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints";

const TYPES = [
  { value: "SAT", label: "토요일권" },
  { value: "SUN", label: "일요일권" },
  { value: "BOTH", label: "양일권" },
];
const DISCOUNTS = [
  { value: "NONE", label: "할인 없음", rate: 0 },
  { value: "DISABLED", label: "장애인 (60%)", rate: 60 },
  { value: "VETERAN", label: "국가유공자 (70%)", rate: 70 },
  { value: "SENIOR", label: "경로 (80%)", rate: 80 },
  { value: "KANT", label: "KANT (90%)", rate: 90 },
];

const KST = { timeZone: "Asia/Seoul" };
const fmtDate = (s) => new Date(s).toLocaleString("ko-KR", { ...KST, month: "long", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" });
const won = (n) => `${n.toLocaleString()}원`;

export default function ReservePage({ festivalId, version, notify, onReserved, onBack }) {
  const [festival, setFestival] = useState(null);
  const [perfs, setPerfs] = useState([]);
  const [type, setType] = useState("SAT");
  const [qty, setQty] = useState(1);
  const [discount, setDiscount] = useState("NONE");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState({}); // performance_id → {detail, availability}

  // 회차 상세 + 실시간 예매 가능 여부
  async function check(id) {
    try {
      const [detail, availability] = await Promise.all([api.performance(id), api.availability(id)]);
      setLive((cur) => ({ ...cur, [id]: { detail, availability } }));
    } catch (e) {
      notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);
    }
  }

  useEffect(() => {
    api.festival(festivalId).then(setFestival).catch(() => {});
    api.performances(festivalId).then((d) => setPerfs(d?.items || [])).catch(() => {});
  }, [version, festivalId]);

  const sat = perfs.find((p) => new Date(p.starts_at).toLocaleDateString("en-US", { ...KST, weekday: "short" }) === "Sat");
  const sun = perfs.find((p) => new Date(p.starts_at).toLocaleDateString("en-US", { ...KST, weekday: "short" }) === "Sun");

  const price = useMemo(() => {
    const unit = type === "SAT" ? sat?.price : type === "SUN" ? sun?.price : (sat?.price || 0) + (sun?.price || 0);
    if (!unit) return null;
    const total = unit * qty;
    const rate = DISCOUNTS.find((d) => d.value === discount).rate;
    const off = Math.floor((total * rate) / 100);
    return { unit, total, off, final: total - off };
  }, [type, qty, discount, sat, sun]);

  async function reserve() {
    setBusy(true);
    try {
      const r = await api.createReservation({ festival_id: festivalId, ticket_type: type, quantity: qty, discount_type: discount });
      notify("good", `예매 #${r.reservation_id} 생성 · ${won(r.final_price)} · 이제 결제해 주세요`);
      onReserved();
    } catch (e) {
      notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <button className="ghost small back" onClick={onBack}>← 축제 목록</button>
      {festival && (
        <section className="hero">
          <div className="eyebrow">FESTIVAL #{festival.festival_id} · {festival.status}</div>
          <h1>{festival.name}</h1>
          <p className="muted">{festival.venue} · {festival.starts_on} ~ {festival.ends_on}</p>
        </section>
      )}

      <section className="perf-grid">
        {[sat, sun].filter(Boolean).map((p) => {
          const pct = Math.round((p.remaining_count / p.capacity) * 100);
          return (
            <article key={p.performance_id} className="perf-card">
              <div className="perf-top">
                <h3>{p.title}</h3>
                <span className={`pill ${p.status}`}>{p.status}</span>
              </div>
              <p className="muted">{fmtDate(p.starts_at)}</p>
              <div className="remain">
                <div className="bar"><span style={{ width: `${pct}%` }} /></div>
                <div className="remain-text">
                  <b>{p.remaining_count}</b> / {p.capacity}석 남음
                </div>
              </div>
              <div className="perf-price">{won(p.price)}</div>
              <button className="ghost small" onClick={() => check(p.performance_id)}>회차 상세 · 잔여 확인</button>
              {live[p.performance_id] && (
                <p className="hint">
                  {live[p.performance_id].availability.is_bookable ? "지금 예매 가능" : "지금 예매 불가"} · 잔여 {live[p.performance_id].availability.remaining_count}석
                  {" · "}예매 {fmtDate(live[p.performance_id].detail.booking_open_at)} ~ {fmtDate(live[p.performance_id].detail.booking_close_at)}
                  {" · "}취소 마감 {fmtDate(live[p.performance_id].detail.cancel_deadline_at)}
                </p>
              )}
            </article>
          );
        })}
      </section>

      <section className="card form">
        <h2>예매하기</h2>
        <label className="field-label">티켓 종류</label>
        <div className="seg">
          {TYPES.map((t) => (
            <button key={t.value} className={type === t.value ? "on" : ""} onClick={() => setType(t.value)}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="row">
          <div>
            <label className="field-label">수량 (1인 하루 최대 2장)</label>
            <div className="seg small">
              {[1, 2].map((n) => (
                <button key={n} className={qty === n ? "on" : ""} onClick={() => setQty(n)}>{n}장</button>
              ))}
            </div>
          </div>
          <div className="grow">
            <label className="field-label">할인</label>
            <select value={discount} onChange={(e) => setDiscount(e.target.value)}>
              {DISCOUNTS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </div>
        </div>

        {price && (
          <div className="price-box">
            <div><span>1장 가격{type === "BOTH" ? " (토+일)" : ""}</span><span>{won(price.unit)}</span></div>
            <div><span>총 금액</span><span>{won(price.total)}</span></div>
            {price.off > 0 && <div className="off"><span>할인</span><span>- {won(price.off)}</span></div>}
            <div className="final"><span>결제 금액</span><span>{won(price.final)}</span></div>
          </div>
        )}

        <button className="primary big" disabled={busy} onClick={reserve}>
          {busy ? "처리 중…" : "예매하기"}
        </button>
        <p className="hint">가격은 화면에서 미리 보여줄 뿐이고, 실제 금액은 서버가 회차 가격으로 다시 계산해요.</p>
      </section>
    </div>
  );
}
