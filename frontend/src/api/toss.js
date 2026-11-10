// 토스페이먼츠 결제창 (테스트 모드)
// - 브라우저에서 결제창을 띄워 paymentKey를 받고, 그 키를 우리 서버의 승인 API로 넘긴다
// - 클라이언트 키는 공개용 키다 (시크릿 키는 서버의 .env에만 둔다)
// - frontend/.env.local 에 VITE_TOSS_CLIENT_KEY=test_ck_... 를 넣는다
//   서버 .env의 TOSS_SECRET_KEY와 "같은 상점"의 테스트 키여야 승인이 된다 (토스 개발자센터 > API 키)
const CLIENT_KEY = import.meta.env.VITE_TOSS_CLIENT_KEY || "";
const SDK_URL = "https://js.tosspayments.com/v1/payment";

let sdk = null;
function loadSdk() {
  if (window.TossPayments) return Promise.resolve();
  if (!sdk) {
    sdk = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = SDK_URL;
      s.onload = resolve;
      s.onerror = () => {
        sdk = null;
        reject(new Error("토스 결제창을 불러오지 못했어요. 인터넷 연결을 확인하세요."));
      };
      document.head.appendChild(s);
    });
  }
  return sdk;
}

// 가상계좌 입금 마감 : "yyyy-MM-ddTHH:mm:ss" (한국 시간)
function toDueDate(iso) {
  return new Date(iso).toLocaleString("sv-SE", { timeZone: "Asia/Seoul" }).replace(" ", "T");
}

// method : "가상계좌" | "카드"
// 결제창에서 인증이 끝나면 successUrl로 돌아오고, 토스가 paymentKey·orderId·amount를 붙여 준다
export async function openPaymentWindow({ method, payment, reservation, customerName }) {
  if (!CLIENT_KEY) {
    throw Object.assign(new Error("토스 클라이언트 키가 없어요. frontend/.env.local 에 VITE_TOSS_CLIENT_KEY를 넣고 프론트를 다시 켜 주세요."), { code: "TOSS_CLIENT_KEY_MISSING" });
  }
  await loadSdk();
  const base = `${window.location.origin}/`;
  const options = {
    amount: payment.amount, // 서버가 계산해 저장한 금액
    orderId: payment.order_id, // 서버가 만든 주문번호
    orderName: `${reservation.festival_name} 예매 #${reservation.reservation_id}`,
    customerName,
    successUrl: `${base}?pay=${payment.payment_id}`,
    failUrl: `${base}?payfail=${payment.payment_id}`,
  };
  if (method === "가상계좌") {
    options.dueDate = toDueDate(reservation.deposit_due_at);
    options.cashReceipt = { type: "소득공제" };
  }
  // 사용자가 결제창을 닫으면 reject 된다
  try {
    await window.TossPayments(CLIENT_KEY).requestPayment(method, options);
  } catch (e) {
    if (e?.code === "UNAUTHORIZED_KEY") e.message = "토스가 이 클라이언트 키를 거절했어요. 개발자센터의 테스트 키가 맞는지 확인해 주세요.";
    throw e;
  }
}

// 결제창에서 돌아온 주소의 값 읽기 → 읽은 뒤 주소창에서 지운다
export function readPaymentReturn() {
  const q = new URLSearchParams(window.location.search);
  const pay = q.get("pay");
  const fail = q.get("payfail");
  if (!pay && !fail) return null;
  const result = pay
    ? { ok: true, paymentId: Number(pay), paymentKey: q.get("paymentKey"), amount: Number(q.get("amount")) }
    : { ok: false, code: q.get("code"), message: q.get("message") };
  window.history.replaceState(null, "", window.location.pathname);
  return result;
}
