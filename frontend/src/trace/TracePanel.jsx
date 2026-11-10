// 오른쪽 코드 패널
// - client.js가 보내는 request/response 이벤트를 받아 "실행 기록(run)"을 만든다
// - run마다 step을 한 칸씩 진행하고, 응답 코드에 따라 성공/실패 지점에서 멈춘다
// - 거의 동시에 들어온 요청 2개는 2열로 나란히 보여준다 (동시 취소 시연)
import { useEffect, useReducer, useRef, useState } from "react";
import { traceBus } from "./traceBus";
import { findFlow, pickOutcome } from "./flows";
import CodeView from "./CodeView";

const LAYERS = [
  ["router", "라우터"],
  ["auth", "인증"],
  ["service", "서비스"],
  ["domain", "도메인"],
  ["repository", "저장소"],
  ["demo", "데모"],
];
const WAIT_TICKS = 3; // 잠금 대기 연출 길이
const BASE_MS = 1600; // 1x 기준 한 단계 시간
const SPEEDS = [
  [0, "수동 (→ 키)"],
  [0.25, "0.25x"],
  [0.5, "0.5x"],
  [1, "1x"],
  [2, "2x"],
];

function loadSpeed() {
  try {
    const v = Number(localStorage.getItem("trace-speed"));
    return SPEEDS.some(([s]) => s === v) && localStorage.getItem("trace-speed") !== null ? v : 0.5;
  } catch {
    return 0.5;
  }
}

function stepIndex(flow, id) {
  return flow.steps.findIndex((s) => s.id === id);
}

function targetOf(run) {
  const last = run.flow.steps.length - 1;
  if (!run.response) return last;
  const idx = run.outcome?.stopAt ? stepIndex(run.flow, run.outcome.stopAt) : -1;
  return idx >= 0 ? idx : last;
}

// run 하나를 한 칸 진행 (잠금 대기 연출 → 다음 step → 마지막이면 성공/실패 확정)
function advance(r) {
  if (r.phase !== "playing") return r;
  if (r.waitLeft > 0) return { ...r, waitLeft: r.waitLeft - 1 };
  const waitIdx = r.outcome?.waitAt ? stepIndex(r.flow, r.outcome.waitAt) : -1;
  if (waitIdx >= 0 && r.step === waitIdx && !r.waited) {
    return { ...r, waitLeft: WAIT_TICKS, waited: true };
  }
  const target = targetOf(r);
  if (r.step < target) return { ...r, step: r.step + 1 };
  if (!r.response) return r; // 응답 기다리는 중
  const failed = r.response.status >= 400 || r.response.status === 0;
  return { ...r, phase: failed ? "failed" : "done" };
}

function reducer(state, action) {
  switch (action.type) {
    case "request": {
      const e = action.event;
      const flow = findFlow(e.method, e.template);
      const run = {
        id: e.id,
        method: e.method,
        path: e.path,
        body: e.body,
        userId: e.userId,
        flow,
        step: 0,
        phase: flow ? "playing" : "noflow",
        waitLeft: 0,
        waited: false,
        response: null,
        outcome: null,
        at: Date.now(),
      };
      return { ...state, runs: [...state.runs.slice(-19), run], manual: null };
    }
    case "response": {
      const { id, status, json } = action.event;
      return {
        ...state,
        runs: state.runs.map((r) => {
          if (r.id !== id) return r;
          const outcome = r.flow ? pickOutcome(r.flow, status, json?.code) : null;
          const phase = r.phase === "noflow" ? (status < 400 ? "done" : "failed") : r.phase;
          return { ...r, response: { status, json }, outcome, phase };
        }),
      };
    }
    case "tick":
      return { ...state, runs: state.runs.map(advance) };
    // 다음 단계 : 재생 중이면 한 칸 진행(성공/실패 판정 포함), 이미 끝났으면 단계만 앞으로
    case "next":
      return {
        ...state,
        runs: state.runs.map((r) => {
          if (!action.ids.includes(r.id) || !r.flow) return r;
          if (r.phase === "playing") {
            let n = advance(r);
            while (n.phase === "playing" && n.waitLeft > 0) n = advance(n); // 대기 연출은 건너뜀
            return n;
          }
          return { ...r, step: Math.min(r.step + 1, r.flow.steps.length - 1) };
        }),
      };
    case "prev":
      return {
        ...state,
        runs: state.runs.map((r) =>
          action.ids.includes(r.id) && r.flow ? { ...r, step: Math.max(0, r.step - 1), waitLeft: 0 } : r,
        ),
      };
    case "replay":
      return {
        ...state,
        runs: state.runs.map((r) =>
          action.ids.includes(r.id) && r.flow ? { ...r, step: 0, phase: "playing", waited: false, waitLeft: 0 } : r,
        ),
      };
    // 단계 목록 클릭 : 그 단계로 이동하고 자동 재생은 멈춤 (끝난 run이면 결과는 유지)
    case "jump":
      return {
        ...state,
        runs: state.runs.map((r) => (r.id === action.id && r.flow ? { ...r, step: action.step, waitLeft: 0 } : r)),
      };
    case "focus":
      return { ...state, manual: action.id };
    case "clear":
      return { runs: [], manual: null };
    default:
      return state;
  }
}

export default function TracePanel({ collapsed, onToggle }) {
  const [state, dispatch] = useReducer(reducer, { runs: [], manual: null });
  const [paused, setPaused] = useState(false);
  const [speed, setSpeedState] = useState(loadSpeed);
  const setSpeed = (v) => {
    setSpeedState(v);
    try {
      localStorage.setItem("trace-speed", String(v));
    } catch {}
  };
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => traceBus.subscribe((event) => dispatch({ type: event.type, event })), []);

  // 화면 동기화 : 패널이 열려 있으면 왼쪽은 흐름이 끝날 때까지 결과 반영을 기다림
  useEffect(() => {
    traceBus.syncEnabled = !collapsed;
    if (collapsed) traceBus.releaseAll();
    return () => {
      traceBus.syncEnabled = false;
      traceBus.releaseAll();
    };
  }, [collapsed]);

  // 성공/실패가 확정된 run → 왼쪽에 결과 반영 허용
  useEffect(() => {
    state.runs.forEach((r) => {
      if (r.phase === "done" || r.phase === "failed") traceBus.release(r.id);
    });
  }, [state.runs]);

  useEffect(() => {
    if (speed === 0) return; // 수동 모드 : 자동 진행 없음
    const t = setInterval(() => {
      if (!pausedRef.current) dispatch({ type: "tick" });
    }, BASE_MS / speed);
    return () => clearInterval(t);
  }, [speed]);

  // 화면에 보여줄 run
  // - 기록 칩을 눌렀으면 그 run
  // - 아니면 "아직 재생 중인 run 중 가장 먼저 온 것" (재생이 끝나야 다음 요청으로 넘어감)
  // - 재생 중인 게 없으면 가장 최근 run
  // + 같은 API가 0.5초 안에 함께 들어왔으면 나란히 (동시 요청 시연)
  const playing = state.runs.filter((r) => r.phase === "playing");
  const focusRun =
    state.runs.find((r) => r.id === state.manual) || playing[0] || state.runs[state.runs.length - 1];
  const shown = focusRun
    ? state.runs.filter(
        (r) => r === focusRun || (r.flow && r.flow === focusRun.flow && Math.abs(r.at - focusRun.at) < 500),
      )
    : [];

  const shownIds = shown.filter((r) => r.flow).map((r) => r.id);
  const manualMode = speed === 0;
  const stopped = paused || manualMode;
  const go = (type) => shownIds.length && dispatch({ type, ids: shownIds });

  // 키보드 : Space 일시정지/재생, → 다음 단계, ← 이전 단계 (입력창에 있을 때는 무시)
  const goRef = useRef(go);
  goRef.current = go;
  useEffect(() => {
    const onKey = (e) => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        goRef.current("next");
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        goRef.current("prev");
      } else if (e.key === " ") {
        e.preventDefault();
        setPaused((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (collapsed) {
    return (
      <aside className="trace collapsed">
        <button className="ghost vertical" onClick={onToggle}>◀ 코드 흐름 보기</button>
      </aside>
    );
  }

  return (
    <aside className="trace">
      <header className="trace-head">
        <div>
          <div className="eyebrow">BACKEND · 실행 흐름</div>
          <div className="trace-title">{focusRun ? (focusRun.flow?.title || "흐름 정의 없음") : "왼쪽에서 아무 버튼이나 눌러 보세요"}</div>
          {stopped && shownIds.length > 0 && (
            <div className="hint-keys">{manualMode ? "수동 모드" : "일시정지"} · → 다음 단계 · ← 이전 단계</div>
          )}
        </div>
        <div className="controls">
          {!manualMode && (
            <button className={`ghost ${paused ? "attn" : ""}`} onClick={() => setPaused((p) => !p)} title="일시정지 / 재생 (Space)">
              {paused ? "▶" : "⏸"}
            </button>
          )}
          <button className="ghost" disabled={!shownIds.length} onClick={() => go("prev")} title="이전 단계 (←)">⏮</button>
          <button className={`ghost ${stopped ? "attn" : ""}`} disabled={!shownIds.length} onClick={() => go("next")} title="다음 단계 (→)">⏭</button>
          <button className="ghost" disabled={!shownIds.length} onClick={() => go("replay")} title="처음부터 다시">↻</button>
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} title="재생 속도">
            {SPEEDS.map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
          <button className="ghost" onClick={onToggle} title="패널 접기">▶</button>
        </div>
      </header>

      <div className={`runs cols-${shown.length}`}>
        {shown.length === 0 && <EmptyState />}
        {shown.map((run, i) => (
          <RunView
            key={run.id}
            run={run}
            label={shown.length > 1 ? `요청 ${String.fromCharCode(65 + i)}` : null}
            onJump={(id, step) => dispatch({ type: "jump", id, step })}
          />
        ))}
      </div>

      <footer className="history">
        {state.runs.slice().reverse().map((r) => (
          <button
            key={r.id}
            className={`chip ${r.phase} ${focusRun?.id === r.id ? "active" : ""}`}
            onClick={() => dispatch({ type: "focus", id: r.id })}
            title={r.path}
          >
            <b>{r.method}</b> {r.path.replace(/\?.*/, "")}
            {r.response && <span className="st">{r.response.status}</span>}
          </button>
        ))}
        {state.runs.length > 0 && <button className="ghost small" onClick={() => {
              traceBus.releaseAll();
              dispatch({ type: "clear" });
            }}>지우기</button>}
      </footer>
    </aside>
  );
}

function EmptyState() {
  return (
    <div className="empty">
      <p>왼쪽 화면에서 API 요청이 나가면</p>
      <p>
        <b>라우터 → 서비스 → 도메인 → 저장소</b>
      </p>
      <p>순서로 실제 백엔드 코드가 강조돼요.</p>
    </div>
  );
}

function RunView({ run, label, onJump }) {
  if (!run.flow) {
    return (
      <section className="run">
        <RequestLine run={run} label={label} />
        <div className="empty">이 API는 아직 흐름이 정의되지 않았어요.</div>
        <ResponseBox run={run} />
      </section>
    );
  }
  const base = run.flow.steps[run.step];
  // 실패해서 멈춘 step이면 outcome.anchor(보통 raise 줄)를 강조
  const step =
    run.phase === "failed" && run.outcome?.anchor && run.outcome.stopAt === base.id
      ? { ...base, anchor: run.outcome.anchor }
      : base;
  const tone = run.phase === "failed" ? "bad" : run.phase === "done" ? "good" : run.waitLeft > 0 ? "wait" : "now";
  const usedLayers = new Set(run.flow.steps.map((s) => s.layer));
  const passed = new Set(run.flow.steps.slice(0, run.step + 1).map((s) => s.layer));

  return (
    <section className={`run ${run.phase}`}>
      <RequestLine run={run} label={label} />
      {run.flow.badge && <div className="badge-line">{run.flow.badge}</div>}

      <div className="layers">
        {LAYERS.filter(([k]) => usedLayers.has(k)).map(([k, name]) => (
          <span key={k} className={`layer ${k} ${passed.has(k) ? "on" : ""} ${step.layer === k ? "cur" : ""}`}>{name}</span>
        ))}
      </div>

      <ol className="steps">
        {run.flow.steps.map((s, i) => (
          <li
            key={s.id}
            className={i < run.step ? "past" : i === run.step ? `cur ${tone}` : ""}
            onClick={() => onJump?.(run.id, i)}
            title="이 단계로 이동"
          >
            <span className="dot" />
            <span className="sym">{s.symbol}</span>
          </li>
        ))}
      </ol>

      <div className="file-line">
        <span className={`layer-tag ${step.layer}`}>{step.layer}</span>
        <span className="file">{step.file}</span>
      </div>
      <CodeView step={step} tone={tone} />

      <div className={`note ${tone}`}>
        {run.waitLeft > 0 ? "⏳ 다른 요청이 이 예매 행을 잠그고 있어서 기다리는 중…" : step.note}
      </div>

      {(run.phase === "done" || run.phase === "failed") && run.outcome?.note && (
        <div className={`verdict ${run.phase}`}>
          {run.phase === "done" ? "✓" : "✕"} {run.outcome.note}
        </div>
      )}
      <ResponseBox run={run} />
    </section>
  );
}

function RequestLine({ run, label }) {
  return (
    <div className="req">
      {label && <span className="req-label">{label}</span>}
      <span className={`method ${run.method}`}>{run.method}</span>
      <span className="path">{run.path.replace(/\?.*/, "")}</span>
      {run.userId && <span className="who">user {run.userId}</span>}
    </div>
  );
}

function ResponseBox({ run }) {
  const [open, setOpen] = useState(false);
  if (!run.response) return <div className="resp pending">응답 대기 중…</div>;
  const { status, json } = run.response;
  const ok = status > 0 && status < 400;
  return (
    <div className={`resp ${ok ? "ok" : "err"}`}>
      <button className="resp-head" onClick={() => setOpen((o) => !o)}>
        <span className="status">{status || "ERR"}</span>
        <span>{json?.code || ""}</span>
        <span className="msg">{json?.message || ""}</span>
        <span className="toggle">{open ? "접기" : "JSON"}</span>
      </button>
      {open && <pre>{JSON.stringify(json, null, 2)}</pre>}
    </div>
  );
}
