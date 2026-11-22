// A stand-in for Lenco's collections API, for end-to-end tests (no network, no real money).
// Uses Lenco's published sandbox numbers: 0961111111 / 0971111111 succeed, others fail.
// Run: node fake-lenco.mjs  (port 8090), then start Django with
//   LENCO_SANDBOX_API_URL=http://localhost:8090/access/v2
import { createServer } from "node:http";

const collections = new Map();
const SUCCEEDS = new Set(["0961111111", "0971111111", "0951111111"]);

function data(c, status) {
  return {
    id: `fake-${c.reference}`,
    amount: c.amount.toFixed(2),
    fee: "0.00",
    currency: "ZMW",
    reference: c.reference,
    lencoReference: `FAKE${collections.size}`,
    type: "mobile-money",
    status,
    reasonForFailure: status === "failed" ? "Not enough funds" : null,
    mobileMoneyDetails: { country: "zm", phone: c.phone, operator: c.operator },
  };
}

function send(res, code, body) {
  res.writeHead(code, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

createServer((req, res) => {
  let raw = "";
  req.on("data", (chunk) => (raw += chunk));
  req.on("end", () => {
    if (!req.headers.authorization?.startsWith("Bearer ")) return send(res, 401, { status: false, message: "Invalid token" });
    if (req.method === "POST" && req.url.endsWith("/collections/mobile-money")) {
      const c = JSON.parse(raw);
      c.checks = 0;
      collections.set(c.reference, c);
      return send(res, 200, { status: true, message: "", data: data(c, "pay-offline") });
    }
    const m = req.url.match(/\/collections\/status\/([^/?]+)/);
    if (req.method === "GET" && m) {
      const c = collections.get(decodeURIComponent(m[1]));
      if (!c) return send(res, 404, { status: false, message: "Collection not found" });
      c.checks += 1; // the customer "approves on the phone" before the second check
      const status = c.checks < 2 ? "pay-offline" : SUCCEEDS.has(c.phone) ? "successful" : "failed";
      return send(res, 200, { status: true, message: "", data: data(c, status) });
    }
    send(res, 404, { status: false, message: "Unknown path" });
  });
}).listen(8090, () => console.log("Fake Lenco on http://localhost:8090"));
