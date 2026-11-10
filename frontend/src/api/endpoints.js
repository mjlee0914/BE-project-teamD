import { request } from "./client";

// 화면 초기 데이터처럼 설명할 필요 없는 호출은 trace: false
export const api = {
  users: () => request("GET", "/demo/users", { trace: false }),
  reset: () => request("POST", "/demo/reset", { trace: false }),

  festival: (id) => request("GET", `/v1/festivals/${id}`, { trace: false }),
  performances: (festivalId, { trace = false } = {}) =>
    request("GET", `/v1/festivals/${festivalId}/performances?size=10`, { trace }),

  createReservation: (body) => request("POST", "/v1/reservations", { body }),
  myReservations: ({ trace = true } = {}) => request("GET", "/v1/reservations/me", { trace }),
  cancelReservation: (id, opts = {}) =>
    request("PATCH", `/v1/reservations/${id}/cancel`, opts),

  // 입금 완료 시뮬레이션 (실제로는 결제 웹훅 → confirm_reservation)
  confirmReservation: (id) => request("POST", `/demo/reservations/${id}/confirm`),
  // 입금 기한 경과 시뮬레이션 → 서버 만료 작업(expire_overdue) 1회 실행
  expireReservation: (id) => request("POST", `/demo/reservations/${id}/expire`),

  myTickets: () => request("GET", "/v1/tickets?size=50"),

  festivalReservations: (festivalId, { day, statuses = [] } = {}) => {
    const q = new URLSearchParams({ size: "50" });
    if (day) q.set("day", day);
    statuses.forEach((s) => q.append("statuses", s));
    return request("GET", `/v1/festivals/${festivalId}/reservations?${q}`);
  },
};
