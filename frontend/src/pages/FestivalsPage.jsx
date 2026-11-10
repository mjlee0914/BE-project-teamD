// 축제 목록 : GET /v1/festivals → 축제를 고르면 예매 화면으로
import { useEffect, useRef, useState } from "react";
import { api } from "../api/endpoints";

const STATUS_LABEL = { SCHEDULED: "예정", OPEN: "예매 중", COMPLETED: "종료", CANCELED: "취소됨" };

export default function FestivalsPage({ version, notify, onSelect }) {
  const [data, setData] = useState(null);
  const first = useRef(true);

  useEffect(() => {
    api.festivals({ trace: first.current })
      .then(setData)
      .catch((e) => notify("bad", `${e.status} ${e.message}`));
    first.current = false;
  }, [version]);

  if (!data) return <div className="page muted">불러오는 중…</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h1>축제</h1>
        <span className="muted">{data.total}개</span>
      </div>
      {data.items.length === 0 && <div className="card muted">등록된 축제가 없어요. 상단의 "↺ 초기화"로 데모 데이터를 넣어 보세요.</div>}
      <div className="fest-list">
        {data.items.map((f) => (
          <button key={f.festival_id} className="fest-card" onClick={() => onSelect(f.festival_id)}>
            <div>
              <div className="eyebrow">FESTIVAL #{f.festival_id}</div>
              <h3>{f.name}</h3>
              <p className="muted">{f.venue} · {f.starts_on} ~ {f.ends_on}</p>
              {f.description && <p className="muted">{f.description}</p>}
            </div>
            <div className="fest-side">
              <span className={`pill ${f.status}`}>{STATUS_LABEL[f.status] || f.status}</span>
              <span className="go">예매하기 →</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
