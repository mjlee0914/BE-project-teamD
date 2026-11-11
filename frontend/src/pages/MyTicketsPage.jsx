// 티켓 : 목록(상태 필터·페이지) + 상세 + 단일 취소
// - 일반 회원 : 내 티켓 / 관리자 : 전체 티켓 검색 (회차 id로 필터 가능)
import { useEffect, useRef, useState } from "react";
import { api } from "../api/endpoints";

const STATUSES = ["PENDING", "ISSUED", "USED", "CANCELED", "EXPIRED"];
const fmt = (s) => (s ? new Date(s).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" }) : "-");
const SIZE = 10;

export default function MyTicketsPage({ version, notify, isAdmin }) {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [perfId, setPerfId] = useState("");
  const [data, setData] = useState(null);
  const [detail, setDetail] = useState(null);
  const detailRef = useRef(null);
  // 상세를 열면 목록 위의 상세 카드가 보이도록 올려준다
  useEffect(() => {
    if (detail) detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [detail?.ticket_id]);

  async function load() {
    try {
      setData(await api.tickets({ status: status || undefined, page, size: SIZE, performanceId: isAdmin && perfId ? perfId : undefined }));
    } catch (e) {
      notify("bad", `${e.status} ${e.message}`);
    }
  }
  useEffect(() => {
    load();
  }, [version, status, page, perfId]);

  async function open(id) {
    try {
      setDetail(await api.ticket(id));
    } catch (e) {
      notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);
    }
  }

  async function cancel(id) {
    if (!window.confirm(`티켓 #${id}을 취소할까요? 양일권은 짝이 되는 티켓도 함께 취소돼요.`)) return;
    try {
      const t = await api.cancelTicket(id);
      setDetail(t);
      notify("good", `티켓 #${id} 취소 완료`);
      load();
    } catch (e) {
      notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);
    }
  }

  const items = data?.items || [];
  const pages = data ? Math.max(1, Math.ceil(data.total / SIZE)) : 1;

  return (
    <div className="page">
      <div className="page-head">
        <h1>{isAdmin ? "티켓 검색 (관리자)" : "내 티켓"}</h1>
        <span className="muted">{data ? `${data.total}장` : ""}</span>
      </div>

      <div className="card filters">
        <div>
          <label className="field-label">상태</label>
          <div className="seg small">
            {[["", "전체"], ...STATUSES.map((s) => [s, s])].map(([v, l]) => (
              <button key={v} className={status === v ? "on" : ""} onClick={() => { setStatus(v); setPage(1); }}>{l}</button>
            ))}
          </div>
        </div>
        {isAdmin && (
          <div className="form">
            <label className="field-label" htmlFor="t-perf">회차 ID</label>
            <input id="t-perf" type="number" min="1" value={perfId} onChange={(e) => { setPerfId(e.target.value); setPage(1); }} placeholder="전체" />
          </div>
        )}
      </div>

      {detail && (
        <section className="card form detail-panel" ref={detailRef}>
          <div className="page-head">
            <h2>티켓 #{detail.ticket_id} 상세</h2>
            <button className="ghost small" onClick={() => setDetail(null)}>닫기</button>
          </div>
          <div className="info">
            <div><span>공연</span><b>{detail.performance_title}</b></div>
            <div><span>상태</span><b><span className={`pill ${detail.status}`}>{detail.status}</span></b></div>
            <div><span>입장 코드</span><b>{detail.ticket_code}</b></div>
            <div><span>가격</span><b>{detail.price.toLocaleString()}원</b></div>
            <div><span>공연 시작</span><b>{fmt(detail.performance_start_at)}</b></div>
            <div><span>공연 종료</span><b>{fmt(detail.performance_end_at)}</b></div>
            <div><span>취소 마감</span><b>{fmt(detail.cancel_deadline_at)}</b></div>
            <div><span>발급</span><b>{fmt(detail.issued_at)}</b></div>
            <div><span>취소</span><b>{fmt(detail.canceled_at)}</b></div>
            <div><span>입장</span><b>{fmt(detail.used_at)}</b></div>
          </div>
          {(detail.status === "ISSUED" || detail.status === "PENDING") && (
            <div className="res-actions">
              <button className="danger" onClick={() => cancel(detail.ticket_id)}>이 티켓 취소</button>
            </div>
          )}
        </section>
      )}

      {data && items.length === 0 && <div className="card muted">조건에 맞는 티켓이 없어요.</div>}
      <div className="ticket-grid">
        {items.map((t) => (
          <article key={t.ticket_id} className={`ticket ${t.status} ${detail?.ticket_id === t.ticket_id ? "selected" : ""}`} onClick={() => open(t.ticket_id)} style={{ cursor: "pointer" }}>
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

      {data && pages > 1 && (
        <div className="seg small">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>← 이전</button>
          <span className="muted">{page} / {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)}>다음 →</button>
        </div>
      )}

    </div>
  );
}
