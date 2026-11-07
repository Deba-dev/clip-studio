# Clip Studio licence server

A Cloudflare Worker at `https://clipstudio.zunimilabs.online`. It signs people in with Google, sells Premium through
Razorpay (India, rupees, UPI autopay) and Paddle (everywhere else, dollars), emails licence keys, limits Premium to
2 PCs, and makes gift keys.

**Billing stays off until Google sign-in and at least one payment provider are set up.** While it is off, the app
shows "Premium is coming soon" and every feature stays free, so the app can ship before payments are ready.

| Plan | India (Razorpay) | Everywhere else (Paddle) |
|---|---|---|
| Every 3 months | ₹1,699 | $20.00 |
| Every 6 months | ₹2,999 | $35.00 |
| Yearly | ₹4,999 | $59.99 |

Prices live in `src/index.js` (`PLANS`) and in the app (`clipstudio/ui/premium.py`); the real charge is whatever the
Razorpay plan or Paddle price says, so change all three together.

## Test

```
node test.mjs
```

Runs the whole server against an in-memory SQLite database: sign-in, both checkouts, signed and forged webhooks,
licence keys, the 2-PC limit, cancelling, and gift keys.

## First deploy

The database already exists (`clipstudio`, id in `wrangler.toml`). From this folder:

```
npx wrangler deploy
```

Then open https://clipstudio.zunimilabs.online/plans. It should say `"live": false`.

## Turn on gift keys

Make a long random admin token and give it to the server and to `gift.mjs`:

```
node -e "console.log(require('crypto').randomBytes(24).toString('hex'))" > .admin-token
npx wrangler secret put ADMIN_TOKEN < .admin-token
```

`.admin-token` is git-ignored. Then:

```
node gift.mjs new 3m                                a 3-month gift
node gift.mjs new 30 --note "Thanks for testing"    any number of days
node gift.mjs new 12m --email friend@example.com     also emails the key
node gift.mjs list
node gift.mjs revoke CS-XXXX-XXXX-XXXX-XXXX
```

A gift's days start when the person activates the key in Clip Studio (Settings > Premium > Use a licence key), not
when you make it.

## Turn on sign-in (Google)

1. Google Cloud Console > APIs & Services > Credentials > Create OAuth client ID > **Web application**.
2. Authorised redirect URI: `https://clipstudio.zunimilabs.online/oauth/callback`
3. OAuth consent screen: app name **Clip Studio**, scopes `openid`, `email`, `profile` only. These are not sensitive
   scopes, so Google does not need to verify the app (unlike YouTube access).
4. `npx wrangler secret put GOOGLE_CLIENT_ID` and `npx wrangler secret put GOOGLE_CLIENT_SECRET`

After this the app shows "Sign in with Google", and gift keys work. Payments are still off.

## Turn on Razorpay (India)

1. Razorpay Dashboard > Subscriptions > Plans: create three plans in INR: ₹1,699 every 3 months, ₹2,999 every 6 months,
   ₹4,999 every 12 months.
2. Webhooks: URL `https://clipstudio.zunimilabs.online/webhooks/razorpay`, a secret of your choice, events
   `subscription.activated`, `subscription.charged`, `subscription.cancelled`, `subscription.halted`,
   `subscription.completed`, `subscription.paused`, `subscription.resumed`.
3. Secrets: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_PLAN_3M`,
   `RAZORPAY_PLAN_6M`, `RAZORPAY_PLAN_12M`

## Turn on Paddle (everywhere else)

1. Paddle > Catalog: one product "Clip Studio Premium" with three recurring prices: $20 every 3 months, $35 every
   6 months, $59.99 every year.
2. Developer tools > Authentication: a **client-side token**. Notifications: destination
   `https://clipstudio.zunimilabs.online/webhooks/paddle`, events `subscription.*`.
3. Approve `clipstudio.zunimilabs.online` as a website domain in Paddle (checkout runs there).
4. Secrets: `PADDLE_CLIENT_TOKEN`, `PADDLE_WEBHOOK_SECRET`, `PADDLE_PRICE_3M`, `PADDLE_PRICE_6M`, `PADDLE_PRICE_12M`.
   For testing first, set `PADDLE_ENV = "sandbox"` in `wrangler.toml` and use sandbox values.

## Licence key emails (optional)

Resend.com: verify `zunimilabs.online`, then `npx wrangler secret put RESEND_API_KEY`. Without it, keys are still made
and gift keys are printed by `gift.mjs`; buyers simply do not get the email.

## Going live

Billing turns on by itself once Google and Razorpay or Paddle are set. From then on the free plan's weekly caps apply
in the app, and Premium removes them.
