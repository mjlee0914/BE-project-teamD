import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /v1 요청을 FastAPI로 넘긴다 → 백엔드에 CORS 설정이 필요 없음
// 백엔드 주소는 VITE_API_TARGET 환경변수로 바꿀 수 있다 (기본 localhost:8000)
// fs.allow : 오른쪽 코드 패널이 레포의 src/*.py 를 그대로 읽어 오기 위해 상위 폴더 접근 허용
const proxy = { "/v1": process.env.VITE_API_TARGET || "http://localhost:8000" };

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy,
    fs: { allow: [".."] },
  },
  // EC2 등에서 빌드본을 띄울 때(npm run preview)도 같은 프록시 사용
  preview: { port: 4173, host: true, proxy },
});
