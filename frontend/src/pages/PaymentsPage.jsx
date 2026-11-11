// 결제 내역 : 목록 / 상세 / 상태 재확인(reconcile) / 결제 취소(환불)
import { useEffect, useState } from "react";
import { api } from "../api/endpoints";

const won = (n) => `${n.toLocaleString()}원`;
const fmt = (s) => (s ? new Date(s).toLocaleString("ko-KR") : "-");
const CANCELABLE = ["DONE", "WAITING_FOR_DEPOSIT"];

export default function PaymentsPage({ version, notify }) {
  const [list, setList] = useState(null);
  const [detail, setDetail] = useState(null);
  const [reason, setReason] = useState("단순 변심");
  const [bank, setBank] = useState("");
  const [account, setAccount] = useState("");
  const [holder, setHolder] = useState("");

  async function load() {
    // 결제 목록 API는 reservation_id가 필수 → 내 예매마다 결제 목록을 받아 합친다
    try {
      const reservations = await api.myReservations({ trace: false });
      const lists = await Promise.all(
        reservations.map((r) => api.payments(r.reservation_id).catch(() => [])),
      );
      setList(lists.flat().sort((a, b) => a.payment_id - b.payment_id));
    } catch (e) {
      setList([]); // 실패해도 "불러오는 중"에 멈추지 않게
      notify("bad", `${e.status} ${e.message}`);
    }
  }
  useEffect(() => {
    load();
  }, [version]);

  async function run(fn, okMsg) {
    try {
      const p = await fn();
      setDetail(p);
      notify("good", okMsg);
      load();
    } catch (e) {
      notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);
    }
  }

  function cancel(p) {
    // 가상계좌 입금 완료 건은 환불 계좌가 필요하다 (카드는 필요 없음)
    const refund = bank && account && holder ? { bank, account_number: account, holder_name: holder } : undefined;
    if (!window.confirm(`결제 #${p.payment_id}(${won(p.amount)})를 취소할까요?`)) return;
    run(() => api.cancelPayment(p.payment_id, { reason, refund_account: refund }), `결제 #${p.payment_id} 취소 완료`);
  }

  if (!list) return <div className="page muted">불러오는 중…</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1>결제 내역</h1>
        <span className="muted">{list.length}건</span>
      </div>
      {list.length === 0 && <div className="card muted">결제 내역이 없어요.</div>}
      {list.length > 0 && (
        <div className="card table-card">
          <table>
            <thead>
              <tr><th>#</th><th>예매</th><th>금액</th><th>수단</th><th>상태</th><th /></tr>
            </thead>
            <tbody>
              {[...list].reverse().map((p) => (
                <tr key={p.payment_id}>
                  <td>{p.payment_id}</td>
                  <td>#{p.reservation_id}</td>
                  <td>{won(p.amount)}</td>
                  <td>{p.method || "-"}</td>
                  <td><span className="pill">{p.status}</span></td>
                  <td>
                    <button className="ghost small" onClick={() => api.payment(p.payment_id).then(setDetail).catch((e) => notify("bad", `${e.status} ${e.message}`))}>상세</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail && (
        <section className="card form">
          <div className="page-head">
            <h2>결제 #{detail.payment_id} 상세</h2>
            <button className="ghost small" onClick={() => setDetail(null)}>닫기</button>
          </div>
          <div className="info">
            <div><span>주문번호</span><b>{detail.order_id}</b></div>
            <div><span>상태</span><b>{detail.status}</b></div>
            <div><span>금액</span><b>{won(detail.amount)}</b></div>
            <div><span>수단</span><b>{detail.method || "-"}</b></div>
            <div><span>결제 시각</span><b>{fmt(detail.paid_at)}</b></div>
            <div><span>취소 시각</span><b>{fmt(detail.canceled_at)}</b></div>
          </div>
          <div className="res-actions">
            <button className="ghost" onClick={() => run(() => api.reconcilePayment(detail.payment_id), "토스 결제 상태를 다시 확인했어요")}>
              결제 상태 재확인
            </button>
          </div>
          {CANCELABLE.includes(detail.status) && (
            <>
              <label className="field-label" htmlFor="pc-reason">취소 사유</label>
              <input id="pc-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} />
              {detail.method === "가상계좌" && (
                <>
                  <p className="hint">가상계좌 입금 완료 건은 환불 받을 계좌가 필요해요.</p>
                  <input placeholder="은행 (예: 신한)" value={bank} onChange={(e) => setBank(e.target.value)} />
                  <input placeholder="계좌번호 (숫자만)" value={account} onChange={(e) => setAccount(e.target.value)} />
                  <input placeholder="예금주" value={holder} onChange={(e) => setHolder(e.target.value)} />
                </>
              )}
              <button className="danger" onClick={() => cancel(detail)}>결제 취소</button>
            </>
          )}
        </section>
      )}
    </div>
  );
}
