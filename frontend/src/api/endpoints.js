import { request } from "./client";

// 화면 초기 데이터처럼 설명할 필요 없는 호출은 trace: false
export const api = {
  // ── 회원·인증 (실제 API)
  signup: (body) => request("POST", "/v1/users", { body, auth: false }),
  login: (email, password, { trace = true } = {}) =>
    request("POST", "/v1/auth/login", { body: { email, password }, auth: false, trace }),
  logout: () => request("POST", "/v1/auth/logout"),
  me: ({ trace = false } = {}) => request("GET", "/v1/users/me", { trace }),
  updateMe: (body) => request("PATCH", "/v1/users/me", { body }),

  // ── 축제·회차
  festivals: ({ trace = true } = {}) => request("GET", "/v1/festivals?size=20", { trace, auth: false }),
  festival: (id) => request("GET", `/v1/festivals/${id}`, { trace: false, auth: false }),
  performances: (festivalId, { trace = false } = {}) =>
    request("GET", `/v1/festivals/${festivalId}/performances?size=10`, { trace, auth: false }),

  // ── 예매
  createReservation: (body) => request("POST", "/v1/reservations", { body }),
  myReservations: ({ trace = true } = {}) => request("GET", "/v1/reservations/me", { trace }),
  cancelReservation: (id, opts = {}) => request("PATCH", `/v1/reservations/${id}/cancel`, opts),

  // ── 결제
  // 결제 건 생성 (서버가 예매에서 금액·주문번호를 정한다)
  createPayment: (reservationId) => request("POST", "/v1/payments", { body: { reservation_id: reservationId } }),
  // 결제창에서 받은 paymentKey로 승인 (실제 API → 토스 서버 호출)
  approvePayment: (paymentId, body) => request("POST", `/v1/payments/${paymentId}/approve`, { body }),
  payments: (reservationId) => request("GET", `/v1/payments?reservation_id=${reservationId}`, { trace: false }),

  // ── 티켓
  myTickets: () => request("GET", "/v1/tickets?size=50"),

  // ── 관리자
  festivalReservations: (festivalId, { day, statuses = [] } = {}) => {
    const q = new URLSearchParams({ size: "50" });
    if (day) q.set("day", day);
    statuses.forEach((s) => q.append("statuses", s));
    return request("GET", `/v1/festivals/${festivalId}/reservations?${q}`);
  },
};
