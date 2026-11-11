// 백엔드 파이썬 소스를 빌드 시점에 그대로 읽어 온다 (항상 실제 코드가 보이게)
// 키 : 레포 루트 기준 경로 ("src/reservations/application/service.py")

const rawModules = import.meta.glob("../../../src/**/*.py", { query: "?raw", import: "default" });

const loaders = {};
for (const [p, loader] of Object.entries(rawModules)) {
  const key = p.replace("../../../", "");
  loaders[key] = loader;
}

const cache = {};
export async function loadSource(file) {
  if (cache[file]) return cache[file];
  const loader = loaders[file];
  if (!loader) {
    console.warn("[trace] 소스 없음:", file);
    return null;
  }
  cache[file] = await loader();
  return cache[file];
}

const indentOf = (line) => line.match(/^\s*/)[0].length;

// "Class.method" / "function" 위치 찾기 → { start, end, highlight } (0부터 시작하는 줄 번호)
export function locate(source, symbol, anchor) {
  const lines = source.split("\n");
  const parts = symbol.split(".");
  const fnName = parts[parts.length - 1];
  let from = 0;

  if (parts.length === 2) {
    const ci = lines.findIndex((l) => new RegExp(`^\\s*class\\s+${parts[0]}\\b`).test(l));
    if (ci >= 0) from = ci;
  }

  const defRe = new RegExp(`^\\s*(async\\s+)?def\\s+${fnName}\\s*\\(`);
  let defLine = -1;
  for (let i = from; i < lines.length; i++) {
    if (defRe.test(lines[i])) {
      defLine = i;
      break;
    }
  }
  if (defLine < 0) {
    console.warn("[trace] 함수 없음:", symbol);
    return { start: 0, end: Math.min(lines.length - 1, 20), highlight: 0, lines };
  }

  // 위쪽 데코레이터·주석까지 포함
  let start = defLine;
  while (start > 0 && /^\s*(@|#)/.test(lines[start - 1])) start--;

  // 함수 끝 : def보다 들여쓰기가 같거나 작은 첫 코드 줄 직전
  // 시그니처가 여러 줄일 수 있음 → ":"로 끝나는 줄(주석 제외)까지가 시그니처
  const base = indentOf(lines[defLine]);
  let sigEnd = defLine;
  while (sigEnd < lines.length - 1 && !/:\s*$/.test(lines[sigEnd].replace(/#.*$/, ""))) sigEnd++;

  let end = lines.length - 1;
  for (let i = sigEnd + 1; i < lines.length; i++) {
    const l = lines[i];
    if (!l.trim()) continue;
    if (indentOf(l) <= base) {
      end = i - 1;
      break;
    }
  }
  // 다음 함수 위의 주석·데코레이터는 제외
  while (end > defLine && (!lines[end].trim() || (indentOf(lines[end]) <= base && /^\s*(#|@)/.test(lines[end])))) end--;
  while (end > defLine && !lines[end].trim()) end--;

  let highlight = defLine;
  if (anchor) {
    for (let i = defLine; i <= end; i++) {
      if (lines[i].includes(anchor)) {
        highlight = i;
        break;
      }
    }
    if (highlight === defLine && !lines[defLine].includes(anchor)) {
      console.warn("[trace] anchor 없음:", symbol, anchor);
    }
  }
  return { start, end, highlight, lines };
}
