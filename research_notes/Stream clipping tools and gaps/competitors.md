# Competitive landscape: stream clipping and short-form repurposing tools (as of 6 Nov 2026)

Evidence key, used throughout:
- **[F]** = I fetched the page and read the content.
- **[S]** = search-result excerpt only, page not opened. The eklipse.gg sites returned HTTP 403 to fetching, so every Eklipse-sourced fact is [S].
- Most comparison content on the web is written by vendors. Vendor claims about rivals are labelled as such.

## Who exists now, what each does, how it works, and what it costs

### Takeaway
The market has three layers: free local capture (GPU vendors, OBS, peripheral makers), paid cloud AI clippers (Eklipse, StreamLadder, OpusClip, Vizard, plus a wave of 2025-26 entrants), and native platform tools (Twitch, Kick, YouTube) that are now moving into auto-clipping. The biggest 2026 changes are that Powder closed, Eklipse dropped its free AI tier, and Twitch began shipping chat-aware Auto Clips for free.

### Cited Findings

**Stream-focused AI clippers**

| Tool | Status (late 2026) | What it does and how | Platforms | Cloud or local | Price (date) | Free tier and watermark |
|---|---|---|---|---|---|---|
| Eklipse | Alive | Scans the VOD after the stream ends, including chat spikes — [S](https://eklipse.gg/features/ai-highlights/) | Twitch, Kick, YouTube — [S](https://eklipse.gg/) | Cloud, post-stream | $24.99/mo or $179.99/yr, "region pricing auto-detected" (Eklipse page stamped July 2026) — [S](https://eklipse.gg/compare/eklipse-vs-streamladder/) | Moved to fully paid in June 2026; signup, browser tools and a preview remain free — [S](https://eklipse.gg/help/is-eklipse-free). Older sources show 720p, watermark, 15 highlights per stream; stale — [S](https://blog.eklipse.gg/eklipse-news-and-guide/is-eklipse-free-pricing-and-features-explained.html) |
| StreamLadder | Alive | Clip-to-vertical editor plus ClipGPT AI; VOD-based per a rival — [F](https://clipme.com/best-ai-clipping-tool-for-kick) | Twitch; Kick import reported — [S](https://vidpros.com/streamladder-review-2026/) | Cloud | Unconfirmed. Pricing URL 301-redirects to a login-gated app page ([F](https://app.streamladder.com/upgrade), no plans visible). Third parties say about $8.28/mo to about $19/mo, or unpriced — [S](https://www.creatorstackclub.com/software/streamladder) | Sources conflict on whether free exports carry a watermark — [S](https://vidpros.com/streamladder-review-2026/) |
| Sizzle | Site live, no shutdown notice, undated — [F](https://sizzle.gg/) | AI gaming highlights, filters for kills, knockdowns, headshots, wins; "Universal AI" for unsupported games | Twitch, YouTube, file upload — [F](https://sizzle.gg/). 43 native games (Eklipse's count, undated) — [S](https://eklipse.gg/compare/eklipse-vs-sizzle) | Cloud (inferred from account linking) | Not shown; page links to a "Subscribe" page — [F](https://sizzle.gg/) | Conflicting: "free" versus premium option — [S](https://blog.eklipse.gg/tools/eklipse-vs-sizzle.html) |
| ClipMe (new) | Alive; page updated 7 Oct 2026 | Reads live HLS during the broadcast and cuts ranked 9:16 captioned clips; multi-signal model includes chat velocity; aimed at IRL and Just Chatting — [F](https://clipme.com/best-ai-clipping-tool-for-kick) | Kick, Twitch, YouTube, live and VOD | Not stated (hosted, inferred) | Pro $29/mo (verified by vendor July 2026) | Starter: 1 video/mo at 1080p |
| Cut.Pro (new, Brazil) | Alive; post modified 26 Sep 2026 | Flags moments live, processes VOD after stream, ranks by "Viral Score", publishes to TikTok, Reels, Shorts — [F](https://cut.pro/en/blog/best-clipping-tool-twitch-kick-2026) | Twitch, Kick native | Hosted | R$19.90 (100 credits), R$69.90 (1,000), R$119.90 (2,500) per month; 1 credit = 1 minute | Free tier exists, allowance not given |
| klypra (new) | Alive | Finds highlights live from chat activity, but built for clipping someone else's Twitch stream — [S](https://klypra.app/blog/best-ai-tool-to-clip-twitch-streams) | Twitch | Unclear | Not found | Not found |
| StreamGen (new) | Alive | Lists chat as a clip-finding input — [S](https://streamgen.cc/blog/best-ai-clipping-tool/) | Twitch only | Unclear | Not found | Not found |

ClipMe's own field survey (14 Sep 2026, a vendor source) adds these claims — [F](https://clipme.com/best-ai-clipping-tool-for-kick):
- Clipbait does live clipping on Twitch only.
- StreamClipping AI accepts live input.
- Higgsfield takes YouTube URLs only.
- OpusClip supports Kick only by URL import.
- AutoStreamPro is discontinued, and ClipStream's site no longer resolves.

Other Kick and clip-channel-focused sellers include [AutoClip](https://autoclip.dev/blog/kick-clipping-guide-2026) and [ClipSpeedAI](https://clipspeed.ai/blog/kick-clip-maker.html) [S].

**General repurposing tools (podcast and talking-head first)**

| Tool | Status | Price | Free tier and watermark | Notes |
|---|---|---|---|---|
| OpusClip | Alive; "OpusClip 4.0" banner, undated — [F](https://www.opus.pro/pricing) | Starter $15/mo, Pro $29/mo, Business custom (official page, undated, $ only) — [F](https://www.opus.pro/pricing). Third parties: Starter 150 credits, Pro 300, Pro annual $14.50/mo — [S](https://www.castmagic.io/blog/opus-clip-pricing) | "Post one clip every day for free"; watermark; 3-day export and storage limit; up to 1080p — [F](https://www.opus.pro/pricing). 60 credits/mo per third parties — [S](https://costbench.com/software/ai-video-editing-saas/opus-clip/free-plan/) | Paid plans watermark-free. API on Business only — [S](https://www.castmagic.io/blog/opus-clip-pricing). Rival says no native Twitch or Kick integration — [F](https://cut.pro/en/blog/best-clipping-tool-twitch-kick-2026) |
| Vizard | Alive | Official page rendered "$0" for paid plans, so true prices were not visible — [F](https://vizard.ai/pricing). Third parties conflict: Creator $29, Business $39 monthly; annual figures of $14.50 to $16.90 and $19.50 to $22.80 — [S](https://www.layer3labs.io/guides/vizard-ai-pricing) | 60 credits/mo, 720p, watermark, 3-day storage, 60-min and 1 GB uploads, 10-min export limit — [F](https://vizard.ai/pricing) | Paid plans: from 600 credits, 4K, no watermark, yearly 50% off. Caption languages conflict, 30+ versus 100+ — [S](https://aitoolsatlas.ai/tools/vizard) |
| Clouted (new) | Alive; agency beta planned Q4 2026 | Not found | Not found | AI plus 100,000+ gig clippers for brands and agencies, so not a streamer self-serve tool — [S](https://startupfortune.com/clouted-raises-7/) |
| Klap, Spikes Studio | Alive | USD billing, no Twitch or Kick integration (rival claim) — [F](https://cut.pro/en/blog/best-clipping-tool-twitch-kick-2026) | Not checked | Not researched in depth |

**Streaming-suite and capture tools**

| Tool | Status | Function | Local or cloud | Price and limits |
|---|---|---|---|---|
| Medal | Alive; 17m+ monthly active players, on track for 3bn uploaded clips a year — [F](https://mobilegamer.biz/general-intuition-raises-220m-at-6-2bn-valuation-trains-ai-on-gameplay-clips/) | Game clip capture plus a clip-hosting social platform | Desktop capture, cloud hosting | Free: ads, 20-min uploads, 1080p, watermark on downloads, limited storage — [F](https://medal.tv/premium). Premium: 14-day trial, price not shown; removable watermark, auto subtitles, unlimited storage. A Premium update titled "Same Price, More Stuff" dates to June 2026 — [S](https://medal.tv/blog/categories/features). App-store tracker shows "Medal Gold" $9.99/mo, $95.90/yr at 3 May 2026, not confirmed as the same plan — [S](https://apppricinglab.com/iap/apple/1518008441) |
| Streamlabs Cross Clip | Alive | Clip-to-vertical converter | Cloud | Pro $4.99/mo removes watermark and outro — [S](https://streamlabs.com/cross-clip/plans). Free: 30-min videos, 15 GB. Ultra: 1-hour videos, 250 GB — [F](https://streamlabs.com/goprime) |
| Streamlabs Podcast Editor | Alive | Text-based editing | Cloud | Free: 1-hour uploads with watermark. Ultra: no watermark, 40 hours — [F](https://streamlabs.com/goprime) |
| Streamlabs Ultra | Alive | Bundle | n/a | From $15.75/mo (page showing a promo ending 1 Nov 2026) — [F](https://streamlabs.com/goprime) |
| Replay (formerly Streamlabs Highlighter, now "GHUB Replay") | Alive, renamed | Automated highlighting for 52 games including Apex, Fortnite, LoL, Valorant, Rocket League; exports to PC or phone by QR code | Windows download; local processing implied but not stated | Free; watermark not mentioned — [F](https://streamlabs.com/highlighter). Launched Sept 2024 as the AI Game Highlighter, Fortnite first — [S](https://www.businesswire.com/news/home/20240917543459/en) |
| Outplayed (Overwolf) | Still listed | Auto-records kills, headshots and key moments; share to Discord or YouTube — [S](https://go.overwolf.com/outplayed-inf-2022) | Local, on Overwolf | Price not found |
| Insights Capture (Overwolf) | Still listed | Capture for post-match review — [S](https://www.overwolf.com/browse-by-game/diablo-iv) | Local | Not found |
| SteelSeries Moments | No sign of discontinuation; nothing dated 2026 found | Trim, sort, export; auto-saves with GameSense — [S](https://SteelSeries.com/moments). Auto-Clip not available in every game (rival's blog) — [S](https://clip.dor.gg/en/blog/steelseries-moments-alternative) | Local, in SteelSeries GG | Free |
| NVIDIA ShadowPlay | Alive; folded into the NVIDIA App during 2025 — [S](https://clip.dor.gg/en/blog/shadowplay-alternative) | Instant Replay. App 11.0.8 (17 Jul 2026) adds 240 FPS recording on RTX 40 and 50 — [S](https://www.ithome.com/0/978/389.htm) | Local | Free with NVIDIA hardware (inferred) |
| AMD ReLive | Alive inside Adrenalin; latest thread title shows 26.8.1 WHQL — [S](https://forums.hardwarezone.com.sg/threads/amd-software-adrenalin-edition-26-5-2-whql.7204388/) | Rolling buffer saved on hotkey. Found no AI highlights feature. Optional "AI bundle" exists but is unexplained | Local | Free with AMD hardware (inferred) |
| OBS replay buffer | Alive | Hotkey rolling buffer. The community plugin Replay Buffer Pro needs OBS 32.2.0+, and 1.8.0 lets other apps request 1-second to 6-hour clips through obs-websocket — [S](https://github.com/JoshuaPotter/replay-buffer-pro/releases/tag/1.8.0) | Local | Free |

**Native platform tools**

- **Twitch (official blog, 30 May 2026)** — [F](https://d1x43om3304ey9.cloudfront.net/en/2026/05/30/everything-we-announced-at-twitchcon-rotterdam-2026/) (CDN mirror of a page carrying Twitch branding):
  - Auto Clips generate captioned clips using chat activity, vocal inflection and on-screen events. Beta "in the coming months", with a waitlist.
  - About 50% of streamers have a clip after a stream today; with Auto Clips this rises to about 85%.
  - Saying "Twitch Clip That" creates a clip.
  - Best-clips list in the stream summary and clips in Stories from June. Dual Format streaming in beta.
  - Auto-cropping and trimming are "being explored".
- **Twitch rollout detail:** a third-party post dated 14 Jul 2026 says the voice command is English-only and for Partners and Affiliates — [F](https://badgebase.de/blog/twitch-auto-clips/). Twitch's help article would not render, so this is unverified.
- **Twitch vertical:** auto-generated vertical clips and a clip editor with vertical and split layouts are reported — [S](https://www.lindseygamble.com/blog/twitch-rolls-out-new-clip-editor-to-convert-live-streams-into-vertical-videos).
- **Kick:**
  - `/clip` in chat saves the last 30 seconds or a set duration, up to 180 seconds, but only for Kick Clipping Program members, who apply through Kick's Discord (article dated 3 Nov 2026) — [F](https://win.gg/how-to-use-kick-chat-clipping-feature/).
  - The program pays viewers who clip and share. Kick said it produced 3bn+ views in September 2025 — [S](https://win.gg/kick-clipping-program/).
  - Payout rates such as $1-5 per 1K views come only from tool sellers, so they are unreliable — [S](https://autoclip.dev/blog/kick-clip-channel-monetization-2026).
- **YouTube:**
  - AI highlights that turn a livestream's best moments into Shorts were announced in Sept 2025 — [S](https://techcrunch.com/2025/09/20/updates-to-studio-youtube-live-new-gen-ai-tools-and-everything-else-announced-at-made-on-youtube).
  - A Studio "Video Clips" tool suggests clips, reportedly English-only and 16:9 output (glossary source) — [S](https://www.creatoressentials.com/glossary/auto-generated-clips/).

### Inferences
- Free tiers are narrowing among cloud tools because AI processing costs money per minute. Eklipse went fully paid, and OpusClip and Vizard limit free use with 3-day storage plus watermarks. Local processing avoids that per-minute cost.
- Twitch Auto Clips, once out of beta, directly threatens paid Twitch-only clippers, since it is free and has first-party access to chat and video. Kick and YouTube are less covered on the chat-signal side.
- Paid entry prices cluster around $15-29/mo. Cross Clip Pro at $4.99 and Cut.Pro at R$19.90 are the low-end outliers.

### Gaps
- StreamLadder and Vizard paid prices could not be confirmed from official pages. Medal Premium's price is not publicly displayed.
- OpusClip's official page shows no date, so "as of" dates for its pricing come from third parties (April to October 2026).
- Not confirmed: NVIDIA Highlights' current status and game list, Outplayed pricing and watermark, and any dated 2026 SteelSeries statement.
- Not confirmed: current YouTube AI highlights availability, and YouTube's native viewer-clip limits (the help page I tried returned 404).
- OBS 32 official release notes were not found. Plugin release dates are unverified.

## Which tools have shut down, pivoted or been acquired, and why

### Takeaway
Powder closed for stated financial reasons, confirmed by its own notice. Athenascope closed in 2022 with no public reason found. Medal is the notable pivot: its clips now feed a sister AI lab valued in the billions.

### Cited Findings
- **Powder (closed).** powder.gg now 301-redirects to a Google Doc titled "To the Powder community". It says the team "can no longer sustain the app" after they "stretched our financial capacities as far as possible", the app will no longer be updated, active subscriptions are cancelled, and refunds of unused yearly plans are attempted "wherever possible". No calendar date, no successor, and nothing on user data — [F](https://docs.google.com/document/d/1p8TjN7bCRdOnhrD5DjG02pmoGi4ylsGKmdCS-YV4jrg/edit?tab=t.0).
- **Powder closure date is contested.** Eklipse's comparison page (stamped July 2026) points to July 2026, while another source says 2025 — [S](https://eklipse.gg/compare/eklipse-vs-powder/). A directory checked 8 Oct 2026 still listed it as active, with free (1080p, Powder outro) and Pro at $9.99/mo — [S](https://www.toolmage.com/en/tool/powder-1/). The page attribution of that directory excerpt is my best match from the result set.
- **Powder's last price.** The "$24.99/mo" figure attributed to Powder in search output is the same wording Eklipse uses for its own price, so it is probably Eklipse's and not Powder's — [S](https://eklipse.gg/compare/eklipse-vs-powder/).
- **Powder funding context.** TechCrunch covered it in the past — [S](https://techcrunch.com/?p=2631595). I did not open the article.
- **Athenascope (closed).** Founded by Xfire's Chris Kirmse; $2.5M seed led by First Round in 2019 — [S](https://techcrunch.com/2019/02/08/athenascope-nabs-2-5m-seed-led-by-first-round-to-bring-gamers-ai-edited-highlight-reels). Competitors date the closure to April 2022 — [S](https://framedrop.ai/blog/athenascope-alternative). Users' raw video was uploaded to its server cluster — [S](https://blog.eklipse.gg/tools/athenascope-alternatives-you-need-to-try.html).
- **Medal (pivot, not sale).** Medal and General Intuition are sister companies under a shared parent, and gameplay clips train AI for robotics and driving. Medal says players can opt out at any time — [F](https://mobilegamer.biz/general-intuition-raises-220m-at-6-2bn-valuation-trains-ai-on-gameplay-clips/).
- **Streamlabs Highlighter (renamed).** It is now GHUB Replay under Logitech's G HUB brand — [F](https://streamlabs.com/highlighter).
- **ShadowPlay (absorbed).** Moved from GeForce Experience into the NVIDIA App — [S](https://clip.dor.gg/en/blog/shadowplay-alternative).
- **Eklipse (business-model shift).** Dropped its free AI tier in June 2026 — [S](https://eklipse.gg/help/is-eklipse-free).
- **Small failures.** AutoStreamPro discontinued and ClipStream offline, per a vendor survey — [F](https://clipme.com/best-ai-clipping-tool-for-kick).
- **Overwolf.** No 2026 acquisition, funding or layoff news found. Older deals: CurseForge 2020, Tebex 2022 for $29M, Nitro 2024 — [S](https://en.wikipedia.org/wiki/Overwolf).

### Inferences
- Powder and Eklipse point the same way: free or low-priced AI highlights for gamers are hard to fund. Powder offered unlimited free local analysis and still ran out of money, which suggests that local processing alone does not make a business work. Monetization matters as much as compute cost. This is one case, so treat it as a caution and not a rule.
- Medal's value now appears to lie in its data as much as its clipping product. Streamers wary of AI training may be open to an alternative with no such use of their footage.

### Gaps
- No primary source for why Athenascope closed. A targeted search found no 2022 press coverage or founder statement.
- The Powder notice has no date. The exact closure month is unresolved.
- Fate of Powder users' clips and data is not addressed in the notice.

## Which tools run locally, and which use live chat as a signal

### Takeaway
Local tools rely on game events or hotkeys, while chat-aware tools are all cloud or platform-hosted. I found no live product that does both on the streamer's own PC.

### Cited Findings
- **Local capture, with no AI:** OBS replay buffer, ShadowPlay Instant Replay and AMD ReLive all save on a hotkey (sources in the table above).
- **Local with game-event detection:** Outplayed — [S](https://go.overwolf.com/outplayed-inf-2022); SteelSeries Moments Auto-Clip — [S](https://clip.dor.gg/en/blog/steelseries-moments-not-clipping); Replay (52 games) — [F](https://streamlabs.com/highlighter).
- **Replay's load claim:** a secondary source says it is not a background process and should not add load — [S](https://www.netinfluencer.com/streamlabs-ai-game-highlighter-tool/).
- **Powder** was the closest thing to local AI analysis (unlimited local recording and analysis, any local file) and has closed — [S](https://www.toolmage.com/en/tool/powder-1/).
- **Chat as a signal:**
  - Twitch Auto Clips (chat, vocal inflection, on-screen events) — [F](https://d1x43om3304ey9.cloudfront.net/en/2026/05/30/everything-we-announced-at-twitchcon-rotterdam-2026/)
  - Eklipse (chat spikes in the VOD) — [S](https://eklipse.gg/features/ai-highlights/)
  - ClipMe (chat velocity) — [F](https://clipme.com/best-ai-clipping-tool-for-kick)
  - klypra — [S](https://klypra.app/blog/best-ai-tool-to-clip-twitch-streams)
  - StreamGen — [S](https://streamgen.cc/blog/best-ai-clipping-tool/)
- **Chat as a trigger, not a signal:** Kick's `/clip` command, for program members only — [F](https://win.gg/how-to-use-kick-chat-clipping-feature/).
- **Live, during-broadcast clipping:** ClipMe, Cut.Pro and Clipbait (Twitch), all vendor claims — [F](https://clipme.com/best-ai-clipping-tool-for-kick). Eklipse, StreamLadder and OpusClip are post-stream or VOD-based, per the same source.

### Inferences
- A tool running on the streamer's PC could combine full-quality local video, a replay buffer and live chat across platforms. That combination appears unoccupied. This rests on a search of limited depth, so an obscure plugin or tool could exist.
- Game-event detection needs per-title work (Replay lists 52 games), while chat and voice signals work for any game and for Just Chatting.

### Gaps
- ClipMe, Cut.Pro, klypra and StreamGen do not state their processing architecture clearly. "Hosted" is inferred.
- No independent measurement of clip quality or FPS impact. Eklipse's FPS ranking article returned 403 and would be vendor-written anyway.
- Whether Medal uses any chat input was not established.

## Which support multistreaming, Kick, non-English languages and Indian creators

### Takeaway
Kick support is now common among cloud clippers, but true multistream handling was not found anywhere. I found no stream-clipping tool with confirmed INR and UPI pricing, and the platforms' own new AI features appear to start in English.

### Cited Findings
- **Kick support:** Eklipse — [S](https://eklipse.gg/); ClipMe, live and VOD — [F](https://clipme.com/best-ai-clipping-tool-for-kick); Cut.Pro native — [F](https://cut.pro/en/blog/best-clipping-tool-twitch-kick-2026); StreamLadder import — [S](https://vidpros.com/streamladder-review-2026/); OpusClip by URL only (rival claim) — [F](https://clipme.com/best-ai-clipping-tool-for-kick).
- **Conflict:** Cut.Pro claims to be "the only" native Kick tool in 2026, which ClipMe's and Eklipse's pages contradict — [F](https://cut.pro/en/blog/best-clipping-tool-twitch-kick-2026).
- **Multi-platform input:** ClipMe takes Kick, Twitch and YouTube links — [F](https://clipme.com/best-ai-clipping-tool-for-kick). Eklipse connects all three — [S](https://eklipse.gg/). Neither page I saw describes merging chat from simultaneous streams.
- **Language:**
  - Cut.Pro is built around PT-BR captions and lists `hi` (Hindi) in page metadata; that is not evidence of Hindi clipping quality — [F](https://cut.pro/en/blog/best-clipping-tool-twitch-kick-2026).
  - Twitch's voice command starts in English only — [F](https://badgebase.de/blog/twitch-auto-clips/). A search summary also reported Auto Clips alpha as English-only — [S](https://streamer.guide/blog/twitchcon-rotterdam-2026-new-features-1440p-clips-guilds). The official post gives no language detail.
  - YouTube's Video Clips AI suggestions are reportedly English-only — [S](https://www.creatoressentials.com/glossary/auto-generated-clips/).
- **India pricing:**
  - No evidence OpusClip offers INR or UPI — [S](https://fluxnote.io/guides/opus-clip-cost-2026). That source is a competitor.
  - OpusClip's and Vizard's official pages show "$" only — [F](https://www.opus.pro/pricing), [F](https://vizard.ai/pricing). Fetching from a non-Indian IP may hide localized prices.
  - Eklipse says "region pricing auto-detected", but whether India gets a lower price or INR is unknown — [S](https://eklipse.gg/compare/eklipse-vs-streamladder/).
  - FluxNote, an AI video generator and not a stream clipper, bills in INR through Razorpay with UPI: ₹999, ₹1,699, ₹3,999 per month, 3 free videos/mo — [S](https://fluxnote.io/for-india).
  - Most foreign merchants cannot accept UPI QR or collect requests, per a vendor guide — [S](https://fluxnote.io/guides/best-ai-video-generator-india-2026).
- **Regional pricing precedent:** Cut.Pro bills in reais and argues that USD tools cost Brazilians more, citing the 6.38% IOF tax — [F](https://cut.pro/en/blog/best-clipping-tool-twitch-kick-2026). ChatGPT added Indian pricing and UPI, with Go at ₹399/mo in a 2025 report — [S](https://www.freepressjournal.in/tech/chatgpt-rolls-out-india-pricing-upi-payments-now-accepted).

### Inferences
- Cut.Pro shows that a regional tool can compete on local language plus local billing. No equivalent for Hindi or Hinglish streamers surfaced.
- A $24.99/mo plan is a high price point for many Indian creators, and card-only checkout adds friction, so INR and UPI pricing may be a real wedge. No India demand data was collected here to confirm this.

### Gaps
- Hindi and Hinglish transcription quality for OpusClip, Vizard, Eklipse and StreamLadder was not found. The Eklipse India search returned irrelevant results.
- BGMI and other Indian mobile titles: no tool confirmed support. Replay's full 52-game list was not reviewed.
- India checkout behaviour could not be tested. Checking each tool from an Indian IP and card would settle it.
- No source quantifies Indian streamer usage of any of these tools.

## Market size, funding and adoption

### Takeaway
No credible market size exists for stream clipping specifically. The strongest figures are company-level: OpusClip at about $20M revenue in 2025, Medal's 17m+ monthly users, and General Intuition's billions in valuation built on Medal clips.

### Cited Findings
- **Market:** MarketIntelo projects "clip creation tools" at $6.2B in 2025, about $6.74B in 2026 and $11.8B by 2034 at 8.7% CAGR. This is a broad category from a syndicated report with methodology unseen, so confidence is low — [S](https://marketintelo.com/report/clip-creation-tools-market).
- **OpusClip finance (Sacra):** $20M revenue for 2025, 150% growth, $215M valuation (March 2025), $50M raised, investors including SoftBank Vision Fund 2 and DCM — [F](https://sacra.com/c/opusclip/).
- **OpusClip finance, conflicting:** total raised of $68M — [S](https://geo.sig.ai/brands/opusclip.md) and $79.25M — [S](https://www.cbinsights.com/company/opus-clip/financials). A "$30M+ ARR" claim in a vendor blog is unsourced — [S](https://ideausher.com/blog/build-ai-video-clipping-platform-opusclip/). A tracker estimates about $10.3M revenue — [S](https://yespress.io/opusclip.md).
- **OpusClip users:** 10M+ by early 2025 and 170M+ clips — [F](https://sacra.com/c/opusclip/). 16M+ per its media kit, as reported — [S](https://yespress.io/opusclip.md).
- **General Intuition:** $133.7M seed in Oct 2025 — [S](https://siliconangle.com/?p=716580). $220M at $6.2bn, reported 29 Sep 2026, following "a January round of $320m at a $2.3bn valuation" — [F](https://mobilegamer.biz/general-intuition-raises-220m-at-6-2bn-valuation-trains-ai-on-gameplay-clips/).
- **General Intuition date conflict:** SiliconANGLE reported only talks for about $300M at about $2B on 18 June 2026, which does not fit a January close — [S](https://siliconangle.com/2026/06/18/game-clip-ai-startup-general-intuition-talks-raise-300m-2b-valuation/).
- **Clouted:** $7M seed led by Slow Ventures (May or June 2026, dates differ) — [S](https://startupfortune.com/clouted-raises-7/).
- **Small players:** ClipMe AI is listed as pre-funding, founded 2025, one employee — [S](https://startupim.com/company/clipme-ai). This directory entry may or may not be the clipme.com product. Wisecut about $200K — [S](https://www.vcbacked.co/company/wisecut-ai).
- **Overwolf:** $75M Series D in 2021 led by a16z, about $149M total — [S](https://en.wikipedia.org/wiki/Overwolf).
- **Adoption signals:** Twitch's 50% to 85% post-stream clip figure — [F](https://d1x43om3304ey9.cloudfront.net/en/2026/05/30/everything-we-announced-at-twitchcon-rotterdam-2026/). Kick's 3bn clip-program views in Sept 2025 — [S](https://win.gg/kick-clipping-program/). Medal's 3bn clips a year — [F](https://mobilegamer.biz/general-intuition-raises-220m-at-6-2bn-valuation-trains-ai-on-gameplay-clips/).

### Inferences
- Venture money in this space is concentrated in general repurposing (OpusClip) and in clip data as an AI asset (General Intuition). Stream-only clippers show little disclosed funding, and one of them (Powder) ran out of money.
- Half of streamers lacking a clip after a stream suggests that the bottleneck is clip creation itself, particularly for small channels.

### Gaps
- No funding or revenue data found for Eklipse, StreamLadder, Vizard, Sizzle or Cut.Pro.
- No credible TAM for stream clipping, and no count of paying users across the category.
- No 2026 funding round found for OpusClip.
