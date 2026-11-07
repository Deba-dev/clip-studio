// Offline test of the licence server with a real SQLite database standing in for D1. Run: node test.mjs
import { DatabaseSync } from "node:sqlite";
import { createHmac } from "node:crypto";
import worker, { PLANS } from "./src/index.js";

const sqlite = new DatabaseSync(":memory:");
const statement = (sql, args = []) => ({
  bind: (...a) => statement(sql, a),
  first: async () => sqlite.prepare(sql).get(...args) ?? null,
  all: async () => ({ results: sqlite.prepare(sql).all(...args) }),
  run: async () => sqlite.prepare(sql).run(...args),
});
const DB = { prepare: (sql) => statement(sql), batch: async (list) => Promise.all(list.map((s) => s.run())) };

const env = {
  DB, BASE_URL: "https://cs.test", GOOGLE_CLIENT_ID: "gid", GOOGLE_CLIENT_SECRET: "gsec",
  RAZORPAY_KEY_ID: "rk", RAZORPAY_KEY_SECRET: "rs", RAZORPAY_WEBHOOK_SECRET: "rwh",
  RAZORPAY_PLAN_3M: "plan_3", RAZORPAY_PLAN_6M: "plan_6", RAZORPAY_PLAN_12M: "plan_12",
  PADDLE_CLIENT_TOKEN: "ptok", PADDLE_WEBHOOK_SECRET: "pwh",
  PADDLE_PRICE_3M: "pri_3", PADDLE_PRICE_6M: "pri_6", PADDLE_PRICE_12M: "pri_12", RESEND_API_KEY: "re",
  ADMIN_TOKEN: "admin-token-admin-token-123",
};

const mails = [];
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
globalThis.fetch = async (url, init = {}) => {
  const u = String(url);
  if (u.startsWith("https://oauth2.googleapis.com/token")) {
    return new Response(JSON.stringify({ id_token: "h." + b64({ aud: "gid", iss: "https://accounts.google.com", sub: "g-123",
      email: "drxshi@example.com", email_verified: true, name: "DRXSHI" }) + ".s" }));
  }
  if (u.startsWith("https://api.razorpay.com/v1/subscriptions")) return new Response(JSON.stringify({ id: "sub_R1" }));
  if (u.startsWith("https://api.resend.com")) { mails.push(JSON.parse(init.body)); return new Response("{}"); }
  throw new Error("unexpected fetch " + u);
};

let fails = 0;
const check = (ok, what) => { console.log((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; };
const call = (method, path, { body, headers = {}, token } = {}) => worker.fetch(new Request("https://cs.test" + path, {
  method, body: body === undefined ? undefined : (typeof body === "string" ? body : JSON.stringify(body)),
  headers: { ...headers, ...(token ? { authorization: "Bearer " + token } : {}) }, redirect: "manual",
}), env);

// plans
const plans = await (await call("GET", "/plans")).json();
check(plans.live && plans.india && plans.world, "billing is live once Google and both providers are configured");
check(plans.plans.find((p) => p.cycle === "12m").usd === 59.99 && PLANS["3m"].inr === 1699, "prices match the review page");
const off = await (await worker.fetch(new Request("https://cs.test/plans"), { DB })).json();
check(!off.live, "billing stays off with no keys, so the app locks nothing");

// sign-in
const start = await call("GET", "/login?port=50111&state=abcdefghijklmnop1234");
const google = new URL(start.headers.get("location"));
check(google.host === "accounts.google.com" && google.searchParams.get("scope") === "openid email profile",
  "sign-in asks Google only for email and profile");
const done = await call("GET", "/oauth/callback?code=c1&state=" + google.searchParams.get("state"));
const back = new URL(done.headers.get("location"));
check(back.host === "127.0.0.1:50111" && back.searchParams.get("state") === "abcdefghijklmnop1234", "the app gets its own state back");
const token = back.searchParams.get("token");
check(/^[0-9a-f]{64}$/.test(token), "the app receives a session token");
const replay = await call("GET", "/oauth/callback?code=c1&state=" + google.searchParams.get("state"));
check(replay.status === 400, "a sign-in link works only once");

const device = (id) => ({ "x-device-id": id, "x-device-name": "PC " + id });
let mine = await (await call("GET", "/me", { token, headers: device("A") })).json();
check(mine.plan === "free" && mine.email === "drxshi@example.com", "a new account is on the free plan");
check((await call("GET", "/me")).status === 401, "no token, no account");

// Razorpay: India
const link = await (await call("POST", "/buy-link", { token, body: { cycle: "6m", region: "in" } })).json();
const checkout = await (await call("GET", new URL(link.url).pathname + new URL(link.url).search)).text();
check(checkout.includes("sub_R1") && checkout.includes("₹2,999"), "India checkout opens Razorpay for ₹2,999 every 6 months");
const userId = sqlite.prepare("SELECT id FROM users").get().id;
const until = Math.floor(Date.now() / 1000) + 180 * 86400;
const rzpEvent = JSON.stringify({ event: "subscription.activated", payload: { subscription: { entity: {
  id: "sub_R1", plan_id: "plan_6", status: "active", current_end: until, notes: { user_id: userId } } } } });
const forged = await call("POST", "/webhooks/razorpay", { body: rzpEvent, headers: { "x-razorpay-signature": "00" } });
check(forged.status === 401, "a forged Razorpay webhook is refused");
const signed = createHmac("sha256", "rwh").update(rzpEvent).digest("hex");
check((await call("POST", "/webhooks/razorpay", { body: rzpEvent, headers: { "x-razorpay-signature": signed } })).ok,
  "a signed Razorpay webhook is accepted");
mine = await (await call("GET", "/me", { token, headers: device("A") })).json();
check(mine.plan === "premium" && mine.cycle === "6m" && mine.until === until, "Premium is on after Razorpay activates");
const key = sqlite.prepare("SELECT key FROM licence_keys").get()?.key;
check(/^CS(-[A-HJ-NP-Z2-9]{4}){4}$/.test(key || ""), "a licence key is made");
check(mails.length === 1 && mails[0].text.includes(key) && mails[0].to[0] === "drxshi@example.com", "the key is emailed");
await call("POST", "/webhooks/razorpay", { body: rzpEvent, headers: { "x-razorpay-signature": signed } });
check(sqlite.prepare("SELECT COUNT(*) n FROM licence_keys").get().n === 1 && mails.length === 1, "a repeated webhook makes no second key");

// two PCs
await call("GET", "/me", { token, headers: device("B") });
const third = await (await call("GET", "/me", { token, headers: device("C") })).json();
check(!third.device_ok && third.plan === "free" && third.devices.length === 2, "a third PC stays free while two hold Premium");
const freed = await (await call("POST", "/devices/remove", { token, body: { device_id: "B" }, headers: device("C") })).json();
check(freed.device_ok && freed.plan === "premium", "removing a PC frees a seat for this one");

// cancelling keeps Premium until the paid period ends
const cancel = JSON.stringify({ event: "subscription.cancelled", payload: { subscription: { entity: {
  id: "sub_R1", plan_id: "plan_6", status: "cancelled", current_end: until, notes: { user_id: userId } } } } });
await call("POST", "/webhooks/razorpay", { body: cancel, headers: { "x-razorpay-signature": createHmac("sha256", "rwh").update(cancel).digest("hex") } });
mine = await (await call("GET", "/me", { token, headers: device("A") })).json();
check(mine.plan === "premium" && mine.renews === false, "after cancelling, Premium lasts to the end of the period");

// Paddle: everywhere else, and a licence key used on a second Google account
const raw = JSON.stringify({ event_type: "subscription.activated", data: { id: "sub_P1", status: "active",
  items: [{ price: { id: "pri_12" } }], custom_data: { user_id: "u_other" },
  current_billing_period: { ends_at: new Date(Date.now() + 365 * 86400e3).toISOString() } } });
const ts = Math.floor(Date.now() / 1000);
const h1 = createHmac("sha256", "pwh").update(`${ts}:${raw}`).digest("hex");
check((await call("POST", "/webhooks/paddle", { body: raw, headers: { "paddle-signature": `ts=${ts};h1=${h1}` } })).ok,
  "a signed Paddle webhook is accepted");
check((await call("POST", "/webhooks/paddle", { body: raw, headers: { "paddle-signature": `ts=${ts};h1=bad` } })).status === 401,
  "a forged Paddle webhook is refused");
const paddleKey = sqlite.prepare("SELECT key FROM licence_keys WHERE subscription_id = 'pdl_sub_P1'").get().key;
const world = await (await call("POST", "/buy-link", { token, body: { cycle: "12m", region: "world" } })).json();
const page = await (await call("GET", new URL(world.url).pathname + new URL(world.url).search)).text();
check(page.includes("pri_12") && page.includes("$59.99"), "world checkout opens Paddle for $59.99 a year");
const activated = await (await call("POST", "/activate", { token, body: { key: paddleKey.toLowerCase() }, headers: device("A") })).json();
check(activated.plan === "premium" && activated.cycle === "12m", "a licence key moves Premium onto the signed-in account");
check((await call("POST", "/activate", { token, body: { key: "CS-NOPE" } })).status === 404, "an unknown key is refused");

// gift licences
const admin = { authorization: "Bearer admin-token-admin-token-123", "content-type": "application/json" };
check((await call("POST", "/admin/gift", { body: { cycle: "3m" } })).status === 403, "nobody makes gifts without the admin token");
const made = await (await call("POST", "/admin/gift", { body: { days: 30, note: "Thanks for testing", email: "fan@example.com" }, headers: admin })).json();
check(/^CS(-[A-HJ-NP-Z2-9]{4}){4}$/.test(made.key) && made.days === 30 && made.emailed, "a 30-day gift key is made and emailed");
check(mails.at(-1).to[0] === "fan@example.com" && mails.at(-1).text.includes(made.key), "the gift email carries the key");
let list = (await (await call("GET", "/admin/gifts", { headers: admin })).json()).gifts;
check(list.some((g) => g.key === made.key && g.status === "unused"), "an unused gift shows as unused");
const before = Math.floor(Date.now() / 1000);
const fan = await (await call("POST", "/activate", { token, body: { key: made.key }, headers: device("A") })).json();
check(fan.plan === "premium", "activating a gift turns Premium on");
const giftSub = sqlite.prepare("SELECT * FROM subscriptions WHERE provider = 'gift'").get();
check(giftSub.until >= before + 30 * 86400 && giftSub.until <= before + 30 * 86400 + 5, "the gift's 30 days start at activation");
const plan3 = await (await call("POST", "/admin/gift", { body: { cycle: "12m" }, headers: admin })).json();
check(plan3.days === 366, "a yearly gift is a full year");
await call("POST", "/admin/gift/revoke", { body: { key: plan3.key }, headers: admin });
check((await call("POST", "/activate", { token, body: { key: plan3.key } })).status === 410, "a cancelled gift cannot be used");
list = (await (await call("GET", "/admin/gifts", { headers: admin })).json()).gifts;
check(list.find((g) => g.key === made.key).used_by === "drxshi@example.com", "the gift list shows who used each key");

await call("POST", "/logout", { token });
check((await call("GET", "/me", { token })).status === 401, "signing out ends the session");

console.log(fails ? `\n${fails} FAILED` : "\nALL PASSED");
process.exit(fails ? 1 : 0);
