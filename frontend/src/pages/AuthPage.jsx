// 로그인 / 회원가입 : 실제 POST /v1/auth/login, POST /v1/users 를 호출한다
import { useState } from "react";
import { api } from "../api/endpoints";

export default function AuthPage({ onLogin, notify }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "", phone: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") {
        await api.signup({
          email: form.email,
          name: form.name,
          password: form.password,
          phone: form.phone || null,
        });
        notify("good", "회원가입 완료 · 이어서 로그인할게요");
      }
      const t = await api.login(form.email, form.password);
      await onLogin(t.access_token);
    } catch (err) {
      setError(`${err.status} ${err.code || ""} · ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page auth">
      <section className="hero">
        <div className="eyebrow">KANT ROCK FESTIVAL</div>
        <h1>{mode === "login" ? "로그인" : "회원가입"}</h1>
        <p className="muted">
          {mode === "login"
            ? "이메일과 비밀번호로 로그인하면 서버가 JWT 토큰을 발급해요. 이후 모든 요청에 이 토큰이 실려요."
            : "가입하면 비밀번호는 bcrypt로 해시되어 저장돼요."}
        </p>
      </section>

      <form className="card form" onSubmit={submit}>
        <div className="seg">
          <button type="button" className={mode === "login" ? "on" : ""} onClick={() => { setMode("login"); setError(null); }}>로그인</button>
          <button type="button" className={mode === "signup" ? "on" : ""} onClick={() => { setMode("signup"); setError(null); }}>회원가입</button>
        </div>

        <label className="field-label" htmlFor="email">이메일</label>
        <input id="email" type="email" autoComplete="username" value={form.email} onChange={set("email")} placeholder="you@example.com" required />

        {mode === "signup" && (
          <>
            <label className="field-label" htmlFor="name">이름 (2~20자)</label>
            <input id="name" value={form.name} onChange={set("name")} placeholder="홍길동" required />
            <label className="field-label" htmlFor="phone">전화번호 (선택)</label>
            <input id="phone" value={form.phone} onChange={set("phone")} placeholder="01012345678" />
          </>
        )}

        <label className="field-label" htmlFor="password">
          비밀번호{mode === "signup" && " (영문·숫자·특수문자 포함 8자 이상)"}
        </label>
        <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={form.password} onChange={set("password")} required />

        {error && <div className="form-error">{error}</div>}

        <button className="primary big" disabled={busy}>
          {busy ? "처리 중…" : mode === "login" ? "로그인" : "가입하고 로그인"}
        </button>
      </form>

    </div>
  );
}
