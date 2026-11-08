# Clipping apps: how each one finds clips, and what else it does

Researched 8 Nov 2026. This report complements [Stream clipping tools and gaps.md](Stream%20clipping%20tools%20and%20gaps.md), which covers prices, shutdowns, market size and strategy. This one is about mechanics and features.

**How much to trust this.** Almost every source is a vendor page or a competitor's comparison page. Eklipse in particular writes most of the "X vs Y" pages on the web. Nobody publishes independent accuracy tests. Treat every "how it works" line below as what the company says it does.

## 1. There are five ways to find a clip

Every tool uses one or more of these. The method decides what a tool can and cannot catch.

| Method | How it works | Who uses it | Good at | Misses |
|---|---|---|---|---|
| **Hotkey or buffer** | A rolling recording of the last N seconds is saved when you press a key | OBS replay buffer, ShadowPlay, AMD ReLive, Medal (F8), Steam | Anything you remember to mark | Everything you forget to mark |
| **Game events from an API** | The game or an overlay SDK reports a kill or death, and the app saves the time around it | Overwolf Outplayed, Insights Capture, Medal auto-clip, Steam Timeline (Dota 2 and other "timeline-enhanced" games) | Exact kills, aces and deaths, with no guessing | Unsupported games, and funny moments |
| **Reading the HUD from video** | A vision model watches the kill feed, kill banners and score, frame by frame or from keyframes | Eklipse, SteelSeries Moments ("GameSense AI trained to look for events on your in-game HUD"), DOR, Sizzle, GHUB Replay, Clip Studio's `hud.py` | Kills in VODs, with no game integration | Changed HUD settings, a non-English client, overlays covering the kill feed |
| **Audio and chat signals** | Loudness spikes, shouting, laughter, and chat message rate with a delay correction | Eklipse, Sizzle, Spikes Studio, Twitch Auto Clips, StreamLadder ClipGPT ("High chat excitement"), Powder (closed) | Any game, including Just Chatting | Quiet skilled plays, and small channels with little chat |
| **Transcript plus LLM** | Speech-to-text, then a language model picks self-contained moments with a hook and gives each a score | OpusClip (ClipAnything), Vizard, Klap, Submagic Magic Clips, CapCut Long video to shorts | Podcasts and talking | Gameplay with little speech; non-English speech |

The strongest tools combine several methods and then **rank** the candidates instead of applying a cutoff. Eklipse's newer engine is described as multi-signal ("kill feed parsing, recoil/spray context, kill density"). Its older engine found one trigger and cut a fixed 15-30 second window around it. Clip Studio already works this way: sound, HUD and chat feed a ranked shortlist, with speech recognition run only on the shortlist.

## 2. Tool by tool

### A. Clippers built for gaming streams (cloud, VOD after the stream)

**Eklipse**: the closest competitor.
- *How it clips:* you link Twitch, Kick or YouTube, and it scans the VOD after the stream. It reads the HUD (the kill feed is the key element), audio spikes, chat velocity and voice commands. It requires the stream category to be set correctly ("if your stream isn't tagged as Valorant, highlights won't be captured"), the default kill feed style and an English game client. Muted VODs badly hurt accuracy. Its claimed 80-90% usable clips is vendor data.
- *Other features:*
  - AI Edit: auto captions, frame tracking of the action, dead-air removal, and memes and effects placed for you
  - AI Montage maker
  - Meme and gaming templates
  - Auto-Refit 9:16 crop
  - Content Publisher: post now or schedule to TikTok, Reels and Shorts
  - Free browser tools: a caption generator and a montage maker
- *Note:* fully paid since June 2026.
- Sources: [how Eklipse picks highlights](https://eklipse.gg/help/how-does-eklipse-ai-choose-highlights/), [Valorant best practices](https://eklipse.gg/help/best-practices-valorant/), [AI Edit](https://eklipse.gg/features/ai-edit), [Content Planner](https://eklipse.gg/features/content-planner), [montage](https://eklipse.gg/features/the-best-ai-gaming-montage-maker), [gameplay intelligence](https://blog.eklipse.gg/streaming-tips/how-gameplay-intelligence-works-2.html)

**StreamLadder**
- *How it clips:* it started as a manual clip-to-vertical editor. ClipGPT now scans a VOD and returns up to about 10 timestamped candidates, each with a reason such as "High chat excitement".
- *Other features:* automatic facecam and gameplay detection into a 9:16 layout, adjustable layout templates, captions, and a Content Publisher with a scheduler for TikTok, Reels and Shorts. There is also a mobile app, "StreamLadder: AI Clip Editor".
- Sources: [StreamLadder blog](https://www.streamladder.com/blog/best-ai-clipping-tools-in-2025-and-why-many-creators-still-choose-streamladder), [Auto Clips guide](https://streamladder.com/blog/twitch-auto-clips-your-guide-to-automatically-capturing-stream-highlights), [AutoClip comparison](https://autoclip.dev/blog/captions-ai-vs-streamladder-vs-autoclip-for-clippers-2026)

**Sizzle**
- *How it clips:* it analyses video, audio and live chat together, so a chat spike during a big play raises that moment's score. Filters cover kills, knockdowns, headshots and wins. About 43 games are supported natively, with a "Universal AI" fallback for the rest.
- Sources: [sizzle.gg](https://sizzle.gg/), [TwoAverageGamers](https://www.twoaveragegamers.com/best-ai-clip-detection-tools-for-streamers-2026/)

**Spikes Studio**
- *How it clips:* general moment detection, which it says was "trained on hundreds of thousands of broadcasts". It integrates with Twitch and uses chat reaction data. Competitors say it is weaker on game-specific events.
- *Other features:* positions itself as a clipping plus social media management platform, with scheduling.
- Sources: [similarlabs](https://similarlabs.com/p/spikes-studio), [Eklipse vs Spikes](https://eklipse.gg/compare/eklipse-vs-spikes-studio/)

**Framedrop** (successor to JoinCombo)
- *How it clips:* auto-clipping that covers gaming content and chat reactions.
- Sources: [framedrop.ai](https://www.framedrop.ai/joincombo)

**ClipMe and Cut.Pro** (newer, live-capable)
- *How they clip:* ClipMe reads the live HLS stream during the broadcast and ranks moments using several signals, including chat velocity. Cut.Pro flags moments live, then processes the VOD and ranks clips by a "Viral Score".
- *Other features:* both auto-publish. Cut.Pro is built for Brazilian Portuguese and bills in reais, a model for regional pricing.
- Sources: in the [main report](Stream%20clipping%20tools%20and%20gaps.md)

### B. Local desktop recorders with auto-clip (record while you play)

**Medal**
- *How it clips:* desktop capture with a rolling buffer (F8 saves the last 15-180 seconds). Auto-clipping lets you choose which game events to save in Fortnite, League, Rocket League and other games. Medal does not explain the detection method.
- *Other features:*
  - A clip social network with hosting and share links
  - Auto subtitles (Premium)
  - A built-in editor
- *Note:* clips feed General Intuition's AI training, with an opt-out.
- Sources: [medal.tv/auto-clipping](https://medal.tv/auto-clipping), [Eklipse vs Medal](https://eklipse.gg/compare/eklipse-vs-medal-tv)

**Overwolf Outplayed**
- *How it clips:* uses Overwolf's game-event API to capture kills, deaths and objectives automatically. Valorant is supported.
- *Other features:* a match timeline with every event, bookmarks on the editor timeline, and sharing to Discord and YouTube. Ads on the free tier, removed by Premium. It needs the Overwolf client.
- Sources: [Epic Store listing](https://store.epicgames.com/p/outplayed), [PCGamesN](https://www.pcgamesn.com/overwolf-outplayed)

**Insights Capture** (Overwolf, and standalone since 2026)
- *How it clips:* auto-tags kills and deaths with timestamps in Valorant and League, and shows a timeline of game events after each match.
- *Other features:* a VOD Review tool for studying aim, positioning and comms, with drawing and comments, aimed at coaching. It is the only tool here built for self-improvement rather than short clips.
- Sources: [Insights Valorant](https://insights.gg/games/valorant), [Insights vs Outplayed](https://insights.gg/blog/insights-vs-outplayed)

**SteelSeries Moments** (inside SteelSeries GG)
- *How it clips:* "GameSense AI" is trained on each game's HUD and fires an auto-clip on kills and other events. It works only in supported modes and settings, and not with Windows 11 HDR. Valorant is supported.
- *Other features:* trim, sort, export and share.
- Sources: [SteelSeries support](https://support.steelseries.com/hc/en-us/articles/4416847694349), [GG 13.1 notes](https://techblog.steelseries.com/2022/01/19/GG-notes-13.1.html)

**DOR** (clip.dor.gg)
- *How it clips:* starts recording when Valorant launches and saves kills, aces and clutch rounds as separate clips. It keeps the full-match recording too, and falls back to monitor capture where anti-cheat blocks hooking.
- *Other features:* shares clips as a dor.gg link that plays in a mobile browser with no app needed.
- Sources: [DOR Valorant](https://clip.dor.gg/en/games/valorant), [auto clip detection explained](https://clip.dor.gg/en/blog/auto-clip-detection-explained)

**GHUB Replay** (formerly Streamlabs Highlighter)
- *How it clips:* automated highlights for 52 games, including Valorant.
- *Other features:* exports to PC, or to your phone by QR code. Free.
- Sources: [streamlabs.com/highlighter](https://streamlabs.com/highlighter)

**Allstar**
- *How it clips:* does **not record your screen.** It takes the game's own match data or demo file and **renders the clip in the cloud**, so there is no FPS cost. You can also upload CS2 demos (zipped, Competitive and Wingman only), and clips appear about 30 minutes later. It supports CS2, Dota 2, League and Fortnite, but **not Valorant**, because Valorant has no public demo files.
- Sources: [Allstar demo upload](https://help.allstar.gg/hc/en-us/articles/12775949766551-Can-I-upload-a-demo-file-to-Allstar), [CS2 FAQ](https://help.allstar.gg/hc/en-us/articles/17552790931735-CS2-FAQ)

**Steam Game Recording**
- *How it clips:* background recording keeps the last 120 minutes by default, or you record on demand. The **Steam Timeline** shows markers for achievements and screenshots, your own markers (Ctrl+F12), and markers that "timeline-enhanced" games add themselves, such as kills in Dota 2.
- *Other features:* export to MP4, sharing with Steam friends, and Steam Deck support.
- Sources: [HotHardware](https://hothardware.com/news/steam-has-a-new-game-recording-tool), [Insider Gaming](https://insider-gaming.com/steams-game-recording-feature-is-now-out-of-beta/)

**NVIDIA ShadowPlay, AMD ReLive, OBS replay buffer**
- *How they clip:* hotkey buffers with no AI.
- *Other features:* the OBS plugin Replay Buffer Pro lets other apps request clips of 1 second to 6 hours through obs-websocket, the same path Clip Studio uses.

### C. General repurposing tools (podcast and talking-head first, but streamers use them)

**OpusClip**
- *How it clips:* the **ClipAnything** model is multimodal: it uses transcript, visuals and sound. You can steer it with a prompt ("clip the moment where..."). Each clip gets a **0-99 virality score** for hook, flow, value and trend.
- *Other features:*
  - **ReframeAnything:** tracks moving speakers and objects for 9:16
  - Animated captions, plus AI B-roll that can be swapped
  - Brand templates and a scheduler that posts to social platforms
  - Export to Premiere and DaVinci
- *Added in Aug 2026:* AI Producer, automatic sound effects, retake detection and brand-aware editing. Agent Opus makes a video from a topic.
- *Pricing:* 1 credit = 1 minute of source video.
- Sources: [ClipAnything](https://opus.pro/clipanything), [AI Reframe](https://www.opus.pro/ai-reframe), [choppingblock profile](https://www.choppingblock.ai/companies/opusclip-65197), [computertech review](https://computertech.co/opus-clip-review/)

**Vizard**
- *How it clips:* a highlight engine over transcript and video. You choose length bands (under 30s, 30-60s, 60-90s), and it may give a lighter engagement prediction; sources conflict.
- *Other features:* text-based editing (delete words to cut video), vertical reframing, B-roll, auto subtitles, and translation into "100+" languages, a figure sources dispute.
- Sources: [Vizard blog](https://vizard.ai/blog/best-ai-video-clipping-tools-in-2026), [Capterra](https://www.capterra.ae/software/1050295/vizard)

**Klap**
- *How it clips:* paste a YouTube link and get clips. It analyses transcript, tone and visuals, and gives a virality score (disputed).
- *Other features:* reframing with speaker detection, captions with keyword highlighting, and a scheduler.
- Sources: [Dupple review](https://dupple.com/reviews/klap-ai), [aisotools](https://aisotools.com/blog/klap-review-2026)

**Submagic**: a finishing tool more than a finder.
- *How it clips:* Magic Clips picks highlights, and some users report bugs.
- *Other features:*
  - **Auto zooms** with no keyframing
  - **Magic B-roll** chosen from the transcript, which reviewers say often mismatches
  - **Sound effects** and animated emojis with sound
  - **"Generate Hook Title"** intro text
  - Word-emphasis captions with emojis, in 48 languages
  - Background music and audio cleanup
- Sources: [auto zooms](https://submagic.co/features/auto-zooms), [B-roll](https://submagic.co/features/b-roll), [help guide](https://care.submagic.co/en/article/how-to-use-submagic-step-by-step-guide-pafx7o/)

**CapCut** (desktop)
- *How it clips:* "Long video to shorts" accepts uploads of 1 minute to 3 hours. You pick a length (Auto, under 60s, 60-90s, 90s-3min), and it picks moments from speech patterns and adds subtitles.
- *Other features:* a separate "Auto Cut" feature syncs edits to music rhythm. CapCut is free and the default editor for many Indian creators. A competitor's test found its Hinglish accuracy weak.
- Sources: [CapCut help](https://www.capcut.com/help/auto-cut-in-capcut), [Lindsey Gamble](https://www.lindseygamble.com/blog/capcut-launches-long-video-to-shorts-tool-to-turn-long-form-horizontal-videos-into-short-form-videos)

**Descript, Captions.ai, Streamlabs Cross Clip and Podcast Editor**
- Text-based editing is the common thread.
- Captions.ai adds **eye-contact correction**, voice cloning and AI dubbing.
- Cross Clip is a cheap clip-to-vertical converter.
- Munch's self-serve tool appears to be gone; it is now a done-for-you agency.
- Sources: [toolradar](https://toolradar.com/compare/captions-vs-descript), [OpenClip on Munch](https://openclip.app/alternatives/munch-alternatives)

### D. Platform-native tools (free, and the biggest threat)

**Twitch Auto Clips**
- *How it clips:* chat activity, vocal inflection and on-screen events, then it publishes captioned clips automatically.
- *Other features:* the **"Twitch, Clip That"** voice command, a vertical clip editor with split layouts, and best clips in the stream summary. Auto-cropping is being explored.
- *Status:* still a staged closed beta. I found no general release by Nov 2026. The voice command is English-only, for Partners and Affiliates.
- Sources: [Twitch blog](https://blog.twitch.tv/en/2026/05/30/everything-we-announced-at-twitchcon-rotterdam-2026/), [GamingCareers](https://gamingcareers.com/newsletters/twitch-clip-that-actually-works-now/), [Zach Bussey](https://x.com/zachbussey/status/2033003837032702321)

**YouTube Live AI highlights**
- *How it clips:* after a stream, YouTube drafts highlight Shorts for you to review and post. Announced Sept 2025. I found no current language list, though earlier sources say English-only with 16:9 output.
- Sources: [Dexerto](https://jamtest.dexerto.com/youtube/youtube-launches-ai-powered-highlight-tool-to-automatically-create-stream-clips-3252018), [Tribune](https://tribune.com.pk/story/2567348/youtube-introduces-ai-powered-tool-to-automatically-generate-stream-highlights)

**Kick `/clip`**
- *How it clips:* a chat command saves up to 180 seconds, for Clipping Program members only.

### E. Indian, Hinglish-first tools (small, new, caption-focused)

None of these find gameplay moments. They are caption tools that compete only with Clip Studio's caption step, and none has proven traction.

| Tool | What it says it does | Source |
|---|---|---|
| Zoupyu | A Hinglish shorts generator that uses Sarvam's Saaras model instead of Whisper. Free tier: 3 videos. | [AlternativeTo](https://alternativeto.net/software/zoupyu/about/) |
| UNR Captions | Hinglish captions. Launched on Product Hunt in Dec 2025; 3 free videos a month. | [Product Hunt](https://www.producthunt.com/products/unr-captions) |
| Bol Studio | Hindi, Hinglish and English captions | [SaaSHub](https://www.saashub.com/bolstudio-me) |
| Captiq | One-click Hindi captions. Very little traction. | [Product Hunt](https://www.producthunt.com/p/captiq) |
| VideoCaptions.AI | Claims the lowest Hindi and Hinglish word error rate in its own test | [comparison](https://www.videocaptions.ai/best/hindi-caption-generator) |

Adobe users are still asking for Hinglish captions in Premiere ([Adobe community](https://community.adobe.com/t5/premiere-pro-ideas/hinglish-language-speech-to-text-for-captions-feature-request-indian-creators/idi-p/15499811)), which shows that mainstream editors don't handle it.

### F. Open source (useful to read, check licences first)

- **clipsmith:** Twitch VOD plus chat replay, faster-whisper, candidate scoring, then LLM selection with titles and reasons. MIT. ([PyPI](https://pypi.org/project/clipsmith-ai/))
- **sfce:** VOD, WAV audio and chat CSV feed a LangGraph multimodal pipeline that outputs clips plus JSON. ([GitHub mirror](https://gh.ali360.cloudns.ch/orhna/sfce))
- **Auto-Clipper:** Whisper trigger phrases plus YOLO for game visuals. ([GitHub](https://github.com/bendawg2010/Auto-clipper))
- **stream-clipper:** audio plus chat activity. ([GitHub](https://github.com/nirvagold/stream-clipper))
- **VodAutoClipper:** clips from a Twitch VOD, with faster-whisper as an option. ([mirror](https://gh.r-mj.com/wAIfu-DEV/VodAutoClipper))
- ClipsKitty (`clips-studio`, AGPL) is covered in the main report.

## 3. Feature checklist against Clip Studio

I checked this against the code in `clipstudio/` as of today. "Has" means the feature exists in some form, not that it matches the competitor's quality.

| Feature | Who has it | Clip Studio |
|---|---|---|
| Ranked shortlist with a reason per clip | StreamLadder ClipGPT, OpusClip | **Has** (`detect.py`, review desk tags) |
| HUD kill and death reading for Valorant | Eklipse, SteelSeries, DOR, Insights | **Has** (`hud.py`) |
| Laughter, shouting, gunfire from audio | Powder (closed), Eklipse (spikes only) | **Has** (`sound.py`) |
| Chat signal with delay correction | Eklipse, Sizzle, Twitch Auto Clips | **Has** (`chat.py`, `detect.py`) |
| Hotkey markers during stream | Medal, Steam, OBS, Twitch voice command | **Has** (F9 and OBS replay) |
| Virality score | OpusClip, Klap, Cut.Pro | **Has** (`insights.py`, 0-99) |
| Title and hashtag suggestions | OpusClip, Klap | **Has** (`insights.py`) |
| Montage or compilation | Eklipse, Insights | **Has** ("only kills" filter joined in stream order) |
| Facecam plus gameplay 9:16 layout | StreamLadder, Eklipse | **Has** (`ui/facecam.py`, `render.py`) |
| Caption styles and translation | Everyone; Submagic leads on style | **Has** (Hinglish romanisation in `roman.py`, English translation) |
| Full local recording, no upload | Medal, Outplayed, DOR, Steam | **Has** (OBS) |
| **Post or schedule to YouTube Shorts, Reels, TikTok** | Eklipse, StreamLadder, OpusClip, Klap, Spikes, Cut.Pro | **Missing** |
| **Auto zoom or punch-in on the kill and the reaction** | Submagic, Eklipse ("frame tracks the action"), OpusClip ReframeAnything | **Missing** |
| **Sound effects, memes, emoji pops** | Eklipse AI Edit, Submagic, OpusClip (Aug 2026) | **Missing** |
| **Hook text on screen in the first seconds** | Submagic "Generate Hook Title" | Partial: titles are generated but not burned in as an intro overlay |
| **Prompt-based search ("find where I said 'bhai'")** | OpusClip ClipAnything | **Missing** (the transcript is there, so this is a cheap win) |
| Dead-air or silence removal | Eklipse AI Edit, Descript, Vizard | Unclear: manual cut exists, auto not found |
| B-roll from stock footage | OpusClip, Vizard, Submagic | Missing, low value for gameplay |
| Text-based editing (delete words to cut) | Vizard, Descript, Captions | Missing |
| Match timeline with every event, coach-style VOD review | Outplayed, Insights | Partial: the timeline exists, but not a review mode |
| Share link that plays on phone | DOR, Medal | Missing (export only) |
| Live clipping during the stream | ClipMe, Cut.Pro, Twitch | Deliberately not done (analysis waits for the stream to end) |
| Dubbing, voice cloning, eye contact | Captions.ai, Munch | Missing, not relevant |

## 4. What this suggests for Clip Studio

1. **Direct posting is the biggest missing piece.** Every paid competitor has a publisher or scheduler, and it is what turns "I have clips" into "I posted clips". The YouTube Data API allows Shorts uploads with OAuth. TikTok and Instagram have stricter app review. Start with YouTube Shorts.
2. **Gaming-specific editing effects are the next differentiator.** No one has gaming-aware effects done well. Clip Studio already knows the exact kill timestamp from `hud.py` and the laugh timestamp from `sound.py`, so it can place:
   - a punch-in zoom on the kill
   - a sound effect or emoji pop on the laugh
   - hook text over the first 2 seconds

   Competitors guess these from the transcript. Clip Studio would place them from actual events.
3. **Prompt or keyword search over the transcript is a cheap feature that people love.** The transcript already exists for every shortlisted clip.
4. **Hinglish is still an open position.** The Indian Hinglish tools are caption-only startups with no gameplay detection, and the big tools are English-first. Twitch's and YouTube's native tools also start English-only.
5. **Allstar's approach does not apply to Valorant** (no demo files), so HUD reading stays the right method for Valorant. Steam Timeline markers could be a cheap extra signal for other games later.

## Gaps in this research

- No first-hand testing of any tool, and no independent accuracy numbers anywhere.
- Medal's auto-clip detection method is undocumented. Sources disagree on whether it is AI or manual.
- Twitch Auto Clips' status in Nov 2026 is unconfirmed beyond "closed beta".
- YouTube AI highlights: no language list or current availability found.
- Clipbait: nothing found.
