// 한 step의 코드 조각을 Shiki로 하이라이트하고, 현재 줄을 강조한다
import { useEffect, useRef, useState } from "react";
import { createHighlighter } from "shiki";
import { loadSource, locate } from "./sourceLoader";

let highlighterPromise = null;
function getHighlighter() {
  highlighterPromise ??= createHighlighter({ themes: ["github-dark-default"], langs: ["python"] });
  return highlighterPromise;
}

export default function CodeView({ step, tone }) {
  const [view, setView] = useState(null);
  const boxRef = useRef(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const src = await loadSource(step.file);
      if (!src || !alive) return;
      const { start, end, highlight, lines } = locate(src, step.symbol, step.anchor);
      const hl = await getHighlighter();
      const slice = lines.slice(start, end + 1).join("\n");
      const { tokens } = hl.codeToTokens(slice, { lang: "python", theme: "github-dark-default" });
      if (alive) setView({ start, highlight, tokens });
    })();
    return () => {
      alive = false;
    };
  }, [step.file, step.symbol, step.anchor]);

  // 강조 줄이 보이도록 스크롤
  useEffect(() => {
    const el = boxRef.current?.querySelector(".line.hl");
    if (el && boxRef.current) {
      const box = boxRef.current;
      box.scrollTo({ top: el.offsetTop - box.clientHeight / 2 + el.clientHeight, behavior: "smooth" });
    }
  }, [view]);

  if (!view) return <div className="code-box loading">코드 불러오는 중…</div>;

  return (
    <div className="code-box" ref={boxRef}>
      {view.tokens.map((line, i) => {
        const no = view.start + i;
        const isHl = no === view.highlight;
        return (
          <div key={no} className={`line ${isHl ? `hl ${tone}` : ""}`}>
            <span className="ln">{no + 1}</span>
            <span className="code">
              {line.length === 0 ? " " : line.map((t, j) => (
                <span key={j} style={{ color: t.color }}>{t.content}</span>
              ))}
            </span>
          </div>
        );
      })}
    </div>
  );
}
