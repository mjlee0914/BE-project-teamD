// 모든 API 호출이 지나가는 단 하나의 함수
// - 요청 직전 : traceBus에 "request" 이벤트 → 오른쪽 패널이 코드 흐름 재생 시작
// - 응답 후   : traceBus에 "response" 이벤트 → 성공/실패 경로로 마무리
// - 로그인으로 받은 JWT를 Authorization: Bearer 헤더에 실어 보낸다 (실제 서비스와 같은 방식)
import { traceBus } from "../trace/traceBus";

// 토큰은 탭을 닫으면 사라지는 sessionStorage에 둔다
// → 토스 결제창에 다녀오면 페이지가 새로 열리는데, 그때도 로그인이 유지되어야 함
const TOKEN_KEY = "demo-access-token";
let token = null;
try {
  token = sessionStorage.getItem(TOKEN_KEY);
} catch {
  /* 저장소를 못 쓰는 환경이면 메모리에만 둔다 */
}
let who = null; // 오른쪽 패널에 "누가 보낸 요청인지" 표시할 이름
let onUnauthorized = null;

export function getToken() {
  return token;
}
export function setSession(nextToken, name = null) {
  token = nextToken;
  who = name;
  try {
    if (nextToken) sessionStorage.setItem(TOKEN_KEY, nextToken);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 무시 */
  }
}
export function setWho(name) {
  who = name;
}
// 토큰이 만료·로그아웃·서버 재시작으로 401이 되면 호출 (App이 로그인 화면으로 보냄)
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

let seq = 0;

// "/v1/reservations/12/cancel" → "/v1/reservations/{id}/cancel"
// 숫자 조각을 {id}로 바꿔 flows.js의 경로와 맞춘다
export function toTemplate(path) {
  return path.split("?")[0].replace(/\/\d+(?=\/|$)/g, "/{id}");
}

// 오른쪽 패널에 요청 본문을 보여줄 때 비밀번호는 가린다
function maskBody(body) {
  if (!body || typeof body !== "object") return body;
  const out = { ...body };
  for (const k of Object.keys(out)) if (/password/i.test(k)) out[k] = "••••••••";
  return out;
}

export class ApiError extends Error {
  constructor(status, json) {
    super(json?.message || json?.detail || `HTTP ${status}`);
    this.status = status;
    this.code = json?.code;
    this.json = json;
  }
}

// opts
//   body    : JSON 본문
//   trace   : false면 오른쪽 패널에 보여주지 않음 (화면 초기 데이터 등)
//   auth    : false면 토큰을 붙이지 않음 (로그인·회원가입)
//   token   : 이 요청만 다른 사람의 토큰으로 보냄 (동시 취소 시연의 관리자 요청)
//   as      : token을 바꿨을 때 패널에 표시할 이름
export async function request(method, path, { body, trace = true, auth = true, token: override, as } = {}) {
  const id = ++seq;
  const template = toTemplate(path);
  const useToken = auth ? override ?? token : null;

  if (trace) {
    traceBus.addPending(1);
    traceBus.emit({ type: "request", id, method, path, template, body: maskBody(body), userId: auth ? as ?? who : null });
  }

  const headers = { "Content-Type": "application/json" };
  if (useToken) headers.Authorization = `Bearer ${useToken}`;

  // 응답을 받은 뒤, 오른쪽 패널이 이 요청의 마지막 단계에 도착할 때까지 기다렸다가 왼쪽에 반영
  const finish = async (status, json) => {
    if (!trace) return;
    const done = traceBus.waitFor(id);
    traceBus.emit({ type: "response", id, status, json });
    await done;
    traceBus.addPending(-1);
  };

  let res;
  let json = null;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    json = res.status === 204 ? null : await res.json().catch(() => null);
  } catch (e) {
    await finish(0, { message: String(e) });
    throw new ApiError(0, { message: "서버에 연결할 수 없습니다." });
  }

  await finish(res.status, json);

  if (!res.ok) {
    // 내 토큰이 더 이상 유효하지 않음 → 로그인 화면으로
    if (res.status === 401 && auth && !override && token && onUnauthorized) onUnauthorized();
    throw new ApiError(res.status, json);
  }
  return json?.data ?? null;
}
