// client.js(요청) ↔ TracePanel(오른쪽 패널) 연결 통로
//
// 1) 이벤트 : client가 request/response를 보내면 패널이 코드 흐름을 재생
// 2) 화면 동기화 : 패널이 열려 있으면 client는 응답을 받아도 바로 왼쪽에 반영하지 않고,
//    패널이 그 요청의 마지막 단계(성공/실패)에 도착할 때까지 기다린다
//    → 수동 모드에서 → 키로 넘길 때 왼쪽 화면도 같은 타이밍에 바뀜
// 3) 대기 상태 : 기다리는 요청 수를 왼쪽 화면(안내 띠)에 알려 줌

const listeners = new Set();
const waiters = new Map(); // request id → resolve
const pendingListeners = new Set();
let pending = 0;

function notifyPending() {
  pendingListeners.forEach((fn) => fn(pending));
}

export const traceBus = {
  // 패널이 열려 있을 때만 true (접으면 기다리지 않음)
  syncEnabled: false,

  emit(event) {
    listeners.forEach((fn) => fn(event));
  },
  subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },

  // client → 이 요청의 흐름이 끝날 때까지 기다림
  waitFor(id) {
    if (!this.syncEnabled) return Promise.resolve();
    return new Promise((resolve) => waiters.set(id, resolve));
  },
  // panel → 흐름이 끝났음을 알림
  release(id) {
    const fn = waiters.get(id);
    if (fn) {
      waiters.delete(id);
      fn();
    }
  },
  releaseAll() {
    [...waiters.keys()].forEach((id) => this.release(id));
  },

  // 대기 중인 요청 수
  addPending(delta) {
    pending = Math.max(0, pending + delta);
    notifyPending();
  },
  subscribePending(fn) {
    pendingListeners.add(fn);
    fn(pending);
    return () => pendingListeners.delete(fn);
  },
};
