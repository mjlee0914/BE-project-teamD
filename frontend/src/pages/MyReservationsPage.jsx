// 내 예매 : 목록 + 입금 완료(시뮬레이션) / 만료 / 취소 / 동시 취소(락 시연)
import { useEffect, useRef, useState } from "react";
import { api } from "../api/endpoints";

const TYPE_LABEL = { SAT: "토요일권", SUN: "일요일권", BOTH: "양일권" };
const STATUS_LABEL = { PENDING: "입금 대기", CONFIRMED: "예매 확정", CANCELED: "취소됨", EXPIRED: "기한 만료" };
const won = (n) => `${n.toLocaleString()}원`;

function useNow() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function left(ms) {
  if (ms <= 0) return "기한 지남";
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${m}분 ${String(s).padStart(2, "0")}초 남음`;
}

export default function MyReservationsPage({ version, notify, onChanged, adminId }) {
  const [list, setList] = useState(null);
  const now = useNow();
  const first = useRef(true);

  async function load(trace = true) {
    try {
      setList(await api.myReservations({ trace }));
    } catch (e) {
      notify("bad", e.message);
    }
  }
  useEffect(() => {
    load(first.current);
    first.current = false;
  }, [version]);

  async function act(fn, okMsg) {
    try {
      await fn();
      notify("good", okMsg);
    } catch (e) {
      notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);
    }
    onChanged();
  }

  // 같은 예매에 "본인 취소"와 "관리자 취소"를 동시에 보낸다 → 하나는 성공, 하나는 잠금 대기 후 409
  async function doubleCancel(id) {
    const results = await Promise.allSettled([
      api.cancelReservation(id),
      api.cancelReservation(id, { actor: adminId }),
    ]);
    const ok = results.filter((r) => r.status === "fulfilled").length;
    const fail = results.filter((r) => r.status === "rejected").map((r) => r.reason.code);
    notify(ok === 1 ? "good" : "bad", `동시 취소 2건 → 성공 ${ok}건 / 실패 ${fail.length}건 ${fail.join(", ")}`);
    onChanged();
  }

  if (!list) return <div className="page muted">불러오는 중…</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1>내 예매</h1>
        <span className="muted">{list.length}건</span>
      </div>
      {list.length === 0 && <div className="card muted">아직 예매가 없어요. "예매하기"에서 예매해 보세요.</div>}

      <div className="res-list">
        {[...list].reverse().map((r) => {
          const active = r.status === "PENDING" || r.status === "CONFIRMED";
          const due = r.deposit_due_at ? new Date(r.deposit_due_at).getTime() - now : null;
          const exp = new Date(r.expires_at).getTime() - now;
          return (
            <article key={r.reservation_id} className={`res-card ${r.status}`}>
              <div className="res-top">
                <div>
                  <span className="res-id">#{r.reservation_id}</span>
                  <b>{TYPE_LABEL[r.ticket_type]}</b> × {r.quantity}장
                  {r.discount_type !== "NONE" && <span className="tag">{r.discount_type}</span>}
                </div>
                <span className={`pill ${r.status}`}>{STATUS_LABEL[r.status]}</span>
              </div>
              <div className="res-mid">
                <span className="price">{won(r.final_price)}</span>
                {r.discount_amount > 0 && <span className="muted strike">{won(r.total_price)}</span>}
                {r.status === "PENDING" && (
                  <span className="timer">
                    {due !== null && <>입금 마감 {left(due)} · </>}예매 만료 {left(exp)}
                  </span>
                )}
              </div>
              {active && (
                <div className="res-actions">
                  {r.status === "PENDING" && (
                    <>
                      <button className="primary" onClick={() => act(() => api.confirmReservation(r.reservation_id), `#${r.reservation_id} 입금 완료 → 예매 확정 + 티켓 발급`)}>
                        입금 완료 (시뮬레이션)
                      </button>
                      <button className="ghost" onClick={() => act(() => api.expireReservation(r.reservation_id), `#${r.reservation_id} 입금 기한 만료 처리`)}>
                        입금 기한 지나게 하기
                      </button>
                    </>
                  )}
                  <button className="danger" onClick={() => act(() => api.cancelReservation(r.reservation_id), `#${r.reservation_id} 취소 완료`)}>
                    취소
                  </button>
                  <button className="ghost lock" onClick={() => doubleCancel(r.reservation_id)} title="본인 취소와 관리자 취소를 동시에 보냅니다">
                    🔒 동시에 2번 취소
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
