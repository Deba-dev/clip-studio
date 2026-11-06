# Technical pipeline of AI stream clipping and highlight detection (Twitch, YouTube, Kick)

State as of 2026-11-06. Reliability tags used below:
- **[primary]**: I read the official page or the paper itself.
- **[snippet]**: I saw only a search-result excerpt, not the full page.
- **[secondary]**: third-party blog, vendor page or README.
- **[dated YYYY]**: older than 2025; check it is still true before relying on it.

Three official sources could not be read directly:
- developers.tiktok.com returned HTTP 503 on every direct fetch, so all TikTok wording comes from search excerpts of those pages plus third-party quotes.
- help.twitch.tv did not render (JavaScript error page).
- The body text of legal.twitch.com did not render.

## How is highlight detection done from chat, audio, video and transcripts, and how accurate is it?

### Takeaway
No single signal wins. On pro League of Legends broadcasts, audio and video beat chat alone, and fusing them helps. Cheap chat features with a learned offset of about 25 s still give strong top-K precision when a channel has enough chat. Ranking candidates beats thresholded classification. I found no published accuracy figure for LLM ranking of streamer transcripts, or for any commercial clipper, so those claims are unverified.

### Cited Findings

**Chat signals**
- LIGHTOR [dated 2019, primary] uses a 25 s sliding window and three features: message count, message length, and message similarity (bag-of-words, one-cluster K-means, mean similarity to the centre). Message count alone works for k <= 3 but degrades at k = 10; the three-feature model is best above 5 highlights — [LIGHTOR](https://ar5iv.labs.arxiv.org/html/1910.12201)
- Chat delay: LIGHTOR's learned offset between highlight and chat response was 23–27 s across training sizes, and its worked example shows about 20 s. This was measured on 2019 Twitch latency — [LIGHTOR](https://ar5iv.labs.arxiv.org/html/1910.12201)
- LIGHTOR accuracy:
  - Chat Precision@10 of 0.82 from one training video.
  - End to end on 7 Dota2 videos, trained on 1 LoL video: Precision@5 of 0.906 (start) and 0.719 (end).
  - Joint-LSTM trained on 123 videos scored 0.629 and 0.600.
  - Training took 1.06 s versus more than 3 days.
  - The authors' headline claim is 70–90% precision in the top-k — [LIGHTOR](https://ar5iv.labs.arxiv.org/html/1910.12201)
- LIGHTOR's data had 800–4,300 chat messages per video. In its Dota2 top-10-channel sample, more than 80% of videos exceeded 500 messages per hour — [LIGHTOR](https://ar5iv.labs.arxiv.org/html/1910.12201)
- Simple adjustment matters: the Toretter social-media event baseline got Video Precision@K (start) below 20%, and LIGHTOR's adjustment was about 3x better — [LIGHTOR](https://ar5iv.labs.arxiv.org/html/1910.12201)
- Fu et al. [dated 2017, primary] covered 321 LoL videos (218 NALCS, 103 LMS, about 7,500 chats per video). Test F-scores on NALCS / LMS were: chat-only 43.2 / 39.7, video-only 72.2 / 69.2, joint 74.7 / 70.0. Chat used a forward window of 7 s, and the paper has no explicit lag model — [Fu et al.](https://ar5iv.labs.arxiv.org/html/1707.08559)
- A student practitioner project used an exponentially weighted moving average to flag chat surges [dated 2019, snippet, not peer-reviewed] — [HdM Stuttgart blog](https://blog.mi.hdm-stuttgart.de/index.php/2019/08/21/evaluating-and-visualizing-statistical-bot-data/)
- Emote semantics are poorly labelled: a 2021 paper built an emote pseudo-dictionary and says labelled Twitch emote data is nearly nonexistent [snippet] — [arXiv 2108.08411](https://arxiv.org/pdf/2108.08411.pdf)
- A master's dissertation pre-trained a language model on LoL stream chat for this task [snippet] — [Gutsche 2022](https://www.um.edu.mt/library/oar/handle/123456789/137285)
- Twitch chat latency modes, from third-party guides only and inconsistent: Ultra Low 2–5 s, low about 7 s, normal 10–30 s, plus an optional streamer delay of 0–15 minutes [secondary, snippet] — [guide](https://space-node.net/blog/twitch-low-latency-mode-settings-2026), [guide](https://besttwitchextensions-com.pages.dev/articles/twitch-stream-delay-complete-guide.html)

**Audio**
- Ringer et al. (Autohighlight) [dated 2022, primary, pro LoL broadcasts, weakly supervised]. Single-modality mean AP:
  - Audio 0.366
  - Optical flow 0.335
  - RGB 0.328
  - Single frame 0.151
  - Random 0.118
  - Fusion: RGB+Audio 0.444; RGB+Flow+Audio hybrid 0.462 — [Ringer et al.](https://eprints.whiterose.ac.uk/186731/1/Highlight_Journal_MLwA_2_.pdf)
- Same paper: Gaussian smoothing of the score curve lifted mean AP from 0.462 to 0.511. A ranking model reached F1 0.521 (P 0.488, R 0.559) against 0.343 for a binary classifier at its threshold — [Ringer et al.](https://eprints.whiterose.ac.uk/186731/1/Highlight_Journal_MLwA_2_.pdf)
- General audio taggers:
  - PANNs best system: AudioSet mAP 0.439; a lighter MobileNet variant 0.383 — [PANNs](https://arxiv.org/abs/1912.10211v5)
  - BEATs iter3+: 0.498, from a third-party listing [secondary] — [Codesota](https://codesota.com/audio/classification)
  - YAMNet predicts 521 classes including laughter — [TensorFlow](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio?hl=hi)
- Dedicated laughter detector: Gillick et al. (Interspeech 2021). `segment_laughter.py` outputs time segments, default threshold is 0.5, and v2.0 is more robust to background noise false positives [snippet] — [jrgillick/laughter-detection](https://www.github.com/jrgillick/laughter-detection). A newer close-mic podcast model also exists — [zencastr](https://huggingface.co/zencastr/laughter-detection)
- Open-source heuristic set: ClipsKitty works in 1-second bins with loudness spikes, burst density (laughter or applause) and silence-to-explosion payoff shapes [secondary, README] — [clips-studio](https://github.com/ColinGPT9/clips-studio)
- A patent describes a neural network listening to chat, mic and game audio for laughter or screams [snippet] — [US 12330058](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12330058)

**Video and game events**
- "Gameplay Highlights Generation" (2025) [primary]:
  - Fine-tuned X-CLIP-B/16 on 1-second clips across 5 FPS games, with 4,408 labelled events and 7 event types.
  - Accuracy 94.3%, or 92.9% after INT8 quantisation (768 MB to 192 MB).
  - Weak spots: Fortnite 85.4%, Overwatch 2 76.9%.
  - Unseen Apex Legends: 89.2% average, but kill accuracy only 69.0%.
  - Runtime: about 0.15 s per 1 s clip via ONNX Runtime DirectML on Windows, costing about 13 FPS in Fortnite and about 1,500 MB VRAM.
  - No code released at time of paper — [arXiv 2505.07721](https://ar5iv.labs.arxiv.org/html/2505.07721)
- That paper argues YOLO/OCR-style HUD reading needs expensive per-game engineering and may not generalise across UI or language. It gives no comparison numbers — [arXiv 2505.07721](https://ar5iv.labs.arxiv.org/html/2505.07721)
- I found no published accuracy figure for kill-feed OCR. A US patent sets a kill-event criterion at 85% or more certainty [snippet] — [US 12383838](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12383838). An open-source tool runs game-specific YOLO profiles [snippet] — [Auto-clipper](https://github.com/bendawg2010/Auto-clipper)
- Commercial claims, not independently tested:
  - Powder reportedly has 40+ game-specific models and a chat "Community Hype" feature [secondary] — [AutoClip roundup](https://autoclip.dev/blog/gaming-clip-maker-2026)
  - Powder yell detection, 2023 — [TechCrunch](https://techcrunch.com/2023/11/20/powder-an-ai-clipping-tool-for-gaming-can-detect-when-a-creator-yells-during-a-stream)
  - Eklipse analyses high emotion, sudden volume changes and viewer engagement — [Eklipse help](https://eklipse.gg/help/can-ai-detect-non-gameplay-moments/)
- For unsupported titles, vendors reportedly fall back to audio intensity plus chat velocity, which misses quiet clutch plays [secondary, snippet] — [AutoClip](https://autoclip.dev/blog/gaming-clip-tool)
- Scene change: AutoFlip compares colour histograms between frames [dated 2020] — [Google](https://research.google/blog/autoflip-an-open-source-framework-for-intelligent-video-reframing/). ClipsKitty uses scene cuts, motion and face-area change as signals — [clips-studio](https://github.com/ColinGPT9/clips-studio)

**Multimodal and transcript/LLM ranking**
- KuaiHL (2024) [primary]: a causal multimodal transformer on a proprietary set of 19,334 hours. It reached Kendall tau 0.5961 on KLive and 21.89 mAP on PHD. Removing visual cost 4.72% and removing text cost 2.01%. It does not isolate audio. It is causal, so it uses no future frames — [arXiv 2407.12002](https://arxiv.org/html/2407.12002v1)
- Open-source pattern, signals then LLM:
  - clipsmith ranks by chat density plus clip and `!clip` signals, then sends up to 20 candidates to an LLM, which outputs accepted clips, titles and reasons (1 star, MIT) — [clipsmith](https://github.com/ricardogr07/clipsmith)
  - ClipsKitty scores the transcript with signals, then runs a head-to-head rerank call on the top candidates (213 stars, AGPL-3.0) — [clips-studio](https://github.com/ColinGPT9/clips-studio)
- Trained MLLM highlight detection on QVHighlights reached 56.74 HIT@1 using 25 frames (Dec 2025, not stream data) [snippet] — [arXiv 2512.12246](https://arxiv.org/abs/2512.12246v1). A 2026 zero-shot CLIP+LLM method reports only on TVSum and SumMe [snippet] — [arXiv 2609.14790](https://arxiv.org/pdf/2609.14790)

### Inferences
- A workable baseline for a solo developer:
  1. Bin all signals at 1 s.
  2. Compute chat rate, unique chatters and message similarity over a 25 s window.
  3. Z-score each signal against a rolling channel baseline (EWMA).
  4. Shift chat back by a per-channel offset, initialised near 20–25 s and lowered for low-latency viewers.
  5. Smooth with a Gaussian.
  6. Take top-K peaks.
  7. Send about 20 candidates with transcript text to an LLM for rerank and titles.
- Rank top-K rather than classify. The Ringer and LIGHTOR results both point this way, and users choose from a shortlist anyway.
- Chat methods were tested on channels with thousands of messages per video. Small streamers will have sparse chat, so audio and transcript must carry the score. This is my reasoning; I found no study on low-chat channels.
- Esports numbers come from produced broadcasts with casters. Solo streamer audio (mic reactions) may behave differently, so these figures do not transfer directly.
- Per-game models give the best event precision but cost the most to maintain. X-CLIP-style cross-game fine-tuning is a cheaper middle route, though the 69% unseen-game kill accuracy shows its limit.

### Gaps
- No accuracy data for LLM ranking on streamer transcripts, and no independent benchmark of Eklipse, Powder, Medal, OpusClip or similar tools.
- No study found on facecam emotion for highlight detection, so this signal is unevidenced here.
- No per-class AudioSet AP for laughter or screaming, and no evidence on how these taggers perform with game audio mixed in.
- ffmpeg `ebur128` as a spike detector was not verified.
- 2025–2026 papers specific to game streams combining chat, audio and LLMs did not surface. The absence may reflect search limits.
- No measured 2026 Twitch chat-delay distribution, and no equivalent for YouTube or Kick.

## How do tools capture source footage, and what are the limits?

### Takeaway
There is still no official full-VOD download API on Twitch, YouTube or Kick that I could find. Twitch's official route is now clips only (5–60 s) and needs broadcaster or editor authorisation. For a tool serving the creator, local recording or the OBS replay buffer plus live chat ingest avoids retention, muting and terms problems together. VOD downloading by third parties conflicts with YouTube's and Kick's written terms.

### Cited Findings

**Twitch official APIs** [primary]
- Create Clip `POST /helix/clips`: scope `clips:edit`, user token, duration 5–60 s (default 30), no offset parameter. It captures up to 90 s around the call. `edit_url` is valid up to 24 h or until publish. It returns 403 if the channel restricts or disables clips — [Twitch API reference](https://dev.twitch.tv/docs/api/reference/)
- Create Clip From VOD `POST /helix/videos/clips`: scope `editor:manage:clips` or `channel:manage:clips`, duration 5–60 s. `vod_offset` is the second the clip ends, and the clip starts at `vod_offset - duration`. Broadcaster or editor only — [Twitch API reference](https://dev.twitch.tv/docs/api/reference/). Open beta 2025-12-19, generally available 2026-02-05 — [Twitch changelog](https://dev.twitch.tv/docs/change-log/)
- Get Clips Download `GET /helix/clips/downloads`: up to 10 clip IDs per call, 100 requests per minute, temporary URLs, caller must be an editor for the broadcaster. Generally available 2025-10-30 — [reference](https://dev.twitch.tv/docs/api/reference/), [changelog](https://dev.twitch.tv/docs/change-log/)
- Create Clip gained 2K and vertical output for dual-format streams, plus optional title and duration, on 2025-12-19 — [changelog](https://dev.twitch.tv/docs/change-log/)
- Get Clips: `vod_offset` stays null for typically minutes after a clip is created during a broadcast. Pagination tops out around 1,000 results — [reference](https://dev.twitch.tv/docs/api/reference/)
- The changelog's 2025–2026 entries show no full-VOD download endpoint — [changelog](https://dev.twitch.tv/docs/change-log/)
- Rate limits use a token bucket per client ID (per user for user tokens). The docs show `Ratelimit-Limit: 800` as an example only — [Twitch API guide](https://dev.twitch.tv/docs/api/guide/)
- Chat ingest: `channel.chat.message` remains the EventSub chat event and gained `gif` fragments on 2026-07-16 — [changelog](https://dev.twitch.tv/docs/change-log/)

**Twitch VOD limits**
- Retention [secondary, Twitch's own help page unreadable]:
  - 60 days for Partner, Turbo and Prime; 14 days for Affiliate; 7 days for others.
  - "Store Past Broadcasts" is off by default for non-affiliates.
  - Expiry is permanent — [StreamVault](https://streamvault.gg/how-long-twitch-keeps-vods/)
  - One outlier page disagrees (14 days for regular users, 60 for Affiliates) and looks wrong — [TinyGrab](https://tinygrab.com/how-long-does-twitch-save-vods)
- Highlights and Uploads share a 100-hour cap, enforced from 2025-04-19, with the least-viewed items deleted automatically. VODs and Clips are excluded [secondary] — [StreamVault](https://streamvault.gg/how-long-twitch-keeps-vods/)
- Dual-format 2K or vertical copies reportedly expire after 7 days [secondary, snippet] — [search excerpt source](https://vod.ing/blog/twitch-vod-retention)
- `muted_segments` in Get Videos is a list of `{duration, offset}` objects [secondary, library source; the reference page section was not reached] — [twitch_api crate](https://docs.rs/crate/twitch_api/latest/source/src/helix/endpoints/videos/get_videos.rs)
- Sub-only VODs return 403 with `vod_manifest_restricted` or `unauthorized_entitlements` unless authorised — [TwitchDownloader source](https://github.com/lay295/TwitchDownloader/blob/f3cab4ac6b2195ad3853cda689e4960e3149eab1/TwitchDownloaderCore/TwitchHelper.cs). Community tools ask users to copy a browser OAuth token — [twitch_archiver](https://github.com/F0903/twitch_archiver)
- Unofficial tooling: TwitchDownloader handles VOD, clip and chat download with a cross-platform CLI — [TwitchDownloader](https://github.com/lay295/TwitchDownloader). clipsmith uses twitch-dl plus chat-downloader — [clipsmith](https://github.com/ricardogr07/clipsmith)

**YouTube**
- API clients must not "download, import, backup, cache, or store copies of YouTube audiovisual content" without written approval, and must not scrape or obtain scraped content (Policies III.E.1, III.E.6) — [YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- Live chat: `liveChatMessages.streamList` is server streaming, costs 5 units per call, returns recent history on connect, resumes with `nextPageToken`, and `maxResults` is 200–2000 — [YouTube docs](https://developers.google.com/youtube/v3/live/docs/liveChatMessages/streamList)
- ClipsKitty uses YouTube's most-replayed heatmap as an optional bonus signal and channel RSS to watch for uploads — [clips-studio](https://github.com/ColinGPT9/clips-studio)

**Kick**
- Retention: 7 days for regular channels, 30 for verified. Stored maximum is 16 or 30 replays — [Kick Help](https://help.kick.com/en/articles/7112432-kick-vods-stream-replays)
- Partner and Verified channels can pin up to 5 VODs, kept permanently. The official download button is in Creator Dashboard > Studio > VODs, is desktop only, and works for your own channel only (article dated 2026-10-03) — [Upstream](https://upstream.so/blog/how-to-download-kick-vods/). One post claims 60 days for partners, contradicting the Kick help page [snippet] — [AutoClip](https://autoclip.dev/blog/kick-clipping-guide-2026)
- Official developer docs show channels, chat, livestreams, categories, moderation, Kicks and events such as chat message sent and livestream metadata. No clip or VOD endpoints appear in the pages I could read — [Kick docs](https://docs.kick.com/), [KickDevDocs](https://github.com/KickEngineering/KickDevDocs)
- Chat history conflicts:
  - One developer says no public endpoint returns past chat [secondary] — [DEV post](https://dev.to/devil_scrapes/kick-chat-scraper-archive-live-chat-before-it-disappears-forever-32b3)
  - ClipsKitty says Kick discards chat after a stream — [clips-studio](https://github.com/ColinGPT9/clips-studio)
  - Streams Charts claims chat downloads where replay is public, contradicting the above — [Streams Charts](https://streamscharts.com/tools/chat-logs-downloader)
- A vendor claims Kick's archive is "less aggressively policed" on audio than Twitch's, which is unmeasured [secondary] — [AutoClip](https://autoclip.dev/blog/kick-vs-twitch-vod-availability-for-clippers)

**OBS and local capture** [primary]
- obs-websocket 5.x: `SaveReplayBuffer`, the `ReplayBufferSaved` event (returns `savedReplayPath`) and `GetLastReplayBufferReplay` were added in v5.0.0. `CreateRecordChapter` was added in v5.5.0 and, as of OBS 30.2.0, only Hybrid MP4 supports it — [protocol.md](https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md)
- The "Save Replay Buffer" hotkey must be set in OBS even if you trigger only over websocket [secondary, library docs] — [goobs](https://beta.pkg.go.dev/github.com/andreykaipov/goobs@v0.6.0/api/requests/replay_buffer)

### Inferences
- Best-fit architecture for a creator-facing desktop tool:
  1. OBS records locally, or the tool uses the replay buffer.
  2. The tool ingests live chat from EventSub, YouTube `streamList` and Kick webhooks into one timeline.
  3. It marks moments with `CreateRecordChapter` or its own timestamps.
  
  This one design works across all three platforms, avoids VOD expiry, and avoids post-hoc VOD muting. Kick, which has no clip or VOD API and possibly no chat replay, is the main reason live ingest is needed.
- Twitch's clip APIs give a compliant fallback for short moments, using `vod_offset` from a detector and Get Clips Download with editor authorisation. The 60 s cap limits it to single moments and it cannot build longer Shorts.
- Copying a browser OAuth token for sub-only VODs is fragile and a poor basis for a product.
- Live chat must be captured while live for Kick. Treat chat as lost if the app was not running.

### Gaps
- Exact Get Videos fields could not be confirmed on Twitch's reference page; the fetch chunks did not reach that section. Units for `muted_segments` are presumed to be seconds.
- Twitch's official retention text was unreadable, so those figures are third-party.
- YouTube live archive limits and DVR window: my attempt hit the wrong help page, so nothing is verified.
- Separate clean-audio tracks in OBS (mic vs game) would help detection and captions, but I did not research this.
- Whether Kick has undocumented or roadmap clip endpoints, and Kick API rate limits, were not found.

## How does vertical reframing work?

### Takeaway
Gaming clips are usually a layout problem, not a tracking problem: find the fixed facecam rectangle once, then stack webcam over gameplay. Speaker tracking is mainly needed for IRL or multi-person content. I found no published method or accuracy data for facecam-region detection.

### Cited Findings
- clipsmith detects the webcam rectangle with an OpenCV Haar cascade, caches it or lets the user set it in config, then builds a 1080x1920 stack with a configurable split (example 0.4) — [clipsmith](https://github.com/ricardogr07/clipsmith)
- ClipsKitty uses YOLOv8 pose to keep the subject centred, TalkNet active-speaker detection in group footage, and crop-only output with no stretching — [clips-studio](https://github.com/ColinGPT9/clips-studio)
- AutoFlip [dated 2020, primary blog]: MediaPipe-based, detects scene cuts by histogram, picks a stationary, panning or tracking strategy per scene, and falls back to letterbox when content does not fit. Google listed speaker detection as future work — [Google Research](https://research.google/blog/autoflip-an-open-source-framework-for-intelligent-video-reframing/)
- Light-ASD (CVPR 2023): 94.1% mAP on AVA-ActiveSpeaker versus 94.2% SOTA, with about 1.0M parameters versus 22.5M and 0.6G versus 2.6G FLOPs [snippet]. Code is on GitHub at Junhua-Liao/Light-ASD — [paper page](https://huggingface.co/papers/2303.04439), [CVPR](https://cvpr.thecvf.com/virtual/2023/poster/22778)
- Splitter names OpenCV YuNet and a YOLOv8s ONNX person detector, noting full-body detection is a more reliable tracking anchor than the face. It clamps the crop to the frame [snippet] — [Splitter](https://shaba-git.duckdns.org/unclshura/splitter/commit/05d203c44668aaaed75e3ad99168e648680e5407)
- Commercial tools fall back to body and pose when face detection fails, and use a plain fill when no camera is present [secondary] — [ClipSpeed](https://www.clipspeed.ai/ai-tools/face-tracking-video-crop.html), [ClipSpeed gaming](https://www.clipspeed.ai/ai-tools/gaming-clip-generator.html)
- Twitch dual-format streams can yield vertical clips natively through Create Clip — [changelog](https://dev.twitch.tv/docs/change-log/)

### Inferences
- Practical facecam locator (my suggestion, not from a source):
  1. Sample about 50 frames across the session.
  2. Run YuNet.
  3. Cluster boxes and keep the stable corner cluster.
  4. Refine the rectangle edges with frame-difference or edge detection.
  5. Cache per channel and scene, and let the user drag to correct.
- For local OBS use, the scene item transform of the webcam source could give the exact rectangle with no vision at all. I did not verify the relevant obs-websocket requests.
- A layout state machine fits: split stack (facecam found), full-frame gameplay crop (no cam), and speaker-tracked crop (IRL). Re-evaluate at scene cuts.
- Gameplay crop needs a per-genre focus. Centre crop suits FPS, but HUD elements and kill feeds get lost.

### Gaps
- No academic or engineering write-up on facecam-region detection or on gaming crop-focus selection.
- TalkNet versus Light-ASD on streamer footage, and CPU latency for Light-ASD, were not found.
- Haar cascade accuracy on stylised or green-screen webcams was not found.

## How are captions made, and how accurate are they on gaming and Hinglish speech?

### Takeaway
The standard stack is faster-whisper or WhisperX with VAD and word timestamps. No gaming-speech WER benchmark was found. For Hinglish, stock Whisper is weak, while fine-tuned Tara (Apache-2.0, Whisper large-v3 base) reports about 8–14% WER on code-switch sets, close to commercial systems. Those numbers come from the model's authors, using clips of 30 s or less.

### Cited Findings

**Stack and timing**
- WhisperX adds VAD and phoneme-level forced alignment for word timestamps, and reports a twelve-fold speedup from batched inference with VAD Cut & Merge — [WhisperX paper](https://arxiv.org/abs/2303.00747)
- WhisperX batched inference runs without timestamps per sample, which can differ from default Whisper output [snippet] — [whisperX README mirror](https://github.com/rootflo/whisperX)
- faster-whisper [primary]:
  - `word_timestamps=True`, `vad_filter=True` via Silero. By default only silence longer than 2 s is removed.
  - Large-v2 on RTX 3070 Ti for 13 minutes of audio: 1m03s fp16, 17s batched at 6,090 MB VRAM, 16s int8 batched at 4,500 MB.
  - The README does not say whether batched mode supports word timestamps — [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- large-v3-turbo: decoder cut from 32 to 4 layers, 809M versus 1.55B parameters. One vendor blog reports 13.40% versus 13.20% WER on long-form audio at 129.5x versus 55.3x real time. Community reports say it hallucinates more on short or noisy clips [secondary, snippet, not opened] — [Whisper Notes](https://whispernotes.app/de/blog/introducing-whisper-large-v3-turbo)
- Open ASR Leaderboard, third-party snapshots that disagree: Parakeet TDT 0.6B v3 about 6.3% versus Whisper large-v3 about 7.2–7.4%. An October 2026 post lists Qwen3-ASR-1.7B at 5.40 and Cohere Transcribe at 5.77 [secondary, snippet, not checked against the leaderboard; I could not pin which listed page carried the October post] — [Pinggy](https://pinggy.io/blog/best_open_source_self_hosted_speech_to_text_models/), [OpenWhispr](https://openwhispr.com/blog/parakeet-vs-whisper-vs-nemotron). Parakeet v3 covers 25 languages versus Whisper's 99+ [snippet]

**Hallucination**
- Calm-Whisper (Interspeech 2025): fine-tuning 3 of 20 decoder heads cuts non-speech hallucination by over 80% with under 0.1% WER degradation on LibriSpeech — [arXiv 2505.12969](https://arxiv.org/abs/2505.12969). On UrbanSound, those heads account for over 75% of hallucinations, and the metric counts any output on non-speech clips [snippet] — [paper](https://arxiv.org/pdf/2505.12969)

**Hinglish and code-switching**
- Tara (Trelis), Hinglish WER [author-run, same protocol for all systems, clips of 30 s or less]:

| Set | Tara | Sarvam Saaras-v3 | ElevenLabs Scribe-v2 |
|---|---|---|---|
| CoSHE-500 (conversational) | 14.41 | 11.25 | 12.40 |
| CS-FLEURS hi-en (read) | 8.37 | 16.47 | 7.57 |
| HiACC adult | 12.93 | 13.16 | 12.87 |

  Apache-2.0, Whisper large-v3 base. No stock Whisper comparison on the page — [Tara](https://huggingface.co/Trelis/tara)
- HiACC's authors say Whisper and Google's multilingual models struggle with spontaneous code-switching [snippet] — [HiACC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12329218/)
- Vaani Hindi benchmark reports 34.1 WER for Whisper-large-v3, with worse results on background speech. The setup is unclear and this is not a clean Hinglish score [snippet] — [Vaani](https://arxiv.org/pdf/2606.21408)
- Deepgram says Hinglish WER spans 26.97–69.53% across models on identical audio. It is a vendor source and the dataset is not named in that statement (2026-05-28) — [Deepgram](https://deepgram.com/learn/hinglish-voice-ai-speech-recognition)
- Small-model data point: PolyWhisper reports 58.8% versus 66.6% for vanilla Whisper-Base on its own 3,129-utterance test set [snippet] — [PolyWhisper](https://github.com/eulogik/PolyWhisper/releases)

### Inferences
- WER figures are not comparable across these sources because normalisers and test sets differ. Tara's 14.41 on conversational speech is the most relevant Hinglish number, and real streams with game audio will likely be worse.
- Default recipe: VAD on, word timestamps on, a forced-alignment pass if using batching, and a transcript editor in the UI. Non-speech game audio is a direct hallucination risk, so VAD gating is the cheapest defence.
- Gaming vocabulary (agent names, callouts, usernames) is a known-unknown. Prompt biasing with a per-game glossary is worth testing, but I have no evidence on its benefit.
- For Hinglish creators, Tara is a credible local option, with Scribe or Sarvam as paid comparators. Test it on real stream audio first.

### Gaps
- No WER benchmark on gaming or streamer speech (overlapping game audio, shouting, slang) was found.
- Output script for Tara (Devanagari, Roman or mixed) and its word-timestamp behaviour were not confirmed. This matters a lot because Hinglish captions are usually read in Roman script.
- No measured word-timing error for WhisperX or Whisper on noisy audio. Figures on secondary sites (sub-100 ms, 1–3 s drift) are unsourced and conflict, so they are excluded.
- SwitchLingua results were not retrieved.

## What are the publishing APIs, limits and rules (YouTube Shorts, TikTok, Reels), and what do platform terms say about downloading or clipping?

### Takeaway
YouTube changed sharply this month: since 2026-11-02, uploads from unverified projects are no longer forced private, so most 2020–2026 guides are now stale. The real YouTube limit is 100 `videos.insert` calls per day per project, across all users, until an audit raises it. TikTok is the hardest gate: `SELF_ONLY` until audited, and its guidelines favour authentic creators posting original content. A creator-owned tool fits these rules far better than a third-party clip farm.

### Cited Findings

**YouTube Shorts** [primary]
- Unverified projects: "are not restricted to private viewing mode" as of 2026-11-02, reversing the 2020-07-28 rule. Omitted `privacyStatus` defaults to public, though some accounts default private — [revision history](https://developers.google.com/youtube/v3/revision_history), [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)
  - This is four days old. Third-party guides still state the old rule — [Activepieces](https://www.activepieces.com/blog/youtube-api-quota-exceeded-how-to-fix-and-avoid-it), and the [clips-studio README](https://github.com/ColinGPT9/clips-studio).
- Quota history: about 1,600 units [old], then about 100 on 2025-12-04, then a granular system on 2026-06-01 — [revision history](https://developers.google.com/youtube/v3/revision_history)
- Current costs: `videos.insert` 1 unit in its own bucket, default 100 calls per day; `search.list` likewise; `videos.update` and `thumbnails.set` 50 units; general pool 10,000 units per day; reset at midnight PT — [quota table](https://developers.google.com/youtube/v3/determine_quota_cost)
- More quota requires a compliance audit through the Audit and Quota Extension Form. The page does not address uploads specifically — [quota and compliance audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits)
- `videos.insert`: 256 GB maximum; `youtube.upload` among accepted scopes; `uploadLimitExceeded` is a per-user limit error — [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)
- Shorts definition: up to 3 minutes and square or vertical; classification follows those attributes for uploads after 2024-10-15 — [YouTube Help](https://support.google.com/youtube/answer/15424877)
- Custom Shorts thumbnails are allowed after processing, with `shortsAspectRatio` added 2026-11-03 — [revision history](https://developers.google.com/youtube/v3/revision_history)
- Any Short over one minute with an active copyright claim of any type is blocked globally: not playable, not recommended, not monetisable, with no channel penalty. Shorts under one minute are not affected by this rule — [YouTube Help](https://support.google.com/youtube/answer/15424877)
- Monetisation policy:
  - Reused content is judged on whether there is "a meaningful difference" from the original, and the policy "applies even if you have permission from the original creator".
  - Not allowed: clips edited together with little or no narrative; short videos compiled from social sites; promoting others' content, even with permission.
  - Allowed: critical review, reaction with commentary, and edited footage with storyline and commentary.
  - Violations can remove monetisation from the entire channel.
  - On 2025-07-15, "repetitious" was renamed "inauthentic content", which covers template-like, mass-produced work including generic AI content — [YouTube Help](https://support.google.com/youtube/answer/1311392)

**TikTok Content Posting API** [all snippet or quoted; direct fetch failed with 503]
- Unaudited clients: "can only post contents in `SELF_ONLY` viewership" and "up to 5 users to post in a 24 hour window" — [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines), quoted in [AdaptlyPost](https://adaptlypost.com/de/blog/why-does-my-app-need-approval-post-tiktok). Those accounts must be private when posting — [Postiz docs](https://docs.postiz.com/self-host/providers/tiktok.md)
- Per-creator cap via Direct Post: typically around 15 posts per day, shared across all API clients. Direct Post needs the `video.publish` scope — [guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines), [Direct Post reference](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post). A limit of 6 requests per minute per user token is quoted second-hand — [AdaptlyPost](https://adaptlypost.com/de/blog/why-does-my-app-need-approval-post-tiktok)
- Intended use:
  - "API Clients should facilitate authentic creators to post original content to TikTok."
  - Listed as not acceptable: "A utility tool to help upload contents to the account(s) you or your team manages" — [guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines)
  - A second-hand quote adds "an app that copies arbitrary contents from other platforms to TikTok" as not acceptable. I could not verify this on TikTok's page — [Feedloop](https://feedloophq.com/blog/rss-to-tiktok-auto-publish-2026)
- UX audit points:
  - Preview before upload and express consent.
  - Privacy chosen manually with no default.
  - Commercial disclosure off by default.
  - No app watermark, logo, link or promotional text on the content.
  - Demo video of the full flow — [guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines), [AdaptlyPost](https://adaptlypost.com/de/blog/why-does-my-app-need-approval-post-tiktok)
- Audit outcomes: real rejections cite UX guideline failures — [Postiz issue 1563](https://github.com/gitroomhq/postiz-app/issues/1563). Feedloop reports two rejected attempts — [Feedloop](https://feedloophq.com/blog/rss-to-tiktok-auto-publish-2026). App review may take several days to two weeks, and TikTok gives no audit timeframe — [AdaptlyPost](https://adaptlypost.com/de/blog/why-does-my-app-need-approval-post-tiktok). Private posts stay private after audit (quoted FAQ, search summary) — [AdaptlyPost](https://adaptlypost.com/de/blog/why-does-my-app-need-approval-post-tiktok)
- Upload to inbox ("upload without posting") sends media to the user's TikTok inbox, and the owner must finish within 24 h or it is discarded — [Postiz docs](https://docs.postiz.com/self-host/providers/tiktok.md). At most 5 pending shares in 24 h — [upload reference](https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video)
- Media transfer: `PULL_FROM_URL` needs a verified domain or URL prefix, HTTPS, no redirects, and a 1-hour download timeout. `FILE_UPLOAD` uses 1–1000 sequential chunks. Error: `url_ownership_unverified`. A 4 GB figure appeared in an ambiguous context, so confirm it — [media transfer guide](https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide)
- The Direct Post reference shows a last update of 2026-08-04 [snippet] — [reference](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post)

**Instagram Reels** [primary]
- Requires a professional account. Permissions depend on login type, for example `instagram_business_basic` and `instagram_business_content_publish`. Page Publishing Authorization can block publishing — [content publishing guide](https://developers.facebook.com/docs/instagram-platform/content-publishing/)
- Post cap conflict: the guide says 100 API posts per 24 h moving window in one place and 50 in the carousel section. The IG User Media reference is reported as 50 [snippet]. Check live with `GET /<IG_ID>/content_publishing_limit` — [guide](https://developers.facebook.com/docs/instagram-platform/content-publishing/), [IG User Media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media)
- Containers: 400 per rolling 24 h per account, expiring after 24 h — [IG User Media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media)
- Reel specs — [IG User Media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media):
  - MOV or MP4, moov atom at front, no edit lists.
  - HEVC or H.264, closed GOP, 4:2:0, 23–60 FPS, maximum width 1920.
  - VBR 25 Mbps maximum; AAC up to 48 kHz, 128 kbps.
  - 3 s to 15 min; 300 MB maximum; 9:16 recommended.
- Upload: media must sit on a public URL that Meta fetches, or use resumable upload via `rupload.facebook.com` (the guide scopes this to Facebook Login for Business). Poll `status_code` about once a minute for up to 5 minutes. Trial Reels are supported through `trial_params` — [guide](https://developers.facebook.com/docs/instagram-platform/content-publishing/)
- Permission review needs a screencast and takes an estimated 2–4 weeks [secondary, estimate] — [Postproxy](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/)

**Platform terms on downloading and clipping**
- YouTube API policies [primary]: no download, cache or storage of audiovisual content without approval (III.E.1); no scraping (III.E.6); do not "separate, isolate, or modify the audio or video components" (III.I.7); no redistribution (III.G.1.a); most stored API data capped at 30 days (III.E.4). The page says nothing about AI or ML — [Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- YouTube ToS: no download except as expressly authorised or with written permission, and no automated access such as scrapers. The fetched copy is dated 2022-01-05, which may be region-specific — [YouTube Terms](https://www.youtube.com/t/terms)
- Twitch Developer Services Agreement: "Do not store copies of Twitch Content or Program Materials, unless you" meet an exception, including "(c) cache such information for only a twenty-four hour time period". Quoted in a July 2025 forum thread; I could not read the current agreement directly — [Twitch dev forum](https://discuss.dev.twitch.com/t/storage-of-data-from-twitch-api/63884)
- Twitch staff in that thread said keeping user data with OAuth permission is compliant ("for your users' benefit"). The thread concerns data, not explicitly video — [Twitch dev forum](https://discuss.dev.twitch.com/t/storage-of-data-from-twitch-api/63884). "Twitch Content" is defined to include video [snippet, older agreement version] — [DSA](https://legal.twitch.com/en/legal/developer-agreement/20191511)
- Kick ToS [primary]: prohibits copying "including by any automated or non-automated 'scraping'" (1.4a), automated systems (1.4b), access by unauthorised means (1.4k), and bypassing restrictions (1.4l). Others' User Content counts as Company Content (s.3). Spam or "machine-generated content" uploads are barred (1.4q). No clip or AI clause. No specific developer terms were found — [Kick Terms](https://kick.com/terms-of-service)
- Twitch music: clips with identified music have been deleted, and Soundtrack by Twitch does not carry into clips or VODs [dated 2020, snippet] — [Twitch blog](https://blog.twitch.com/en/2020/11/11/music-related-copyright-claims-and-twitch/). Rights holders can have VODs or clips removed or muted [snippet] — [Twitch music process](https://twitch.tv/p/en/legal/dmca-guidelines/music-reporting-process)

### Inferences
- A hosted multi-user app shares one 100-uploads-per-day YouTube bucket across all users, so scale needs an audit. A local app where each user brings their own Google project (as ClipsKitty does) sidesteps that but adds setup friction.
- Do not build a default free-tier "made with" watermark into TikTok-bound output; the guidelines bar it.
- The strongest position is a creator publishing their own stream clips with explicit per-post review. A clipper-network or auto-post-everything design runs into TikTok's intended-use language and YouTube's reused-content policy. "Utility tool for accounts you manage" may also catch agency-style features, so plan TikTok upload-to-inbox as a fallback.
- Keep Shorts under 60 s by default when game or background music is present, since a claim on anything longer blocks the Short globally.
- Encode one master that fits the tightest spec (H.264, AAC, moov at front, closed GOP, under 300 MB, 9:16) so a single render serves all three platforms. This is my synthesis of the specs above; TikTok's specs were not confirmed.
- YouTube's Developer Policies govern API clients. A tool that processes the creator's own local recording never touches YouTube-hosted content, so III.E.1 should not arise. This is not legal advice.

### Gaps
- TikTok official pages were unreachable (503), so exact current wording, video specs, the 4 GB limit and `spam_risk` error details are unconfirmed.
- No Meta policy found specific to third-party or reposted content through the API. Originality rules for Reels recommendation were not researched.
- No explicit Twitch or Kick rule found on whether a third party may repost clips, and no Eklipse or vendor terms were reviewed.
- Current full text of the Twitch Developer Services Agreement is unread, including any AI clause.
- Meta's official review timelines were not found.
- Whether YouTube's Nov 2026 change alters audit expectations for other purposes is not stated. The quota audit page still applies to extensions.
