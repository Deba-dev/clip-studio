// Clip Studio licence server: Google sign-in for the app, Premium plans, Razorpay (India, rupees, UPI) and Paddle
// (everywhere else, dollars) checkouts, their webhooks, licence keys by email, and a two-PC limit.
//
// Billing is "live" only when Google sign-in and at least one payment provider are configured. Until then the app
// shows the plans but locks nothing, so a release can never take features away from people who have no way to pay.

export const PLANS = {
  "3m": { months: 3, name: "Every 3 months", inr: 1699, usd: 20.0 },
  "6m": { months: 6, name: "Every 6 months", inr: 2999, usd: 35.0 },
  "12m": { months: 12, name: "Yearly", inr: 4999, usd: 59.99 },
};
export const DEVICE_LIMIT = 2;
const SESSION_DAYS = 180;
const TICKET_MINUTES = 15;
const STATE_MINUTES = 10;
const ACTIVE = new Set(["active", "authenticated", "trialing", "past_due", "cancelled", "canceled", "pending"]);

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, google_sub TEXT UNIQUE, email TEXT, name TEXT, created INTEGER)`,
  `CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT, created INTEGER, last_seen INTEGER)`,
  `CREATE TABLE IF NOT EXISTS oauth_states (id TEXT PRIMARY KEY, app_state TEXT, port INTEGER, verifier TEXT, created INTEGER)`,
  `CREATE TABLE IF NOT EXISTS tickets (id TEXT PRIMARY KEY, user_id TEXT, cycle TEXT, region TEXT, created INTEGER)`,
  `CREATE TABLE IF NOT EXISTS subscriptions (id TEXT PRIMARY KEY, user_id TEXT, provider TEXT, cycle TEXT, status TEXT,
     until INTEGER, created INTEGER, updated INTEGER, days INTEGER DEFAULT 0)`,
  `CREATE TABLE IF NOT EXISTS licence_keys (key TEXT PRIMARY KEY, subscription_id TEXT, email TEXT, created INTEGER,
     note TEXT DEFAULT '')`,
  `CREATE TABLE IF NOT EXISTS devices (user_id TEXT, device_id TEXT, name TEXT, last_seen INTEGER,
     PRIMARY KEY (user_id, device_id))`,
];

let ready = null;
async function db(env) {
  if (!ready) ready = env.DB.batch(SCHEMA.map((s) => env.DB.prepare(s))).catch((e) => { ready = null; throw e; });
  await ready;
  return env.DB;
}

const now = () => Math.floor(Date.now() / 1000);
const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function random(bytes = 32) {
  return Array.from(crypto.getRandomValues(new Uint8Array(bytes)), (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sha256(text) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function hmacHex(secret, text) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(text));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

function sameText(a, b) {          // constant time, so a signature cannot be guessed byte by byte
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function licenceKey() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";       // no 0/O or 1/I, so keys can be read aloud
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const chars = Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
  return "CS-" + chars.match(/.{4}/g).join("-");
}

export function billing(env) {
  const google = Boolean(env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET);
  const razorpay = Boolean(env.RAZORPAY_KEY_ID && env.RAZORPAY_KEY_SECRET && env.RAZORPAY_WEBHOOK_SECRET &&
    Object.keys(PLANS).every((c) => env["RAZORPAY_PLAN_" + c.toUpperCase()]));
  const paddle = Boolean(env.PADDLE_CLIENT_TOKEN && env.PADDLE_WEBHOOK_SECRET &&
    Object.keys(PLANS).every((c) => env["PADDLE_PRICE_" + c.toUpperCase()]));
  return { google, razorpay, paddle, live: google && (razorpay || paddle) };
}

function base(env, request) {
  return env.BASE_URL || new URL(request.url).origin;
}

// ---- accounts
async function userFor(env, request) {
  const auth = request.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!/^[0-9a-f]{64}$/.test(token)) return null;
  const d = await db(env);
  const row = await d.prepare(`SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
                               WHERE s.token_hash = ? AND s.created > ?`)
    .bind(await sha256(token), now() - SESSION_DAYS * 86400).first();
  if (row) await d.prepare("UPDATE sessions SET last_seen = ? WHERE token_hash = ?").bind(now(), await sha256(token)).run();
  return row || null;
}

export async function entitlement(env, userId) {
  const d = await db(env);
  const subs = (await d.prepare("SELECT * FROM subscriptions WHERE user_id = ? ORDER BY until DESC").bind(userId).all()).results || [];
  const best = subs.find((s) => ACTIVE.has(s.status) && s.until > now());
  return best
    ? { plan: "premium", until: best.until, cycle: best.cycle, provider: best.provider, renews: !/cancel/.test(best.status) }
    : { plan: "free", until: 0, cycle: "", provider: "", renews: false };
}

async function me(env, request, user) {
  const d = await db(env);
  const deviceId = (request.headers.get("x-device-id") || "").slice(0, 64);
  const deviceName = (request.headers.get("x-device-name") || "PC").slice(0, 60);
  const ent = await entitlement(env, user.id);
  let devices = (await d.prepare("SELECT device_id, name, last_seen FROM devices WHERE user_id = ? ORDER BY last_seen DESC")
    .bind(user.id).all()).results || [];
  let deviceOk = true;
  if (deviceId) {
    const known = devices.some((x) => x.device_id === deviceId);
    if (known || ent.plan !== "premium" || devices.length < DEVICE_LIMIT) {
      await d.prepare(`INSERT INTO devices (user_id, device_id, name, last_seen) VALUES (?, ?, ?, ?)
                       ON CONFLICT (user_id, device_id) DO UPDATE SET name = excluded.name, last_seen = excluded.last_seen`)
        .bind(user.id, deviceId, deviceName, now()).run();
      if (!known) devices = [{ device_id: deviceId, name: deviceName, last_seen: now() }, ...devices];
    } else {
      deviceOk = false;      // Premium is already on two other PCs: this one stays free until one is removed
    }
  }
  return json({
    email: user.email, name: user.name, ...ent, plan: deviceOk ? ent.plan : "free", device_ok: deviceOk,
    device_limit: DEVICE_LIMIT, devices, billing: billing(env).live,
  });
}

// ---- Google sign-in (openid email profile: no Google verification needed for these scopes)
async function login(env, request) {
  const url = new URL(request.url);
  const port = Number(url.searchParams.get("port"));
  const appState = url.searchParams.get("state") || "";
  if (!Number.isInteger(port) || port < 1024 || port > 65535 || !/^[A-Za-z0-9_-]{16,80}$/.test(appState)) {
    return page("Sign-in link is broken", "<p>Start signing in again from Clip Studio.</p>", 400);
  }
  if (!billing(env).google) return page("Sign-in is not set up yet", "<p>Google sign-in is not configured on the server.</p>", 503);
  const id = random(16), verifier = random(32);
  const d = await db(env);
  await d.prepare("DELETE FROM oauth_states WHERE created < ?").bind(now() - STATE_MINUTES * 60).run();
  await d.prepare("INSERT INTO oauth_states (id, app_state, port, verifier, created) VALUES (?, ?, ?, ?, ?)")
    .bind(id, appState, port, verifier, now()).run();
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const auth = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  auth.search = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID, redirect_uri: base(env, request) + "/oauth/callback", response_type: "code",
    scope: "openid email profile", state: id, code_challenge: challenge, code_challenge_method: "S256",
    prompt: "select_account",
  }).toString();
  return Response.redirect(auth.toString(), 302);
}

function claims(idToken) {
  const part = (idToken || "").split(".")[1] || "";
  const text = atob(part.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((part.length + 3) % 4));
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(text, (c) => c.charCodeAt(0))));
}

async function callback(env, request) {
  const url = new URL(request.url);
  const d = await db(env);
  const state = await d.prepare("SELECT * FROM oauth_states WHERE id = ? AND created > ?")
    .bind(url.searchParams.get("state") || "", now() - STATE_MINUTES * 60).first();
  if (!state) return page("Sign-in expired", "<p>Start signing in again from Clip Studio.</p>", 400);
  await d.prepare("DELETE FROM oauth_states WHERE id = ?").bind(state.id).run();
  const back = (params) => Response.redirect(`http://127.0.0.1:${state.port}/done?` + new URLSearchParams(
    { state: state.app_state, ...params }).toString(), 302);
  if (!url.searchParams.get("code")) return back({ error: url.searchParams.get("error") || "cancelled" });
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code: url.searchParams.get("code"), client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: base(env, request) + "/oauth/callback", grant_type: "authorization_code", code_verifier: state.verifier,
    }),
  });
  const tok = await res.json().catch(() => ({}));
  let c = {};
  try { c = claims(tok.id_token); } catch { c = {}; }
  // The token came straight from Google over TLS in exchange for our own code, so its claims can be trusted once
  // they are for this app.
  if (!res.ok || c.aud !== env.GOOGLE_CLIENT_ID || !/accounts\.google\.com$/.test(c.iss || "") || !c.sub || !c.email_verified) {
    return back({ error: "google" });
  }
  let user = await d.prepare("SELECT * FROM users WHERE google_sub = ?").bind(c.sub).first();
  if (!user) {
    user = { id: "u_" + random(12), google_sub: c.sub, email: c.email, name: c.name || "", created: now() };
    await d.prepare("INSERT INTO users (id, google_sub, email, name, created) VALUES (?, ?, ?, ?, ?)")
      .bind(user.id, user.google_sub, user.email, user.name, user.created).run();
  } else {
    await d.prepare("UPDATE users SET email = ?, name = ? WHERE id = ?").bind(c.email, c.name || "", user.id).run();
  }
  const token = random(32);
  await d.prepare("INSERT INTO sessions (token_hash, user_id, created, last_seen) VALUES (?, ?, ?, ?)")
    .bind(await sha256(token), user.id, now(), now()).run();
  return back({ token });
}

// ---- checkout
async function buyLink(env, request, user) {
  const body = await request.json().catch(() => ({}));
  const cycle = PLANS[body.cycle] ? body.cycle : "12m";
  const region = body.region === "in" ? "in" : "world";
  const b = billing(env);
  if (!(region === "in" ? b.razorpay : b.paddle)) return json({ error: "That payment option is not available yet." }, 503);
  const id = random(16);
  const d = await db(env);
  await d.prepare("DELETE FROM tickets WHERE created < ?").bind(now() - TICKET_MINUTES * 60).run();
  await d.prepare("INSERT INTO tickets (id, user_id, cycle, region, created) VALUES (?, ?, ?, ?, ?)")
    .bind(id, user.id, cycle, region, now()).run();
  return json({ url: base(env, request) + "/buy?ticket=" + id });
}

async function buy(env, request) {
  const d = await db(env);
  const ticket = await d.prepare("SELECT t.*, u.email, u.name FROM tickets t JOIN users u ON u.id = t.user_id WHERE t.id = ? AND t.created > ?")
    .bind(new URL(request.url).searchParams.get("ticket") || "", now() - TICKET_MINUTES * 60).first();
  if (!ticket) return page("This checkout link has expired", "<p>Open the plans again in Clip Studio and pick a plan.</p>", 400);
  const plan = PLANS[ticket.cycle];
  const thanks = base(env, request) + "/thanks";
  if (ticket.region === "in") {
    const res = await fetch("https://api.razorpay.com/v1/subscriptions", {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Basic " + btoa(env.RAZORPAY_KEY_ID + ":" + env.RAZORPAY_KEY_SECRET) },
      body: JSON.stringify({ plan_id: env["RAZORPAY_PLAN_" + ticket.cycle.toUpperCase()], total_count: Math.ceil(120 / plan.months),
        customer_notify: 1, notes: { user_id: ticket.user_id, cycle: ticket.cycle } }),
    });
    const sub = await res.json().catch(() => ({}));
    if (!res.ok || !sub.id) return page("Checkout could not start", "<p>Razorpay did not answer. Please try again in a minute.</p>", 502);
    const options = { key: env.RAZORPAY_KEY_ID, subscription_id: sub.id, name: "Clip Studio Premium",
      description: plan.name + " · ₹" + plan.inr.toLocaleString("en-IN"), prefill: { email: ticket.email, name: ticket.name },
      theme: { color: "#a855f7" } };
    return page("Clip Studio Premium", `<p>${esc(plan.name)} · <b>₹${plan.inr.toLocaleString("en-IN")}</b>, renews automatically. Cancel any time.</p>
      <button id="pay">Pay with UPI, card or netbanking</button>
      <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
      <script>const o = ${JSON.stringify(options)}; o.handler = () => location.href = ${JSON.stringify(thanks)};
      const go = () => new Razorpay(o).open(); document.getElementById("pay").onclick = go; go();</script>`);
  }
  const env_ = env.PADDLE_ENV === "sandbox" ? "Paddle.Environment.set('sandbox');" : "";
  const checkout = { items: [{ priceId: env["PADDLE_PRICE_" + ticket.cycle.toUpperCase()], quantity: 1 }],
    customer: { email: ticket.email }, customData: { user_id: ticket.user_id, cycle: ticket.cycle },
    settings: { successUrl: thanks, displayMode: "overlay", theme: "dark" } };
  return page("Clip Studio Premium", `<p>${esc(plan.name)} · <b>$${plan.usd.toFixed(2)}</b>, renews automatically. Cancel any time.</p>
    <button id="pay">Pay by card or PayPal</button>
    <script src="https://cdn.paddle.com/paddle/v2/paddle.js"></script>
    <script>${env_} Paddle.Initialize({ token: ${JSON.stringify(env.PADDLE_CLIENT_TOKEN)} });
    const go = () => Paddle.Checkout.open(${JSON.stringify(checkout)}); document.getElementById("pay").onclick = go; go();</script>`);
}

// ---- payment webhooks
async function saveSubscription(env, sub) {
  const d = await db(env);
  const old = await d.prepare("SELECT * FROM subscriptions WHERE id = ?").bind(sub.id).first();
  if (old) {
    await d.prepare("UPDATE subscriptions SET status = ?, until = ?, cycle = COALESCE(NULLIF(?, ''), cycle), updated = ? WHERE id = ?")
      .bind(sub.status, sub.until || old.until, sub.cycle || "", now(), sub.id).run();
  } else {
    await d.prepare(`INSERT INTO subscriptions (id, user_id, provider, cycle, status, until, created, updated)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(sub.id, sub.user_id || null, sub.provider, sub.cycle || "", sub.status, sub.until || 0, now(), now()).run();
  }
  if (ACTIVE.has(sub.status) && sub.until > now()) await issueKey(env, sub.id);
}

async function issueKey(env, subscriptionId) {
  const d = await db(env);
  if (await d.prepare("SELECT key FROM licence_keys WHERE subscription_id = ?").bind(subscriptionId).first()) return;
  const owner = await d.prepare("SELECT u.email, u.name FROM subscriptions s JOIN users u ON u.id = s.user_id WHERE s.id = ?")
    .bind(subscriptionId).first();
  const key = licenceKey();
  await d.prepare("INSERT INTO licence_keys (key, subscription_id, email, created) VALUES (?, ?, ?, ?)")
    .bind(key, subscriptionId, owner?.email || "", now()).run();
  if (owner?.email && env.RESEND_API_KEY) {
    await fetch("https://api.resend.com/emails", {
      method: "POST", headers: { "content-type": "application/json", authorization: "Bearer " + env.RESEND_API_KEY },
      body: JSON.stringify({ from: env.MAIL_FROM || "Clip Studio <premium@zunimilabs.online>", to: [owner.email],
        subject: "Your Clip Studio Premium licence key",
        text: `Hi${owner.name ? " " + owner.name : ""},\n\nThanks for getting Clip Studio Premium. It is already on for the Google account ` +
          `you signed in with. Your licence key, in case you ever need it on another account:\n\n    ${key}\n\n` +
          `In Clip Studio, open Settings > Premium and choose "Use a licence key".\n\nZunimiLabs` }),
    }).catch(() => {});
  }
}

const CYCLE_FROM_MONTHS = { 3: "3m", 6: "6m", 12: "12m" };

async function razorpayHook(env, request) {
  const raw = await request.text();
  const want = await hmacHex(env.RAZORPAY_WEBHOOK_SECRET || "", raw);
  if (!env.RAZORPAY_WEBHOOK_SECRET || !sameText(want, request.headers.get("x-razorpay-signature") || "")) {
    return json({ error: "bad signature" }, 401);
  }
  const event = JSON.parse(raw);
  const s = event.payload?.subscription?.entity;
  if (!s?.id) return json({ ok: true, ignored: event.event });
  const cycle = Object.keys(PLANS).find((c) => env["RAZORPAY_PLAN_" + c.toUpperCase()] === s.plan_id) || s.notes?.cycle || "";
  const status = { "subscription.cancelled": "cancelled", "subscription.halted": "halted", "subscription.completed": "completed",
    "subscription.paused": "paused" }[event.event] || s.status || "active";
  await saveSubscription(env, { id: "rzp_" + s.id, user_id: s.notes?.user_id, provider: "razorpay", cycle, status,
    until: Number(s.current_end) || 0 });
  return json({ ok: true });
}

async function paddleHook(env, request) {
  const raw = await request.text();
  const header = Object.fromEntries((request.headers.get("paddle-signature") || "").split(";").map((p) => p.split("=")));
  const want = await hmacHex(env.PADDLE_WEBHOOK_SECRET || "", `${header.ts}:${raw}`);
  if (!env.PADDLE_WEBHOOK_SECRET || !header.ts || !sameText(want, header.h1 || "") || Math.abs(now() - Number(header.ts)) > 300) {
    return json({ error: "bad signature" }, 401);
  }
  const event = JSON.parse(raw);
  if (!String(event.event_type || "").startsWith("subscription.")) return json({ ok: true, ignored: event.event_type });
  const s = event.data || {};
  const price = s.items?.[0]?.price?.id;
  const cycle = Object.keys(PLANS).find((c) => env["PADDLE_PRICE_" + c.toUpperCase()] === price) || s.custom_data?.cycle || "";
  const ends = s.current_billing_period?.ends_at || s.scheduled_change?.effective_at;
  const until = ends ? Math.floor(Date.parse(ends) / 1000) : (s.status === "canceled" ? now() : 0);
  await saveSubscription(env, { id: "pdl_" + s.id, user_id: s.custom_data?.user_id, provider: "paddle", cycle,
    status: s.status || "active", until });
  return json({ ok: true });
}

// ---- gift licences, made by the owner with the ADMIN_TOKEN secret (see gift.mjs)
function admin(env, request) {
  const token = (request.headers.get("authorization") || "").replace(/^Bearer /, "");
  return Boolean(env.ADMIN_TOKEN) && env.ADMIN_TOKEN.length >= 24 && sameText(token, env.ADMIN_TOKEN);
}

async function gift(env, request) {
  const body = await request.json().catch(() => ({}));
  const days = PLANS[body.cycle] ? PLANS[body.cycle].months * 30 + Math.floor(PLANS[body.cycle].months / 2)
    : Math.round(Number(body.days));
  if (!Number.isInteger(days) || days < 1 || days > 3660) return json({ error: "Give a plan (3m, 6m, 12m) or 1 to 3660 days." }, 400);
  const d = await db(env);
  const id = "gift_" + random(8);
  // The gift's time starts when someone activates it, not when it is made, so a key sent late loses nothing.
  await d.prepare(`INSERT INTO subscriptions (id, user_id, provider, cycle, status, until, created, updated, days)
                   VALUES (?, NULL, 'gift', ?, 'unused', 0, ?, ?, ?)`)
    .bind(id, PLANS[body.cycle] ? body.cycle : "", now(), now(), days).run();
  const key = licenceKey();
  const note = String(body.note || "").slice(0, 200);
  await d.prepare("INSERT INTO licence_keys (key, subscription_id, email, created, note) VALUES (?, ?, ?, ?, ?)")
    .bind(key, id, String(body.email || "").slice(0, 200), now(), note).run();
  if (body.email && env.RESEND_API_KEY) {
    await fetch("https://api.resend.com/emails", {
      method: "POST", headers: { "content-type": "application/json", authorization: "Bearer " + env.RESEND_API_KEY },
      body: JSON.stringify({ from: env.MAIL_FROM || "Clip Studio <premium@zunimilabs.online>", to: [body.email],
        subject: "A gift: Clip Studio Premium",
        text: `You have been given ${days} days of Clip Studio Premium.\n\nYour licence key:\n\n    ${key}\n\n` +
          `In Clip Studio, sign in, open Settings > Premium and choose "Use a licence key". The ${days} days start ` +
          `when you activate it.${note ? "\n\n" + note : ""}\n\nZunimiLabs` }),
    }).catch(() => {});
  }
  return json({ key, days, note, emailed: Boolean(body.email && env.RESEND_API_KEY) });
}

async function gifts(env) {
  const rows = (await (await db(env)).prepare(`SELECT k.key, k.note, k.email, k.created, s.days, s.status, s.until, u.email AS used_by
      FROM licence_keys k JOIN subscriptions s ON s.id = k.subscription_id LEFT JOIN users u ON u.id = s.user_id
      WHERE s.provider = 'gift' ORDER BY k.created DESC`).all()).results || [];
  return json({ gifts: rows });
}

async function revokeGift(env, request) {
  const body = await request.json().catch(() => ({}));
  const d = await db(env);
  const row = await d.prepare(`SELECT s.id FROM licence_keys k JOIN subscriptions s ON s.id = k.subscription_id
                               WHERE k.key = ? AND s.provider = 'gift'`).bind(String(body.key || "").toUpperCase()).first();
  if (!row) return json({ error: "No gift with that key." }, 404);
  await d.prepare("UPDATE subscriptions SET status = 'revoked', until = ?, updated = ? WHERE id = ?").bind(now(), now(), row.id).run();
  return json({ ok: true });
}

// ---- small pages
function page(title, body, status = 200) {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title><style>
:root{color-scheme:dark}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0820;color:#f3f0ff;
font:16px/1.6 "Segoe UI",system-ui,sans-serif;padding:24px}main{max-width:460px;display:grid;gap:12px;text-align:center}
h1{font-size:26px;margin:0}button{font:600 16px inherit;background:#a855f7;color:#fff;border:0;border-radius:12px;
padding:12px 20px;cursor:pointer}p{margin:0;color:#c9c2ee}</style></head><body><main><h1>${esc(title)}</h1>${body}</main></body></html>`,
  { status, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const route = `${request.method} ${url.pathname}`;
    try {
      if (route === "GET /plans") {
        const b = billing(env);
        return json({ live: b.live, sign_in: b.google, india: b.razorpay, world: b.paddle, device_limit: DEVICE_LIMIT,
          plans: Object.entries(PLANS).map(([cycle, p]) => ({ cycle, ...p })) });
      }
      if (route === "GET /login") return login(env, request);
      if (route === "GET /oauth/callback") return callback(env, request);
      if (route === "GET /buy") return buy(env, request);
      if (route === "GET /thanks") {
        return page("Thank you", "<p>Payment received. Premium turns on in Clip Studio within a minute, and your licence key is on its way by email.</p><p>You can close this tab.</p>");
      }
      if (route === "POST /webhooks/razorpay") return razorpayHook(env, request);
      if (route === "POST /webhooks/paddle") return paddleHook(env, request);
      if (url.pathname.startsWith("/admin/")) {
        if (!admin(env, request)) return json({ error: "not allowed" }, 403);
        if (route === "POST /admin/gift") return gift(env, request);
        if (route === "GET /admin/gifts") return gifts(env);
        if (route === "POST /admin/gift/revoke") return revokeGift(env, request);
        return json({ error: "not found" }, 404);
      }
      const user = await userFor(env, request);
      if (!user) return json({ error: "Sign in again." }, 401);
      if (route === "GET /me") return me(env, request, user);
      if (route === "POST /buy-link") return buyLink(env, request, user);
      if (route === "POST /logout") {
        const token = (request.headers.get("authorization") || "").slice(7).trim();
        await (await db(env)).prepare("DELETE FROM sessions WHERE token_hash = ?").bind(await sha256(token)).run();
        return json({ ok: true });
      }
      if (route === "POST /devices/remove") {
        const body = await request.json().catch(() => ({}));
        await (await db(env)).prepare("DELETE FROM devices WHERE user_id = ? AND device_id = ?").bind(user.id, String(body.device_id || "")).run();
        return me(env, request, user);
      }
      if (route === "POST /activate") {
        const body = await request.json().catch(() => ({}));
        const key = String(body.key || "").trim().toUpperCase();
        const d = await db(env);
        const row = await d.prepare("SELECT * FROM licence_keys WHERE key = ?").bind(key).first();
        if (!row) return json({ error: "That licence key was not found. Check it and try again." }, 404);
        const sub = await d.prepare("SELECT * FROM subscriptions WHERE id = ?").bind(row.subscription_id).first();
        if (sub.status === "revoked") return json({ error: "That licence key has been cancelled." }, 410);
        if (sub.provider === "gift" && sub.status === "unused") {
          await d.prepare("UPDATE subscriptions SET user_id = ?, status = 'active', until = ?, updated = ? WHERE id = ?")
            .bind(user.id, now() + sub.days * 86400, now(), sub.id).run();
        } else if (sub.provider === "gift" && sub.user_id && sub.user_id !== user.id) {
          return json({ error: "That gift key is already used on another account." }, 409);
        } else {
          await d.prepare("UPDATE subscriptions SET user_id = ? WHERE id = ?").bind(user.id, row.subscription_id).run();
        }
        return me(env, request, user);
      }
      return json({ error: "not found" }, 404);
    } catch (e) {
      return json({ error: "Something went wrong on the server. Try again in a minute." }, 500);
    }
  },
};
