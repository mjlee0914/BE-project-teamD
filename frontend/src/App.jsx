// 좌우 분할 : 왼쪽 서비스 화면 / 오른쪽 백엔드 코드 흐름
// 왼쪽은 실제 서비스 흐름을 그대로 따른다
//   회원가입·로그인(JWT) → 축제 목록 → 예매 → 결제(토스 결제창 → 승인) → 입금 확인 → 티켓
import { useEffect, useRef, useState } from "react";
import { api } from "./api/endpoints";
import { getToken, setSession, setUnauthorizedHandler, setWho } from "./api/client";
import { readPaymentReturn } from "./api/toss";
import { traceBus } from "./trace/traceBus";
import TracePanel from "./trace/TracePanel";
import AuthPage from "./pages/AuthPage";
import FestivalsPage from "./pages/FestivalsPage";
import ReservePage from "./pages/ReservePage";
import MyReservationsPage from "./pages/MyReservationsPage";
import MyTicketsPage from "./pages/MyTicketsPage";
import ProfilePage from "./pages/ProfilePage";
import AdminPage from "./pages/AdminPage";
import AdminManagePage from "./pages/AdminManagePage";
import PaymentsPage from "./pages/PaymentsPage";

const TABS = [
  ["festivals", "축제"],
  ["mine", "내 예매"],
  ["tickets", "내 티켓"],
  ["payments", "결제 내역"],
  ["profile", "내 정보"],
  ["admin", "관리자 예매"],
  ["manage", "관리자 운영"],
];

// 결제창에서 돌아온 직후인지 (페이지가 새로 열린 첫 순간에 한 번만 읽는다)
const paymentReturn = readPaymentReturn();

export default function App() {
  const [me, setMe] = useState(null);
  const [booting, setBooting] = useState(Boolean(getToken()));
  const [tab, setTab] = useState(paymentReturn ? "mine" : "festivals");
  const [festivalId, setFestivalId] = useState(null); // 예매 화면에서 보고 있는 축제
  const [version, setVersion] = useState(0);
  const [toast, setToast] = useState(null);
  const [collapsed, setCollapsed] = useState(false);
  const [pending, setPending] = useState(0);
  useEffect(() => traceBus.subscribePending(setPending), []);

  function notify(tone, text) {
    setToast({ tone, text, at: Date.now() });
  }
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  const refresh = () => setVersion((v) => v + 1);

  function clearSession() {
    setSession(null);
    setMe(null);
    setFestivalId(null);
    setTab("festivals");
  }

  // 토큰으로 내 정보 조회 → 로그인 상태 확정
  async function enter(token) {
    setSession(token);
    const user = await api.me();
    setWho(user.name);
    setMe(user);
    return user;
  }

  // 처음 열 때 : 저장된 토큰이 있으면 로그인 복원, 결제창에서 돌아왔으면 승인까지 진행
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearSession();
      notify("bad", "로그인이 만료됐어요. 다시 로그인해 주세요.");
    });
    (async () => {
      if (!getToken()) return;
      try {
        await enter(getToken());
      } catch {
        clearSession();
        return;
      } finally {
        setBooting(false);
      }
      if (paymentReturn) await finishPayment(paymentReturn);
    })();
  }, []);

  // 결제창 인증 완료 → 서버 승인 API (이 안에서 토스 서버 호출)
  async function finishPayment(ret) {
    if (!ret.ok) {
      notify("bad", `결제를 완료하지 못했어요 · ${ret.message || ret.code || ""}`);
      return;
    }
    try {
      const payment = await api.approvePayment(ret.paymentId, { payment_key: ret.paymentKey, amount: ret.amount });
      if (payment.status === "DONE") {
        notify("good", `결제 완료 · 예매 #${payment.reservation_id}`);
      } else {
        notify("good", `가상계좌 발급 완료 · 예매 #${payment.reservation_id} 입금 대기`);
      }
    } catch (e) {
      notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);
    }
    refresh();
  }

  async function logout() {
    try {
      await api.logout(); // 서버가 이 토큰을 차단 목록에 올린다
    } catch {
      /* 이미 만료된 토큰이어도 화면에서는 로그아웃 */
    }
    clearSession();
  }



  const props = { version, notify };
  const isAdmin = me?.role === "ADMIN";

  return (
    <div className={`app ${collapsed ? "wide" : ""}`}>
      <main className="left">
        <header className="topbar">
          <div className="brand">
            <span className="logo">D</span>
            <div>
              <div className="brand-name">TeamD 페스티벌 예매</div>
              <div className="brand-sub">FastAPI 백엔드 실시간 데모</div>
            </div>
          </div>
          <div className="user-switch">
            {me && (
              <>
                <span className="me-chip">
                  {me.name}
                  {isAdmin && <span className="admin-dot">ADMIN</span>}
                </span>
                <button className="ghost small" onClick={logout}>로그아웃</button>
              </>
            )}
          </div>
        </header>

        {me && (
          <nav className="tabs">
            {TABS.map(([k, label]) => (
              <button key={k} className={tab === k ? "on" : ""} onClick={() => { setTab(k); if (k === "festivals") setFestivalId(null); refresh(); }}>
                {label}
              </button>
            ))}
            <span className="as">JWT 토큰으로 <b>{me.name}</b> 요청 중</span>
          </nav>
        )}

        <div className="content">
          {booting && <div className="page muted">로그인 확인 중…</div>}
          {!booting && !me && <AuthPage notify={notify} onLogin={enter} />}
          {me && tab === "festivals" && !festivalId && <FestivalsPage {...props} onSelect={setFestivalId} />}
          {me && tab === "festivals" && festivalId && (
            <ReservePage {...props} festivalId={festivalId} onBack={() => setFestivalId(null)} onReserved={() => { setTab("mine"); refresh(); }} />
          )}
          {me && tab === "mine" && <MyReservationsPage {...props} me={me} onChanged={refresh} />}
          {me && tab === "tickets" && <MyTicketsPage {...props} isAdmin={isAdmin} />}
          {me && tab === "payments" && <PaymentsPage {...props} />}
          {me && tab === "manage" && <AdminManagePage {...props} isAdmin={isAdmin} />}
          {me && tab === "profile" && <ProfilePage notify={notify} onUpdated={(u) => { setWho(u.name); setMe(u); }} onWithdrawn={clearSession} />}
          {me && tab === "admin" && <AdminPage {...props} festivalId={festivalId || 1} isAdmin={isAdmin} />}
        </div>

        {/* 떠 있는 팝업 : 내용을 밀지 않음 */}
        <div className="popups">
          {pending > 0 && !collapsed && (
            <div className="popup wait">
              <span className="spinner" />
              <div>
                <b>서버 처리 중</b>
                <span>오른쪽 코드 흐름이 끝나면 화면에 반영돼요 · → 다음 단계</span>
              </div>
            </div>
          )}
          {toast && (
            <div key={toast.at} className={`popup ${toast.tone}`}>
              <span className="icon">{toast.tone === "good" ? "✓" : "!"}</span>
              <div>
                <b>{toast.tone === "good" ? "완료" : "실패"}</b>
                <span>{toast.text}</span>
              </div>
            </div>
          )}
        </div>
      </main>

      <TracePanel collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
    </div>
  );
}
