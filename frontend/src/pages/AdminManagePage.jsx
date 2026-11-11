// 관리자 : 축제 관리 / 공연(회차) 관리 / 입장 처리·입장 현황
import { useEffect, useState } from "react";
import { api } from "../api/endpoints";

// <input type="datetime-local"> 값(KST로 입력) → 서버용 ISO (+09:00)
const toIso = (v) => (v ? `${v}:00+09:00` : undefined);
// 서버 ISO → datetime-local 값 (KST)
const toLocal = (s) => {
  if (!s) return "";
  const d = new Date(new Date(s).getTime() + 9 * 3600 * 1000);
  return d.toISOString().slice(0, 16);
};
const fmt = (s) => new Date(s).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
// 빈 값은 보내지 않는다 (PATCH는 보낸 필드만 바뀜)
const compact = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== "" && v !== undefined && v !== null));

const EMPTY_FEST = { name: "", venue: "", description: "", starts_on: "", ends_on: "" };
const EMPTY_PERF = { title: "", starts_at: "", ends_at: "", booking_open_at: "", booking_close_at: "", capacity: "", price: "" };

export default function AdminManagePage({ version, notify, isAdmin }) {
  const [festivals, setFestivals] = useState([]);
  const [festId, setFestId] = useState(null);
  const [fest, setFest] = useState(EMPTY_FEST);
  const [perfs, setPerfs] = useState([]);
  const [perfEdit, setPerfEdit] = useState(null); // 수정 중인 performance_id (null이면 새로 만들기)
  const [perf, setPerf] = useState(EMPTY_PERF);
  const [code, setCode] = useState("");
  const [entryPerf, setEntryPerf] = useState("");
  const [entry, setEntry] = useState(null);

  const fail = (e) => notify("bad", `${e.status} ${e.code || ""} · ${e.message}`);

  async function loadFestivals() {
    try {
      const d = await api.festivals({ trace: false });
      setFestivals(d.items);
    } catch (e) {
      fail(e);
    }
  }
  async function loadPerfs(id = festId) {
    if (!id) return setPerfs([]);
    try {
      setPerfs((await api.performances(id))?.items || []);
    } catch (e) {
      fail(e);
    }
  }
  useEffect(() => {
    loadFestivals();
  }, [version]);
  useEffect(() => {
    loadPerfs();
  }, [festId, version]);

  async function run(fn, msg, after) {
    try {
      const r = await fn();
      notify("good", msg);
      after?.(r);
    } catch (e) {
      fail(e);
    }
  }

  // ── 축제
  function pickFestival(f) {
    setFestId(f?.festival_id ?? null);
    setFest(f ? { name: f.name, venue: f.venue, description: f.description || "", starts_on: f.starts_on, ends_on: f.ends_on } : EMPTY_FEST);
    setPerfEdit(null);
    setPerf(EMPTY_PERF);
  }
  function saveFestival(e) {
    e.preventDefault();
    if (festId) {
      run(() => api.updateFestival(festId, compact(fest)), `축제 #${festId} 수정 완료`, loadFestivals);
    } else {
      run(() => api.createFestival(compact(fest)), "축제 생성 완료", (f) => { loadFestivals(); pickFestival(f); });
    }
  }

  // ── 공연
  function pickPerf(p) {
    setPerfEdit(p?.performance_id ?? null);
    setPerf(p ? {
      title: p.title, starts_at: toLocal(p.starts_at), ends_at: toLocal(p.ends_at),
      booking_open_at: toLocal(p.booking_open_at), booking_close_at: toLocal(p.booking_close_at),
      capacity: String(p.capacity), price: String(p.price),
    } : EMPTY_PERF);
  }
  function savePerf(e) {
    e.preventDefault();
    const times = {
      starts_at: toIso(perf.starts_at), ends_at: toIso(perf.ends_at),
      booking_open_at: toIso(perf.booking_open_at), booking_close_at: toIso(perf.booking_close_at),
      capacity: perf.capacity ? Number(perf.capacity) : undefined,
    };
    if (perfEdit) {
      // 수정 가능 필드 : 시각 4개 + 수용 인원 (제목·가격은 바꿀 수 없음)
      run(() => api.updatePerformance(perfEdit, compact(times)), `회차 #${perfEdit} 수정 완료`, () => loadPerfs());
    } else {
      run(() => api.createPerformance(festId, compact({ ...times, title: perf.title, price: Number(perf.price) })), "회차 생성 완료", () => { loadPerfs(); pickPerf(null); });
    }
  }

  const setF = (k) => (e) => setFest({ ...fest, [k]: e.target.value });
  const setP = (k) => (e) => setPerf({ ...perf, [k]: e.target.value });

  return (
    <div className="page">
      <div className="page-head">
        <h1>관리자 · 축제/공연/입장</h1>
        <span className={`pill ${isAdmin ? "CONFIRMED" : "CANCELED"}`}>{isAdmin ? "관리자" : "일반 회원 (403 예상)"}</span>
      </div>

      {/* ── 축제 관리 */}
      <section className="card form">
        <h2>축제 관리</h2>
        <div className="seg small">
          <button className={!festId ? "on" : ""} onClick={() => pickFestival(null)}>+ 새 축제</button>
          {festivals.map((f) => (
            <button key={f.festival_id} className={festId === f.festival_id ? "on" : ""} onClick={() => pickFestival(f)}>
              #{f.festival_id} {f.name} ({f.status})
            </button>
          ))}
        </div>
        <form onSubmit={saveFestival}>
          <label className="field-label">이름</label>
          <input value={fest.name} onChange={setF("name")} maxLength={50} required={!festId} />
          <label className="field-label">장소</label>
          <input value={fest.venue} onChange={setF("venue")} maxLength={50} required={!festId} />
          <label className="field-label">설명</label>
          <input value={fest.description} onChange={setF("description")} />
          <div className="row">
            <div><label className="field-label">시작일</label><input type="date" value={fest.starts_on} onChange={setF("starts_on")} required={!festId} /></div>
            <div><label className="field-label">종료일</label><input type="date" value={fest.ends_on} onChange={setF("ends_on")} required={!festId} /></div>
          </div>
          <div className="res-actions">
            <button className="primary">{festId ? `축제 #${festId} 수정` : "축제 생성"}</button>
            {festId && (
              <button type="button" className="danger" onClick={() => window.confirm(`축제 #${festId}를 취소할까요? 회차·예매도 함께 취소돼요.`) && run(() => api.cancelFestival(festId), `축제 #${festId} 취소 완료`, () => { loadFestivals(); loadPerfs(); })}>
                축제 취소
              </button>
            )}
          </div>
        </form>
      </section>

      {/* ── 공연(회차) 관리 */}
      {festId && (
        <section className="card form">
          <h2>축제 #{festId} 회차 관리</h2>
          <div className="card table-card">
            <table>
              <thead><tr><th>#</th><th>제목</th><th>시작</th><th>잔여</th><th>상태</th><th /></tr></thead>
              <tbody>
                {perfs.map((p) => (
                  <tr key={p.performance_id}>
                    <td>{p.performance_id}</td>
                    <td>{p.title}</td>
                    <td>{fmt(p.starts_at)}</td>
                    <td>{p.remaining_count}/{p.capacity}</td>
                    <td><span className={`pill ${p.status}`}>{p.status}</span></td>
                    <td className="res-actions">
                      <button className="ghost small" onClick={() => pickPerf(p)}>수정</button>
                      <button className="ghost small" onClick={() => run(() => api.performanceAction(p.performance_id, "open"), `회차 #${p.performance_id} 예매 오픈`, () => loadPerfs())}>오픈</button>
                      <button className="ghost small" onClick={() => run(() => api.performanceAction(p.performance_id, "complete"), `회차 #${p.performance_id} 종료 처리`, () => loadPerfs())}>종료</button>
                      <button className="danger small" onClick={() => window.confirm(`회차 #${p.performance_id}를 취소할까요? 예매도 함께 취소돼요.`) && run(() => api.performanceAction(p.performance_id, "cancel"), `회차 #${p.performance_id} 취소`, () => loadPerfs())}>취소</button>
                    </td>
                  </tr>
                ))}
                {perfs.length === 0 && <tr><td colSpan={6} className="muted">회차가 없어요.</td></tr>}
              </tbody>
            </table>
          </div>

          <form onSubmit={savePerf}>
            <h2>{perfEdit ? `회차 #${perfEdit} 수정` : "새 회차"}</h2>
            {!perfEdit && (
              <>
                <label className="field-label">제목</label>
                <input value={perf.title} onChange={setP("title")} maxLength={50} required />
                <label className="field-label">가격 (원)</label>
                <input type="number" min="1" value={perf.price} onChange={setP("price")} required />
              </>
            )}
            <div className="row">
              <div><label className="field-label">공연 시작 (KST)</label><input type="datetime-local" value={perf.starts_at} onChange={setP("starts_at")} required={!perfEdit} /></div>
              <div><label className="field-label">공연 종료</label><input type="datetime-local" value={perf.ends_at} onChange={setP("ends_at")} required={!perfEdit} /></div>
            </div>
            <div className="row">
              <div><label className="field-label">예매 시작</label><input type="datetime-local" value={perf.booking_open_at} onChange={setP("booking_open_at")} required={!perfEdit} /></div>
              <div><label className="field-label">예매 마감</label><input type="datetime-local" value={perf.booking_close_at} onChange={setP("booking_close_at")} required={!perfEdit} /></div>
            </div>
            <label className="field-label">수용 인원</label>
            <input type="number" min="1" value={perf.capacity} onChange={setP("capacity")} required={!perfEdit} />
            <div className="res-actions">
              <button className="primary">{perfEdit ? "회차 수정" : "회차 생성"}</button>
              {perfEdit && <button type="button" className="ghost" onClick={() => pickPerf(null)}>새 회차로</button>}
            </div>
            {perfEdit && <p className="hint">제목과 가격은 수정할 수 없어요.</p>}
          </form>
        </section>
      )}

      {/* ── 입장 */}
      <section className="card form">
        <h2>입장 처리</h2>
        <form onSubmit={(e) => { e.preventDefault(); run(() => api.enterTicket(code.trim()), "입장 처리 완료", (t) => { notify("good", `티켓 #${t.ticket_id} ${t.status}`); setCode(""); }); }}>
          <label className="field-label" htmlFor="enter-code">티켓 입장 코드 (UUID)</label>
          <input id="enter-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="티켓 상세에서 확인" required />
          <button className="primary">입장</button>
        </form>

        <h2>회차별 입장 현황</h2>
        <form onSubmit={(e) => { e.preventDefault(); api.entryStatus(entryPerf).then(setEntry).catch(fail); }}>
          <label className="field-label" htmlFor="entry-perf">회차 ID</label>
          <input id="entry-perf" type="number" min="1" value={entryPerf} onChange={(e) => setEntryPerf(e.target.value)} required />
          <button className="ghost">조회</button>
        </form>
        {entry && (
          <div className="info">
            {Object.entries(entry.counts).map(([k, v]) => (
              <div key={k}><span>{k}</span><b>{v}장</b></div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
