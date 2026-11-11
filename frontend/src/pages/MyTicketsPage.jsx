// 내 티켓 : 예매가 확정되면 회차 × 수량만큼 발급된 티켓
import { useEffect, useState } from "react";
import { api } from "../api/endpoints";

const fmt = (s) => new Date(s).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" });

export default function MyTicketsPage({ version, notify }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.myTickets().then(setData).catch((e) => notify("bad", `${e.status} ${e.message}`));
  }, [version]);

  if (!data) return <div className="page muted">불러오는 중…</div>;
  const items = data.items || [];

  return (
    <div className="page">
      <div className="page-head">
        <h1>내 티켓</h1>
        <span className="muted">{data.total}장</span>
      </div>
      {items.length === 0 && <div className="card muted">발급된 티켓이 없어요. 예매를 결제(입금 완료)하면 티켓이 발급돼요.</div>}
      <div className="ticket-grid">
        {items.map((t) => (
          <article key={t.ticket_id} className={`ticket ${t.status}`}>
            <div className="ticket-l">
              <div className="eyebrow">TICKET #{t.ticket_id} · 예매 #{t.reservation_id}</div>
              <h3>{t.performance_title}</h3>
              <p className="muted">{fmt(t.performance_start_at)}</p>
            </div>
            <div className="ticket-r">
              <span className={`pill ${t.status}`}>{t.status}</span>
              <span className="muted">{t.price.toLocaleString()}원</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
