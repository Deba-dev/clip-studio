// Gift licences for Clip Studio Premium. The person signs in to Clip Studio and enters the key under
// Settings > Premium > Use a licence key; the gift's time starts when they do.
//
//   node gift.mjs new 3m                              a 3-month gift (also 6m, 12m)
//   node gift.mjs new 30 --note "Thanks for testing"  any number of days, with a note
//   node gift.mjs new 12m --email friend@example.com   also emails the key (needs RESEND_API_KEY on the server)
//   node gift.mjs list                                every gift: unused, active, or cancelled, and who used it
//   node gift.mjs revoke CS-ABCD-EFGH-JKLM-NPQR        cancels a gift, used or not
//
// The admin token is read from the CLIPSTUDIO_ADMIN_TOKEN environment variable or from a file named .admin-token
// next to this script. Keep it private: anyone with it can make Premium keys.
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const API = process.env.CLIPSTUDIO_API || "https://clipstudio.zunimilabs.online";
const tokenFile = join(dirname(fileURLToPath(import.meta.url)), ".admin-token");
const token = process.env.CLIPSTUDIO_ADMIN_TOKEN || (existsSync(tokenFile) ? readFileSync(tokenFile, "utf8").trim() : "");
const [command, value, ...rest] = process.argv.slice(2);
const flag = (name) => { const i = rest.indexOf("--" + name); return i >= 0 ? rest[i + 1] : undefined; };

if (!token) {
  console.error("No admin token. Put it in CLIPSTUDIO_ADMIN_TOKEN or in server/.admin-token");
  process.exit(1);
}

async function call(method, path, body) {
  const res = await fetch(API + path, { method, headers: { authorization: "Bearer " + token, "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { console.error(data.error || `The server answered ${res.status}.`); process.exit(1); }
  return data;
}

const day = (t) => (t ? new Date(t * 1000).toISOString().slice(0, 10) : "");

if (command === "new" && value) {
  const plan = ["3m", "6m", "12m"].includes(value) ? { cycle: value } : { days: Number(value) };
  const made = await call("POST", "/admin/gift", { ...plan, note: flag("note") || "", email: flag("email") || "" });
  console.log(`\n  ${made.key}\n\n  ${made.days} days of Premium, starting when it is activated.` +
    (made.emailed ? `\n  Emailed to ${flag("email")}.` : "") + "\n");
} else if (command === "list") {
  const { gifts } = await call("GET", "/admin/gifts");
  if (!gifts.length) console.log("No gifts yet.");
  for (const g of gifts) {
    const state = g.status === "unused" ? "unused" : g.status === "revoked" ? "cancelled"
      : `used by ${g.used_by || "?"}, Premium until ${day(g.until)}`;
    console.log(`${g.key}  ${String(g.days).padStart(4)} days  made ${day(g.created)}  ${state}${g.note ? "  · " + g.note : ""}`);
  }
} else if (command === "revoke" && value) {
  await call("POST", "/admin/gift/revoke", { key: value });
  console.log(`Cancelled ${value.toUpperCase()}. Its Premium ends now.`);
} else {
  console.log("Usage: node gift.mjs new <3m|6m|12m|days> [--note text] [--email address] | list | revoke <key>");
}
