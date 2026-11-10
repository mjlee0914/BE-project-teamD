import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /v1, /demo 요청을 FastAPI(8000)로 넘긴다 → 백엔드에 CORS 설정이 필요 없음
// fs.allow : 오른쪽 코드 패널이 레포의 src/*.py 를 그대로 읽어 오기 위해 상위 폴더 접근 허용
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": "http://localhost:8000",
      // "/demo"로 쓰면 코드 패널이 읽는 /demo_backend/*.py 까지 백엔드로 넘어가므로 "/demo/"로 한정
      "/demo/": "http://localhost:8000",
    },
    fs: { allow: [".."] },
  },
});
