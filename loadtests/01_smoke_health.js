import http from 'k6/http';
import { check, sleep } from 'k6';

// ---- Test configuration ----
// k6 isko padh ke decide karta hai kitne virtual users (VUs) kitni der chalane hain
export const options = {
  vus: 50,          // 10 virtual users — 10 concurrent "nakli users"
  duration: '15s',  // 15 second tak test chalega
};

const BASE_URL = 'http://localhost:8000/api/v1';

// ---- Default function ----
// Har VU is function ko loop mein baar-baar chalata hai, duration khatam hone tak.
// Ek iteration = ek "user action".
export default function () {
  const res = http.get(`${BASE_URL}/health-check/health-check-status`);

  // check() = assertion. Fail hone pe test nahi rukta,
  // bas "checks" metric mein failure count hota hai.
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });

  // Har request ke beech 1 second ka pause — real user behaviour simulate karta hai.
  // Iske bina VUs full speed pe hammer karenge (wo stress test ke liye hota hai).
  // sleep(1);
}
