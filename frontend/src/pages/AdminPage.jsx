// 관리자 : 축제별 예매 목록 (요일·상태 필터)
import { useEffect, useState } from "react";
import { api } from "../api/endpoints";

const STATUSES = ["PENDING", "CONFIRMED", "CANCELED", "EXPIRED"];
const TYPE_LABEL = { SAT: "토요일권", SUN: "일요일권", BOTH: "양일권" };

export default function AdminPage({ festivalId, version, notify, isAdmin }) {
  const [day, setDay] = useState("");
  const [statuses, setStatuses] = useState([]);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  async function load() {
    try {
      setError(null);
      setData(await api.festivalReservations(festivalId, { day: day || undefined, statuses }));
    } catch (e) {
      setData(null);
      setError(`${e.status} ${e.code || ""} · ${e.message}`);
    }
  }
  useEffect(() => {
    load();
  }, [version, festivalId, day, statuses.join(",")]);

  const toggle = (s) => setStatuses((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  return (
    <div className="page">
      <div className="page-head">
        <h1>축제 #{festivalId} 예매 목록</h1>
        <span className={`pill ${isAdmin ? "CONFIRMED" : "CANCELED"}`}>{isAdmin ? "관리자" : "일반 회원 (403 예상)"}</span>
      </div>

      <div className="card filters">
        <div>
          <label className="field-label">회차</label>
          <div className="seg small">
            {[["", "전체"], ["SAT", "토요일 (SAT+BOTH)"], ["SUN", "일요일 (SUN+BOTH)"]].map(([v, l]) => (
              <button key={v} className={day === v ? "on" : ""} onClick={() => setDay(v)}>{l}</button>
            ))}
          </div>
        </div>
        <div>
          <label className="field-label">상태 (여러 개 선택)</label>
          <div className="seg small">
            {STATUSES.map((s) => (
              <button key={s} className={statuses.includes(s) ? "on" : ""} onClick={() => toggle(s)}>{s}</button>
            ))}
          </div>
        </div>
      </div>

      {error && <div className="card error-card">{error}</div>}
      {data && (
        <div className="card table-card">
          <div className="muted small">전체 {data.total}건</div>
          <table>
            <thead>
              <tr><th>#</th><th>종류</th><th>수량</th><th>금액</th><th>상태</th></tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.reservation_id}>
                  <td>{r.reservation_id}</td>
                  <td>{TYPE_LABEL[r.ticket_type]}</td>
                  <td>{r.quantity}</td>
                  <td>{r.final_price.toLocaleString()}원</td>
                  <td><span className={`pill ${r.status}`}>{r.status}</span></td>
                </tr>
              ))}
              {data.items.length === 0 && <tr><td colSpan={5} className="muted">조건에 맞는 예매가 없어요.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
