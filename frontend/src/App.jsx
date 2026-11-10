// 좌우 분할 : 왼쪽 서비스 화면 / 오른쪽 백엔드 코드 흐름
import { useEffect, useState } from "react";
import { api } from "./api/endpoints";
import { setCurrentUser } from "./api/client";
import { traceBus } from "./trace/traceBus";
import TracePanel from "./trace/TracePanel";
import ReservePage from "./pages/ReservePage";
import MyReservationsPage from "./pages/MyReservationsPage";
import MyTicketsPage from "./pages/MyTicketsPage";
import AdminPage from "./pages/AdminPage";

const TABS = [
  ["reserve", "예매하기"],
  ["mine", "내 예매"],
  ["tickets", "내 티켓"],
  ["admin", "관리자"],
];

export default function App() {
  const [users, setUsers] = useState([]);
  const [userId, setUserId] = useState(null);
  const [tab, setTab] = useState("reserve");
  const [version, setVersion] = useState(0);
  const [toast, setToast] = useState(null);
  const [collapsed, setCollapsed] = useState(false);
  const [pending, setPending] = useState(0);
  useEffect(() => traceBus.subscribePending(setPending), []);

  useEffect(() => {
    api.users().then((list) => {
      setUsers(list || []);
      if (list?.length) selectUser(list[0].user_id);
    }).catch(() => setToast({ tone: "bad", text: "백엔드(8000)에 연결할 수 없어요. 데모 서버를 먼저 실행하세요." }));
  }, []);

  function selectUser(id) {
    setCurrentUser(id);
    setUserId(id);
    setVersion((v) => v + 1);
  }

  function notify(tone, text) {
    setToast({ tone, text, at: Date.now() });
  }
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  const refresh = () => setVersion((v) => v + 1);
  const me = users.find((u) => u.user_id === userId);
  const admin = users.find((u) => u.role === "ADMIN");

  async function reset() {
    await api.reset();
    notify("good", "데모 데이터를 초기화했어요 (잔여 100석, 예매 0건)");
    refresh();
  }

  const props = { version, notify };

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
            {users.map((u) => (
              <button key={u.user_id} className={u.user_id === userId ? "on" : ""} onClick={() => selectUser(u.user_id)}>
                {u.name}
                {u.role === "ADMIN" && <span className="admin-dot">ADMIN</span>}
              </button>
            ))}
            <button className="ghost small" onClick={reset} title="데모 데이터 초기화">↺ 초기화</button>
          </div>
        </header>

        <nav className="tabs">
          {TABS.map(([k, label]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => { setTab(k); refresh(); }}>
              {label}
            </button>
          ))}
          {me && <span className="as">현재 <b>{me.name}</b>(으)로 요청 중</span>}
        </nav>

        <div className="content">
          {userId && tab === "reserve" && <ReservePage {...props} onReserved={refresh} />}
          {userId && tab === "mine" && <MyReservationsPage {...props} onChanged={refresh} adminId={admin?.user_id} />}
          {userId && tab === "tickets" && <MyTicketsPage {...props} />}
          {userId && tab === "admin" && <AdminPage {...props} isAdmin={me?.role === "ADMIN"} />}
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
