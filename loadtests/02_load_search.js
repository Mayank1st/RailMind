import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
stages: [
    { duration: '30s', target: 50 },   // 30s mein 0 → 50 users (ramp-up)
    { duration: '30s', target: 50 },   // 30s tak 50 pe hold
    { duration: '30s', target: 200 },  // 30s mein 50 → 200 (aur chadho)
    { duration: '15s', target: 0 },    // wapas 0 (ramp-down)
    ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = 'http://localhost:8000/api/v1';

// Dynamic date: hamesha "kal" ki date — script kabhi purani nahi hogi.
// Init context mein ek baar compute hota hai, har iteration mein nahi.
const journeyDate = new Date(Date.now() + 24 * 60 * 60 * 1000)
  .toISOString()
  .slice(0, 10); // "YYYY-MM-DD"

const body = {
  fromStationCode: 'NDLS',
  toStationCode: 'BCT',
  journey_date: journeyDate,
  train_class: 'SL',
  quota: 'GN',
  nearby_stations: false,
  flexible_dates: false,
};

export default function () {
  const res = http.post(`${BASE_URL}/train/search`, JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
  });

  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
    'trains found': (r) => r.status === 200 && r.json('meta.total') > 0,
  });

//   sleep(1);
}
