// 모든 API 호출이 지나가는 단 하나의 함수
// - 요청 직전 : traceBus에 "request" 이벤트 → 오른쪽 패널이 코드 흐름 재생 시작
// - 응답 후   : traceBus에 "response" 이벤트 → 성공/실패 경로로 마무리
import { traceBus } from "../trace/traceBus";

let currentUserId = null;
export function setCurrentUser(id) {
  currentUserId = id;
}

let seq = 0;

// "/v1/reservations/12/cancel" → "/v1/reservations/{id}/cancel"
// 숫자 조각을 {id}로 바꿔 flows.js의 경로와 맞춘다
export function toTemplate(path) {
  return path.split("?")[0].replace(/\/\d+(?=\/|$)/g, "/{id}");
}

export class ApiError extends Error {
  constructor(status, json) {
    super(json?.message || `HTTP ${status}`);
    this.status = status;
    this.code = json?.code;
    this.json = json;
  }
}

export async function request(method, path, { body, trace = true, actor } = {}) {
  const id = ++seq;
  const template = toTemplate(path);
  const userId = actor ?? currentUserId;

  if (trace) {
    traceBus.addPending(1);
    traceBus.emit({ type: "request", id, method, path, template, body, userId });
  }

  const headers = { "Content-Type": "application/json" };
  if (userId) headers["X-Demo-User"] = String(userId);

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

  if (!res.ok) throw new ApiError(res.status, json);
  return json?.data ?? null;
}
