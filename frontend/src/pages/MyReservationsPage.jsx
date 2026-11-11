// 내 예매 : 목록 + 결제(토스 결제창) / 입금 완료 / 만료 / 취소 / 동시 취소(락 시연)
import { useEffect, useRef, useState } from "react";
import { api } from "../api/endpoints";
import { openPaymentWindow } from "../api/toss";

const TYPE_LABEL = { SAT: "토요일권", SUN: "일요일권", BOTH: "양일권" };
const STATUS_LABEL = { PENDING: "입금 대기", CONFIRMED: "예매 확정", CANCELED: "취소됨", EXPIRED: "기한 만료" };
const PAY_LABEL = {
  READY: "결제 준비됨 (결제창 미완료)",
  IN_PROGRESS: "승인 진행 중",
  WAITING_FOR_DEPOSIT: "가상계좌 발급됨 · 입금 대기",
  DONE: "결제 완료",
  ABORTED: "결제 실패",
  EXPIRED: "결제 만료",
  CANCELED: "결제 취소",
};
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

// 예매의 결제 시도 중 가장 최근 것
const latest = (list) => (list && list.length ? list[list.length - 1] : null);

export default function MyReservationsPage({ version, notify, onChanged, me }) {
  const [list, setList] = useState(null);
  const [pays, setPays] = useState({}); // reservation_id → 결제 목록
  const [paying, setPaying] = useState(null);
  const [detail, setDetail] = useState(null); // 예매 상세 (GET /v1/reservations/{id})
  const now = useNow();
  const first = useRef(true);

  async function load(trace = true) {
    try {
      const rows = await api.myReservations({ trace });
      setList(rows);
      // 입금 대기 예매의 결제 상태 (화면 표시용이라 코드 패널에는 보여주지 않음)
      const pending = rows.filter((r) => r.status === "PENDING");
      const entries = await Promise.all(
        pending.map((r) => api.payments(r.reservation_id).then((p) => [r.reservation_id, p]).catch(() => [r.reservation_id, []])),
      );
      setPays(Object.fromEntries(entries));
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

  // 결제하기 : ① 결제 건 생성(서버가 금액·주문번호 결정) → ② 토스 결제창 → ③ 돌아오면 App이 승인 API 호출
  async function pay(r, method) {
    setPaying(r.reservation_id);
    try {
      const payment = await api.createPayment(r.reservation_id);
      await openPaymentWindow({ method, payment, reservation: r, customerName: me.name });
    } catch (e) {
      // 결제창을 닫은 경우(USER_CANCEL)는 실패로 알리지 않는다
      if (e?.code !== "USER_CANCEL") notify("bad", `${e.status || ""} ${e.code || ""} · ${e.message}`);
      onChanged();
    } finally {
      setPaying(null);
    }
  }


  async function openDetail(id) {
    try {
      setDetail(await api.reservation(id));
    } catch (e) {
      notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);
    }
  }

  if (!list) return <div className="page muted">불러오는 중…</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1>내 예매</h1>
        <span className="muted">{list.length}건</span>
      </div>
      {list.length === 0 && <div className="card muted">아직 예매가 없어요. "축제"에서 예매해 보세요.</div>}

      <div className="res-list">
        {[...list].reverse().map((r) => {
          const active = r.status === "PENDING" || r.status === "CONFIRMED";
          const due = r.deposit_due_at ? new Date(r.deposit_due_at).getTime() - now : null;
          const exp = new Date(r.expires_at).getTime() - now;
          const payment = latest(pays[r.reservation_id]);
          const waiting = payment?.status === "WAITING_FOR_DEPOSIT";
          const paid = payment?.status === "DONE";
          return (
            <article key={r.reservation_id} className={`res-card ${r.status}`}>
              <div className="res-top">
                <div>
                  <span className="res-id">#{r.reservation_id}</span>
                  <b>{r.festival_name}</b> · {TYPE_LABEL[r.ticket_type]} × {r.quantity}장
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

              {r.status === "PENDING" && (
                <div className={`pay-box ${waiting || paid ? "issued" : ""}`}>
                  <div className="pay-state">
                    <span className="eyebrow">결제</span>
                    <b>{payment ? PAY_LABEL[payment.status] || payment.status : "아직 결제 전"}</b>
                    {payment?.method && <span className="muted">{payment.method}</span>}
                  </div>
                  {!waiting && !paid && (
                    <div className="res-actions">
                      <button className="primary" disabled={paying === r.reservation_id} onClick={() => pay(r, "가상계좌")}>
                        가상계좌로 결제
                      </button>
                      <button className="ghost" disabled={paying === r.reservation_id} onClick={() => pay(r, "카드")}>
                        카드로 결제
                      </button>
                    </div>
                  )}
                </div>
              )}

              <div className="res-actions">
                <button className="ghost" onClick={() => openDetail(r.reservation_id)}>상세</button>
              </div>

              {detail?.reservation_id === r.reservation_id && (
                <div className="card info">
                  <div><span>축제 / 장소</span><b>{detail.festival_name} · {detail.venue}</b></div>
                  <div><span>상태</span><b>{STATUS_LABEL[detail.status]}</b></div>
                  <div><span>총 금액</span><b>{won(detail.total_price)}</b></div>
                  <div><span>할인</span><b>{detail.discount_type} · -{won(detail.discount_amount)}</b></div>
                  <div><span>최종 금액</span><b>{won(detail.final_price)}</b></div>
                  <div><span>예매 시각</span><b>{new Date(detail.created_at).toLocaleString("ko-KR")}</b></div>
                  <div><span>입금 확인</span><b>{detail.confirmed_at ? new Date(detail.confirmed_at).toLocaleString("ko-KR") : "-"}</b></div>
                  <div><span>취소</span><b>{detail.canceled_at ? new Date(detail.canceled_at).toLocaleString("ko-KR") : "-"}</b></div>
                  <div><button className="ghost small" onClick={() => setDetail(null)}>닫기</button></div>
                </div>
              )}

              {active && (
                <div className="res-actions">
                  <button className="danger" onClick={() => act(() => api.cancelReservation(r.reservation_id), `#${r.reservation_id} 취소 완료`)}>
                    취소
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
