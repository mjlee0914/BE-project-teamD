// 내 정보 : GET /v1/users/me 조회, PATCH /v1/users/me 수정
import { useEffect, useState } from "react";
import { api } from "../api/endpoints";

export default function ProfilePage({ notify, onUpdated, onWithdrawn }) {
  const [me, setMe] = useState(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");

  function apply(u) {
    setMe(u);
    setName(u.name);
    setPhone(u.phone || "");
  }
  useEffect(() => {
    api.me({ trace: true }).then(apply).catch((e) => notify("bad", `${e.status} ${e.message}`));
  }, []);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await api.updateMe({ name, phone });
      apply(u);
      onUpdated(u);
      notify("good", "회원 정보를 수정했어요");
    } catch (err) {
      notify("bad", `${err.status} ${err.code || ""} · ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  // 비밀번호 변경 : PATCH /v1/users/me/password
  async function changePw(e) {
    e.preventDefault();
    try {
      await api.changePassword(oldPw, newPw);
      setOldPw("");
      setNewPw("");
      notify("good", "비밀번호를 변경했어요");
    } catch (err) {
      notify("bad", `${err.status} ${err.code || ""} · ${err.message}`);
    }
  }

  // 회원 탈퇴 : DELETE /v1/users/me → 성공하면 로그아웃 처리
  async function withdraw() {
    if (!window.confirm("정말 탈퇴할까요? 진행 중인 예매가 있으면 탈퇴할 수 없어요.")) return;
    try {
      await api.withdraw();
      notify("good", "탈퇴했어요");
      onWithdrawn();
    } catch (err) {
      notify("bad", `${err.status} ${err.code || ""} · ${err.message}`);
    }
  }

  if (!me) return <div className="page muted">불러오는 중…</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1>내 정보</h1>
        <span className={`pill ${me.role === "ADMIN" ? "CONFIRMED" : ""}`}>{me.role}</span>
      </div>
      <section className="card info">
        <div><span>회원 번호</span><b>#{me.id}</b></div>
        <div><span>이메일</span><b>{me.email}</b></div>
        <div><span>상태</span><b>{me.status}</b></div>
        <div><span>가입일</span><b>{new Date(me.created_at).toLocaleDateString("ko-KR")}</b></div>
      </section>
      <form className="card form" onSubmit={save}>
        <h2>정보 수정</h2>
        <label className="field-label" htmlFor="p-name">이름 (2~20자)</label>
        <input id="p-name" value={name} onChange={(e) => setName(e.target.value)} required />
        <label className="field-label" htmlFor="p-phone">전화번호</label>
        <input id="p-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="01012345678" required />
        <button className="primary big" disabled={busy}>{busy ? "저장 중…" : "저장"}</button>
        <p className="hint">이메일과 권한은 바꿀 수 없어요. 이름과 전화번호를 함께 보내야 반영돼요.</p>
      </form>
      <form className="card form" onSubmit={changePw}>
        <h2>비밀번호 변경</h2>
        <label className="field-label" htmlFor="p-old">현재 비밀번호</label>
        <input id="p-old" type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} autoComplete="current-password" required />
        <label className="field-label" htmlFor="p-new">새 비밀번호</label>
        <input id="p-new" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} autoComplete="new-password" required />
        <button className="primary big">비밀번호 변경</button>
      </form>
      <section className="card form">
        <h2>회원 탈퇴</h2>
        <p className="hint">탈퇴하면 같은 계정으로 다시 로그인할 수 없어요.</p>
        <button className="danger" onClick={withdraw}>회원 탈퇴</button>
      </section>
    </div>
  );
}
