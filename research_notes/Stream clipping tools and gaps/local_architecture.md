# Local-first architecture for a stream clipping desktop app (Windows 10/11, solo developer)

Research date: 2026-11-06. Sources were read through fetch and search tools that summarise pages, so quoted strings are close to the source but should be re-checked before they go into licence or legal decisions. "Derived" means I calculated the figure from a cited number. Anything with no citation is in Inferences or Gaps.

Source quality: OBS, NVIDIA, FFmpeg LICENSE, GitHub READMEs and model cards are primary. Most speed figures for specific consumer GPUs are secondary or unmeasured, and each is flagged.

## How does OBS integration work (obs-websocket v5, replay buffer, recording events, chapters, multi-track audio, formats, reading a growing file)?

### Takeaway
obs-websocket v5 covers everything needed: replay buffer control, record state events, chapters and file splitting. The safest way to process during a stream is to rotate recordings with `SplitRecordFile` and only read closed segments, because I found no OBS statement that a file can be read while it is being written. Chapters are useful only as a convenience, because they are lost if OBS crashes and they work only in Hybrid MP4/MOV.

### Cited Findings
**Protocol**
- `SaveReplayBuffer`, `StartReplayBuffer`, `GetReplayBufferStatus`, `GetLastReplayBufferReplay` (returns `savedReplayPath`), `StartRecord`, `StopRecord` (returns `outputPath`), `ToggleRecordPause` and `GetRecordStatus` (active/paused, timecode, duration, bytes) were all added in v5.0.0 — [obs-websocket protocol](https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md)
- `SplitRecordFile` and `CreateRecordChapter` were added in v5.5.0. The doc note for chapters says "As of OBS 30.2.0, the only file format supporting this feature is Hybrid MP4." That note predates Hybrid MOV (see below) — [protocol](https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md)
- `ReplayBufferSaved` carries `savedReplayPath`. `RecordStateChanged` carries `outputActive`, `outputState` and `outputPath`, but the path is the saved file name after recording stops and `null` otherwise. `RecordFileChanged` (v5.5.0) carries `newOutputPath`, the file the recorder has started writing to, for example after a split — [protocol](https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md)
- Event subscriptions are a bitmask set in Identify/Reidentify. Categories include Outputs, General and Canvases (v5.7.0). High-volume events such as `InputVolumeMeters` need explicit opt-in. RPC version is 1. Auth is a salted SHA-256-style challenge; failures close with code 4009 — [protocol](https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md)

**Formats**
- OBS 32.0 (22 September 2025): "Hybrid MP4/MOV is now out of beta and has been made the default output format for new profiles." It also "Improved accuracy of chapter markers", fixed "Hybrid MP4 file splitting not working correctly in some cases", and added Hybrid MOV with an HEVC/H.264 + PCM option — [OBS 32.0 release notes](https://obsproject.com/blog/obs-studio-32-0-release-notes)
- Hybrid MP4 first shipped in beta in OBS 30.2 — [OBS 30.2 notes](https://obsproject.com/blog/obs-studio-30-2-release-notes)
- Because the default applies to new profiles, older profiles keep their format (for example MKV). That is the release-note wording plus a third-party reading — [OBS 32.0 notes](https://obsproject.com/blog/obs-studio-32-0-release-notes); [obs-versions.com comparison](https://obs-versions.com/blog/obs-mkv-vs-mp4-hybrid-mp4)
- Hybrid MP4 is written as a fragmented file, "then being finalised like a regular MP4/MOV in a process we call 'soft-remux'". It "remains recoverable even if writing the file is aborted" — [OBS KB: Hybrid MP4](https://obsproject.com/kb/hybrid-mp4)
- "Chapters are written during the finalisation process, i.e. they are not recoverable in the event of a crash." Chapters can be added by hotkey, WebSockets or the frontend API — [OBS KB](https://obsproject.com/kb/hybrid-mp4)
- Hybrid MP4 supports AV1, Opus and FLAC. PCM in MP4 is "not supported in all applications", so Hybrid MOV may suit PCM better — [OBS KB](https://obsproject.com/kb/hybrid-mp4)
- A forum user reported that a Hybrid MP4 left by an OBS crash played in VLC but would not import into Resolve or Premiere; the suggested fix was File > Remux Recordings — [OBS forum](https://obsproject.com/forum/threads/issue-with-new-hybrid-mp4-files.179021/latest)

### Inferences
- **Design: rotate, then process.** Call `SplitRecordFile` on a timer (for example every 5 to 10 minutes), listen for `RecordFileChanged`, and queue the previous path once it is closed. This avoids depending on growing-file behaviour. Require OBS 32.0 or later because of the Hybrid MP4 split fix. Test whether a split causes a dropped frame or an audio gap at the boundary; I found no data on that.
- **Do not rely on chapters as the only marker store.** Write your own timestamp log (wall clock plus `GetRecordStatus` timecode) to SQLite when a hotkey or detector fires, and use `CreateRecordChapter` only as a mirror. This survives crashes, which chapters do not.
- `RecordStateChanged.outputPath` is `null` during recording, so the app cannot learn the live file name from that event at start. Use `RecordFileChanged` after the first split, or watch the recording folder.
- Offer two capture modes. **Replay buffer mode** (`SaveReplayBuffer` on a hotkey or detector, then read `savedReplayPath`) gives closed files and is simple. **Full recording mode** gives whole-stream analysis after the stream. Both give the app files it can process without touching the encoder.
- The app should read `GetRecordStatus`/profile settings on connect and warn about MKV profiles if chapters are wanted, and about crash-damaged Hybrid files.

### Gaps
- I found no OBS statement on opening a Hybrid MP4 or MKV while it is being written, and no test of FFmpeg reading one. The KB page is silent. Test `ffmpeg -i` and `ffprobe` on a live file on Windows, including file-sharing locks. The fragmented layout suggests it may work, but this is unconfirmed.
- The OBS multi-track audio details (number of tracks, per-format limits, how tracks map in Hybrid MP4) were not found in the pages I read. The KB does not mention audio tracks. The OBS 30.2 multi-track item concerns Enhanced RTMP streaming, not recording. Verify by test: mic on one track and game on another is the main value, because it gives clean speech for ASR and an isolated music track for fingerprinting.
- I did not confirm request names for finding the record directory or reading OBS stats (`GetRecordDirectory`, `GetStats` from memory). Check them in the protocol doc.
- I did not find the current OBS Studio version as of November 2026; 32.0 is the last release I confirmed.

## How much do NVENC sessions and GPU load matter while streaming, how do AMF and QSV compare, and how should ML run alongside a game?

### Takeaway
The session count is no longer the constraint: NVIDIA's current documents point to 12 sessions per system on consumer cards. The real risk is contention for the 3D/CUDA engines that the game and OBS compositing need, and I found no measurement of Whisper running beside a game. So the live mode should be CPU-only and light, and heavy work should wait until after the stream, with GPU use during a stream as an opt-in.

### Cited Findings
- "On non-qualified GPUs, the number of concurrent encode sessions is limited to 12 per system", shared across all non-qualified cards in the system — [NVENC Application Note, SDK 13.1](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/nvenc-application-note/index.html)
- NVIDIA's support matrix, as read through a fetch tool, lists 12 concurrent sessions for GTX 1660, RTX 3060, RTX 4070, RTX 5070 and RTX 5090 — [NVIDIA support matrix](https://developer.nvidia.com/video-encode-decode-support-matrix)
- **Older information, superseded:** the 2023-era limit was 5, raised from 3 — [Tom's Hardware](https://www.tomshardware.com/news/nvidia-increases-concurrent-nvenc-sessions-on-consumer-gpus). An "8 sessions" figure also appears — [Emby forum thread](https://emby.media/community/topic/131781-nvidia-geforce-gpus-now-support-up-to-8-concurrent-encoding-sessions). Older drivers may still enforce the lower limits; I found no driver-to-limit table.
- NVENC "is independent of graphics/CUDA cores", "a dedicated block on GPU silicon die". The note does not quantify how NVENC throughput changes under graphics or CUDA load — [NVENC Application Note](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/nvenc-application-note/index.html)
- A single session cannot exceed one NVENC engine's throughput unless Split Frame Encoding is on; multi-engine cards add throughput only across several sessions — [NVENC Application Note](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/nvenc-application-note/index.html)
- OBS forum staff attribute many overloads to a saturated GPU: an uncapped game maxes the GPU and hurts OBS, so cap frame rate — [OBS forum](https://obsproject.com/forum/threads/encoding-overloaded-because-of-gpu.71497/latest). These are moderator opinions, not measurements. Task Manager's encoder figure can look low during reported overloads — [OBS forum](https://obsproject.com/forum/threads/encoder-overloaded-but-only-using-10-of-my-encoder.148994)
- Intel: no defined limit on simultaneous QuickSync encodes; the practical limit depends on hardware and software — [Intel support](https://www.intel.com/content/www/us/en/support/articles/000088556.html)
- FFmpeg exposes `h264_amf`, `hevc_amf`, `av1_amf`; I found no published AMF session limit — [Fora Soft glossary](https://www.forasoft.com/learn/video-encoding/glossary/terms/amf) (secondary)
- GPU process priority is a Windows attribute set through `D3DKMTSetProcessSchedulingPriorityClass`; classes run from Real-time to Idle — [windows-docs-rs](https://microsoft.github.io/windows-docs-rs/doc/windows/Wdk/Graphics/Direct3D/fn.D3DKMTSetProcessSchedulingPriorityClass.html); [Bitsum](https://bitsum.com/?p=986585)
- A Sunshine-fork commit uses High on NVIDIA rather than Realtime; its comment says Realtime could freeze or crash the NVIDIA driver, more often with HAGS, DX12 games or nearly full VRAM. A failed call warns the user to run as administrator — [Apollo commit](https://izackpgit.duckdns.org/izackp/Apollo/commit/6dfe56518cb8295e74e3e4aef0bc771a3c333c1e) (mirror of a third-party project, not OBS)

### Inferences
- A post-stream FFmpeg export using one or two NVENC sessions is safe on session count. During a stream, the app's export would still share the single engine with OBS on most cards, so **do not run hardware exports during a stream by default**.
- **Live mode (default):** CPU-only, using audio-only analysis on low-rate features, loudness, chat rate and hotkeys, and optionally a small ASR model. Use below-normal process priority and a limited thread count. Keep VRAM use at zero.
- **Opt-in GPU live mode:** only on cards with VRAM to spare, using int8 models and small batches, with the app's GPU priority set low. Back off when OBS reports rendering or encoding lag. Never raise priority to Realtime.
- A **governor** matters more than the exact model: poll OBS stats, and pause all analysis if skipped or lagged frames rise, then resume after the stream. Because segments are queued on disk, pausing loses nothing.
- Lowering the GPU priority of your own process is a plausible control, but its effect on CUDA is unproven.

### Gaps
- **No measurement found** of Whisper or any CUDA ML workload running next to a game plus NVENC: no frame-time, OBS dropped-frame or game FPS data. Run your own test matrix (game at cap and uncapped, x OBS NVENC, x ASR off/CPU/GPU), logging OBS skipped frames and game 1% lows.
- No source confirms that a Windows GPU priority class applies to CUDA compute, or behaves the same across NVIDIA and AMD drivers or with HAGS on.
- No confirmed answer on whether OBS sets its own GPU priority. Check OBS source.
- No current AMD AMF session limit, and no 2026 AV1 quality comparison across NVENC, AMF and QSV. The one quality comparison I found was old and unclear, so I left it out.
- One fetched row listed the RTX 5090 as "1 chip, 3 total NVENC", which reads oddly. Re-read the matrix directly before quoting engine counts.

## What are the speeds and memory needs of faster-whisper, whisper.cpp and newer speech models on typical streamer hardware, and how do they handle Hindi/English code-switching?

### Takeaway
Post-stream transcription of a multi-hour stream on an 8 GB-class GPU is a minutes-long job, and CPU-only is workable with smaller models. Stock Whisper large-v3 is weak on Hinglish (about 30% WER on one conversational set) while a Hinglish fine-tune reaches about 14%, so a Hindi-capable fine-tune matters more than engine choice. Parakeet and Canary do not cover Hindi, and Qwen3-ASR has Hindi but no Hindi word timestamps.

### Cited Findings
**Measured numbers (13-minute clip; RTX 3070 Ti 8 GB, CUDA 12.4; i7-12700K with 8 threads; faster-whisper v1.1.0 era)** — [faster-whisper README](https://github.com/SYSTRAN/faster-whisper)

| Setup | Time | Memory | Speed vs real time (derived) |
|---|---|---|---|
| large-v2 fp16, beam 5 | 1m03s | 4525 MB VRAM | about 12x |
| large-v2 fp16, batch 8 | 17s | 6090 MB VRAM | about 46x |
| large-v2 int8 | 59s | 2926 MB VRAM | about 13x |
| large-v2 int8, batch 8 | 16s | 4500 MB VRAM | about 49x |
| whisper.cpp large-v2 fp16, flash attention | 1m05s | 4127 MB VRAM | about 12x |
| small, CPU int8 | 1m42s | 1477 MB RAM | about 7.6x |
| small, CPU int8, batch 8 | 51s | 3608 MB RAM | about 15x |
| small, whisper.cpp CPU fp32 | 2m05s | 1049 MB RAM | about 6.2x |
| small, whisper.cpp OpenVINO fp32 | 1m45s | 1642 MB RAM | about 7.4x |

**Other numbers**
- large-v3-turbo in faster-whisper: float16 about 19.2 s and 2537 MB VRAM; int8 about 19.6 s and 1545 MB. The GPU and clip length were not visible in what I read — [faster-whisper issue #1030](https://github.com/SYSTRAN/faster-whisper/issues/1030)
- Turbo keeps the large-v3 encoder and cuts the decoder from 32 layers to 4 — [Whisper Notes](https://whispernotes.app/blog/introducing-whisper-large-v3-turbo) (secondary)
- RTX 4070, large-v3: faster-whisper about 12x real time, whisper.cpp CUDA about 8x — [PromptQuorum](https://www.promptquorum.com/de/power-local-llm/local-whisper-stt-comparison-2026) (secondary; method unclear)
- whisper.cpp memory: tiny about 273 MB, base 388 MB, small 852 MB, medium 2.1 GB, large 3.9 GB. Backends include CUDA, Vulkan and OpenVINO. Silero VAD is supported. MIT licence — [whisper.cpp README](https://github.com/ggml-org/whisper.cpp)
- faster-whisper is MIT and needs cuBLAS for CUDA 12 and cuDNN 9. On Windows the README points to Purfview's archive for those libraries; the pip NVIDIA packages route is listed as Linux only. Audio decoding uses PyAV, so no FFmpeg binary is required — [faster-whisper README](https://github.com/SYSTRAN/faster-whisper)
- distil-large-v3 is the README's recommended distil model, used with `language="en"` — [faster-whisper README](https://github.com/SYSTRAN/faster-whisper). That makes it unsuitable for Hindi.

**Hindi/English code-switching (corpus WER, self-reported, custom `indic-hindi` normaliser; a research preview, "Numbers and weights may change")** — [Trelis whisper-hinglish-preview](https://huggingface.co/Trelis/whisper-hinglish-preview)

| Test set | whisper-hinglish-preview | Sarvam (cloud) | Scribe-v2 (cloud) | whisper-large-v3 |
|---|---|---|---|---|
| CoSHE-500 (conversational) | 13.67 | 11.47 | 12.43 | 29.74 |
| cs-fleurs (read) | 10.19 | 16.47 | 7.57 | 33.92 |
| hiacc-adult | 12.73 | 14.44 | 16.98 | 28.53 |
| FLEURS-hi | 12.57 | 10.07 | 11.33 | 27.50 |
| FLEURS-en | 6.93 | 5.14 | 4.01 | 4.81 |

- That model is Apache-2.0 per its tag, and outputs each language in its native script. It recommends a `<|mixedcode|>` token and an explicit language tag. Its page says WER figures are not comparable with other sources, and its model tree conflicts with its description on base model — [model card](https://huggingface.co/Trelis/whisper-hinglish-preview)
- Tara is another large-v3 derivative, reporting 8.37 WER on Code-Switch FLEURS (maintainer-reported) — [Trelis/tara](https://huggingface.co/Trelis/tara)
- Oriserve Whisper-Hindi2Hinglish is a large-v3 fine-tune on about 550 hours of Indian-accented Hindi, Apache 2.0, self-reported results — [Oriserve](https://oriserve.com/blog/oriserve-open-sources-india-focused-ai-speech-model-fine-tuned-on-whisper)
- Vaani Benchmark (June 2026) reports higher Whisper-large-v3 WER on background speech; I could not verify headline numbers — [arXiv 2606.21408](https://arxiv.org/pdf/2606.21408)

**Newer models**
- Qwen3-ASR-1.7B: Apache-2.0, Hindi is among its 30 languages, no Hindi-specific WER given. Timestamps need Qwen3-ForcedAligner-0.6B, which covers 11 languages, and Hindi is not one of them. Examples use CUDA; Windows is not mentioned — [model card](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
- Parakeet TDT v3: 25 European languages, no Hindi, CC-BY-4.0. Canary-Qwen 2.5B: English only, CC-BY-4.0 — [Pinggy, October 2026](https://pinggy.io/blog/best_open_source_self_hosted_speech_to_text_models/) (secondary; check the live leaderboard)

### Inferences

| Hardware | Suggested post-stream setup | Basis |
|---|---|---|
| CPU only | small int8 (or base), about 1.5 to 3.6 GB RAM; a 4-hour stream is about 16 to 32 minutes on a 12700K-class CPU (derived, using all 8 threads) | README |
| GTX 1660 (6 GB) | large-v3-turbo or a fine-tune at int8, batch 1 to 4; VRAM fits on paper; **speed unmeasured** | VRAM figures only |
| RTX 3060 (12 GB) | large-v3-class int8 or fp16 batched; **speed unmeasured**; likely below the 3070 Ti rows | Proxy only |
| RTX 4070 (12 GB) | Same as 3060, batched; about 12x sequential is secondary data | PromptQuorum |

- On the 3070 Ti, a 4-hour stream takes about 5 minutes at batch 8 and about 20 minutes sequentially (derived). Long-audio overheads such as VAD and decoding are not included.
- **Recommended stack:** faster-whisper as the NVIDIA path, because it has the batched pipeline; whisper.cpp with Vulkan as the AMD/Intel/no-CUDA path, because it avoids shipping CUDA and has a CPU path. Use a Hinglish fine-tune for Indian streamers and stock turbo for others. Convert the fine-tune to CTranslate2 and GGML formats and re-measure WER after conversion.
- Use word timestamps from the Whisper path for captions, because Qwen3-ASR's aligner does not cover Hindi. Script output (Devanagari plus Latin) needs a font and libass test for burned-in captions.
- The Hinglish numbers come from clean-ish test sets. Streams with game audio will score worse, so transcribe the mic track where one exists.

### Gaps
- **No measured** faster-whisper or whisper.cpp numbers for GTX 1660, RTX 3060 desktop, or RTX 4070 from a primary source. No Vulkan benchmark of whisper.cpp large-v3-turbo. Run `whisper-bench` and a fixed 13-minute clip on each card. A laptop RTX 3060 figure (46.1 s) has no stated clip length, so I left it out of the table — [Whisper Notes](https://whispernotes.app/blog/introducing-whisper-large-v3-turbo)
- GTX 16-series fp16 behaviour is unconfirmed. From memory only, these cards lack tensor cores, so fp16 may offer little gain; `int8_float16` or `int8` must be tested.
- No independent peer-reviewed Hinglish benchmark on streaming or gaming audio was found. All WERs above are vendor or maintainer reported.
- No confirmation that `<|mixedcode|>` works after conversion to CTranslate2 or GGML. The "2B parameters, F32" description on the Trelis page may also mean a larger download than stock Whisper.
- Tara's licence was not checked. The OpenAI Whisper weights licence (MIT from memory) was not opened.
- The newest open models (for example Nemotron 3.5 Transcribe, Voxtral) were not checked for Hindi or licence fit — [Apidog](https://apidog.com/blog/best-open-source-speech-to-text-models/)

## What are the best local options for audio event detection, face detection, OCR and music fingerprinting?

### Takeaway
All four fit on CPU, and only YAMNet-class audio tagging is worth running live; the rest should run after the stream, on candidate clips only. Pick YAMNet first, YuNet or BlazeFace for faces, RapidOCR for OCR. Chromaprint is a weak fit: it is tuned for clean music, and the free AcoustID service bars commercial use.

### Cited Findings
**Audio events**
- YAMNet: 521 classes, about 3.7M weights, 69.2M multiplies per 960 ms frame, balanced mAP 0.306 on AudioSet eval — [YAMNet README](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/README.md). An ONNX port is listed as Apache-2.0 — [Transcriptor sound models](https://huggingface.co/arnoldatse/transcriptor-sound-models)
- PANNs: best system mAP 0.439 on AudioSet tagging — [PANNs paper](https://arxiv.org/abs/1912.10211v2). Code MIT, CNN14 weights CC BY 4.0 per a third-party repackager — [Transcriptor sound models](https://huggingface.co/arnoldatse/transcriptor-sound-models)
- BEATs lives in Microsoft's unilm repo, whose root licence is MIT — [unilm LICENSE](https://raw.githubusercontent.com/microsoft/unilm/master/LICENSE)

**Faces**
- YuNet: 1.45 ms on an Intel CPU at 160x120 per OpenCV Zoo — [OpenCV Zoo mirror](https://github.com/Ir1d/opencv_zoo). About 9.21 ms per 1280x720 image for INT8 in one blog test — [DEV Community](https://dev.to/kiarina/high-speed-face-detection-and-scale-invariance-with-opencv-yunet-4m7f)
- YuNet WIDER Face AP 0.834/0.824/0.708 (easy/medium/hard), MIT per a redistribution; the dynamic-input build needs ONNX Runtime or OpenCV 5 — [pollen-robotics](https://huggingface.co/pollen-robotics/face_detection_yunet_2026may). OpenCV DNN does not support the latest dynamic-shape version — [libfacedetection](https://awesome.ecosyste.ms/projects/github.com%2Fshiqiyu%2Flibfacedetection)
- Small faces get missed unless the frame is upscaled — [DEV Community](https://dev.to/kiarina/high-speed-face-detection-and-scale-invariance-with-opencv-yunet-4m7f). This matters for small webcam overlays.
- BlazeFace (MediaPipe): model card lists Apache 2.0 — [BlazeFace card mirror](https://huggingface.co/langminer/blaze-face-full-range)

**Windows GPU runtime**
- ONNX Runtime docs place DirectML in sustained engineering: still supported, with new feature work going to WinML — [ONNX Runtime DirectML EP](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html). A third-party page says "maintenance mode" and Windows 11 24H2 or later for Windows ML — [aggregator](https://theresanaiforthat.com/company/microsoft/repository/DirectML/)
- Windows ML includes CPU and "DirectML (legacy)" EPs; vendor EPs download separately — [Microsoft Learn](https://learn.microsoft.com/en-in/windows/ai/new-windows-ml/supported-execution-providers)

**OCR**
- 60 images of 1180x92 on a Core Ultra 9 285K: RapidOCR 3.8.1 with OpenVINO about 18.0 s, PaddleOCR 3.5.0 about 62.7 s, RapidOCRSharpOnnx about 9.2 s, using PP-OCRv5 mobile models — [RapidOCRSharpOnnx](https://www.nuget.org/packages/rapidocrsharponnx) (informal, one machine). That is about 0.15 to 0.3 s per strip (derived); full frames will cost more.
- PP-OCRv5's recognition model has a larger dictionary and is slower than v4 — [PaddleOCR docs](https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html). PP-OCRv6 models exist in the onnxocr package — [PyPI](https://pypi.org/project/onnxocr/4.0.0/)

**Music fingerprinting**
- Chromaprint's own code is MIT but it includes FFmpeg parts, so "as a whole" it "should be therefore considered to be licensed under the LGPL 2.1 license". Check the licence of the FFT library it is built with — [Chromaprint LICENSE](https://raw.githubusercontent.com/acoustid/chromaprint/master/LICENSE.md)
- AcoustID: "provided for free for non-commercial use only"; commercial apps sign up through acoustid.biz; limit of 3 requests per second; lookups return MusicBrainz metadata — [AcoustID web service](https://acoustid.org/webservice)
- Commercial pricing appears as 100 EUR a month for 15M searches in an unofficial mirror — [API Evangelist mirror](https://raw.githubusercontent.com/api-evangelist/acoustid/refs/heads/main/plans/acoustid-plans-pricing.yml). Confirm at acoustid.biz.
- Chromaprint is "optimized for musical content" and not designed for microphone-style added noise (2011 mailing-list comments, old and informal) — [AcoustID group](https://groups.google.com/g/acoustid/c/OQ4332mbhF0/m/L8XHAMaBuI8J)
- Secondhand claim: Chromaprint struggles on segments under 15 seconds — [MetaBrainz forum](https://community.metabrainz.org/t/what-can-be-done-with-super-polluted-acoustids/712151/48)
- Background-music matching is hard for all fingerprinting systems: the BAF work reports low recall for tested systems (Chromaprint was not in that table) — [ISMIR 2022 poster](https://ismir2022program.ismir.net/static/posters/228.pdf)

### Inferences
- **Live:** YAMNet on 960 ms frames should cost little CPU, based on its multiply count; measure it. Use it for laughter, screaming, applause and gunfire-type cues, and treat it as a signal to a ranking step rather than an answer. Fine-tune a small head later if game audio confuses it.
- **After stream:** PANNs or BEATs only if YAMNet's quality falls short. BEATs and PANNs are heavier and add licence checks for little proven gain here.
- Face detection only needs to run on candidate clips at 1 to 2 fps to locate the webcam for 9:16 layout. Let the user draw the webcam region once and save it per scene; this is more robust than detection and handles small faces.
- OCR for sensitive text (emails, DMs, keys): sample candidate clips at a low frame rate and match regexes. Treat it as a warning tool for the user, never as a guarantee.
- Use ONNX Runtime with CPU first and DirectML second. DirectML still reaches AMD, Intel and NVIDIA on Windows 10, whereas Windows ML appears to need a recent Windows 11. Keep the runtime layer swappable.
- **Music risk:** with an isolated music track, fingerprinting has a chance; on a mixed stream track, expect misses. A "no match" must never be shown as "safe": AcoustID coverage is MusicBrainz-linked recordings, not a rights database. Local alternative: fingerprint against a user's own known-tracks library, and read now-playing metadata where available.

### Gaps
- No measured CPU latency for YAMNet, PANNs or BEATs on desktop CPUs, and no comparison on gaming audio. The mAP figures are not like-for-like (YAMNet's is "balanced mAP").
- BEATs checkpoint terms were not read separately from the repo licence. Licence risk from AudioSet-derived training was not researched.
- Official MediaPipe licence page was not opened; the card I read was on a mirror.
- Windows.Media.Ocr: no speed, accuracy or Hindi data found. PaddleOCR and RapidOCR licence names and Devanagari quality were not confirmed. From memory PaddleOCR is Apache-2.0, unverified.
- Ultralytics YOLO: search did not cover it. From memory it is AGPL-3.0 with a paid enterprise option, so avoid until checked.
- No direct Chromaprint vs Panako vs Olaf test under speech over music. Panako and Olaf licences not checked (AGPL from memory, unverified, which would matter for a closed app).

## What local LLMs, if any, are practical for ranking moments, compared with an optional cloud API, and what are the costs?

### Takeaway
Do not run an LLM during a stream. Rank with cheap signals first, then send a short list to a model. A cloud model is so cheap for this job (under about 6 US cents per 4-hour stream in my estimate) that an opt-in cloud option plus a post-stream local 4B to 8B option is the sensible split.

### Cited Findings
- Qwen 3 8B Q4_K_M, llama.cpp, RTX 3060 12 GB: about 47 tok/s generation (Ryzen 5 5600X, Linux, CUDA 12.4) — [SpecPicks](https://specpicks.com/reviews/ollama-vs-llama-cpp-vs-vllm-rtx-3060-12gb-2026). Other SpecPicks pages give 35 to 45 tok/s and 18 to 22 tok/s for similar setups, which conflict — [SpecPicks](https://specpicks.com/reviews/llama-cpp-vs-vllm-single-user-12gb-gpu-2026); [SpecPicks](https://specpicks.com/reviews/llm-quantization-12gb-gpu-rtx-3060-2026)
- Estimator figures, not measured: Gemma 3 4B Q4_K_M about 6.9 GB memory and about 56 tok/s on a 3060 12 GB — [WillItRunAI](https://willitrunai.com/can-run/gemma-3-4b-on-rtx-3060-12gb); Llama 3.1 8B Q4_K_M 9.2 GB — [WillItRunAI](https://willitrunai.com/can-run/llama-3.1-8b-on-rtx-3060-12gb)
- llama.cpp ships CUDA and Vulkan backends — [SpecPicks](https://specpicks.com/reviews/ollama-vs-llama-cpp-vs-vllm-rtx-3060-12gb-2026)
- Gemini 3.1 Flash-Lite: $0.25 per 1M input (audio $0.50), $1.50 output. Gemini 3.6/3.8 Flash: $0.75 input, $3.75 output through 31 December 2026, then $1.50/$7.50. On the free tier Google may use content to improve its products; the paid tier does not — [Google pricing](https://aistudio.google.com/docs/pricing)
- Claude Haiku 5.5: $0.10 input, $0.50 output per 1M tokens for prompts up to 100K tokens, and $0.50/$2.50 beyond. Claude Sonnet 5.5: $2/$10. Batch processing runs at 50% cost. Source: the Anthropic `claude-api` skill bundled with Claude Code, table cached 2026-10-06, not checked against the live pricing page.

### Inferences
- **Token estimate (mine, not measured):** 4 hours of speech at 150 words a minute is about 36,000 words, or about 70,000 tokens. Hindi in Devanagari may use noticeably more tokens per word.

| Option | Cost per 4-hour stream, whole transcript in, about 2,000 tokens out (derived) |
|---|---|
| Claude Haiku 5.5 | about $0.008 |
| Gemini 3.1 Flash-Lite | about $0.02 |
| Gemini 3.6 Flash (until 31 Dec 2026) | about $0.06 |
| Gemini 3.6 Flash (from 1 Jan 2027) | about $0.12 |
| Local 8B | no API cost; takes GPU time and 6 to 9 GB VRAM after the stream |

- Sending only top candidate windows cuts this further and keeps Haiku under its 100K tier. Costs are low enough for a bundled allowance on a paid plan, or a user-supplied key.
- A local 4B to 8B model suits per-candidate scoring with structured JSON and short prompts. Whole-stream reasoning over 70,000 tokens is a poor fit on a 12 GB card, particularly next to loaded ASR weights. Unload one before loading the other.
- Ship local LLM as an optional download, not a default. The ranking pipeline should work with no LLM at all, using loudness, YAMNet events, chat rate and keywords.
- Privacy: send text only, never video, and require opt-in. This keeps the "local-first" claim honest.

### Gaps
- No measured llama-bench data from the llama.cpp project itself, no prompt-processing speed (which dominates ranking jobs), and no CPU-only or Vulkan number.
- No evidence on how well any small local LLM ranks Hinglish moments. Build a small labelled set from real streams and compare local vs cloud.
- Current best small open models and their licences as of November 2026 were not surveyed.

## FFmpeg for cuts, hardware encoding, 9:16 layouts and ASS captions: which FFmpeg builds and model licences allow selling a closed-source app?

### Takeaway
Ship an LGPL FFmpeg as separate shared DLLs or a separate process, with no libx264/libx265, and use NVENC, AMF or QSV for encoding. Stream copy is not frame accurate, so clips should be re-encoded (they need a re-encode anyway for 9:16 and captions). Most listed models are permissive, but the AcoustID service and any AGPL dependency need care.

### Cited Findings
- Most FFmpeg files are LGPL v2.1 or later. `--enable-gpl` is needed for x264, x265, xvid, avisynth, frei0r, libvidstab and others, and for some filters such as `vf_delogo` and `vf_eq`; enabling it turns FFmpeg into GPL v2+ — [FFmpeg LICENSE.md](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/LICENSE.md)
- `--enable-nonfree` (fdk-aac, OpenSSL) makes the binary "unredistributable" — [FFmpeg LICENSE.md](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/LICENSE.md)
- `--enable-version3` is needed for some Apache and LGPLv3 libraries — [FFmpeg LICENSE.md](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/LICENSE.md)
- BtbN offers `gpl`, `lgpl`, `gpl-shared`, `lgpl-shared` and nonfree variants. LGPL builds lack GPL-only libraries, "most prominently libx264 and libx265". Shared variants ship the libav* DLLs — [BtbN FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)
- BtbN build scripts include libass, ffnvcodec, AMF, oneVPL, OpenH264, fribidi — [scripts.d](https://github.com/BtbN/FFmpeg-Builds/tree/master/scripts.d). Whether each one is in the LGPL variant was not shown.
- Stream copy can only start on a keyframe, so a cut may land a second or two off; re-encoding creates a new keyframe at the start — [ahosting FAQ](https://www.ahosting.net/faq/ffmpeg-hosting/how-to-trim-cut-and-concatenate-video-with-ffmpeg.html) (secondary)
- "Smart cut" (re-encode only the first partial GOP, copy the rest) was still a proposal on ffmpeg-devel in 2024; I found no evidence that it landed — [ffmpeg-devel](https://ffmpeg.org/pipermail/ffmpeg-devel/2024-August/332030.html). The multi-call route (re-encode head, copy rest, concatenate) is the practical way — [VideoHelp](https://forum.videohelp.com/threads/414634-[FFMPEG]How-can-I-do-a-frame-accurate-cut-while-only-encoding-the-GOP)

**Licences collected**

| Component | Licence seen | Selling a closed app |
|---|---|---|
| FFmpeg LGPL build | LGPL 2.1+ | Yes, with LGPL duties |
| FFmpeg with x264/x265 | GPL | No, unless the app is GPL |
| faster-whisper, whisper.cpp | MIT | Yes, keep notice |
| Qwen3-ASR | Apache-2.0 | Yes |
| Trelis Hinglish preview, Oriserve | Apache-2.0 tag | Yes on the tag; preview weights may change |
| Parakeet, Canary-Qwen | CC-BY-4.0 (secondary) | Yes, attribution |
| YAMNet ONNX port | Apache-2.0 | Yes |
| PANNs | Code MIT, weights CC BY 4.0 (secondary) | Yes, attribution |
| BEATs | Repo MIT; checkpoints not read | Check |
| YuNet / BlazeFace | MIT (redistribution) / Apache 2.0 | Yes; confirm upstream |
| Chromaprint | LGPL 2.1 as a whole | Yes, dynamic link or separate exe |
| AcoustID service | Non-commercial free; paid otherwise | Paid plan required |

### Inferences
- **Export pipeline:** decode the source range, apply crop, scale, overlay and the ASS filter, and encode with `h264_nvenc`, `h264_amf` or `h264_qsv`. A probe at first run should choose the encoder by doing a 1-second test encode. Filters in the LICENSE list (for example `eq`, `delogo`) are unavailable in LGPL builds, so check each filter you need.
- Untested sketch for a 9:16 layout with webcam above gameplay and captions:
  `ffmpeg -ss START -to END -i in.mp4 -filter_complex "[0:v]crop=CAMW:CAMH:CAMX:CAMY,scale=1080:608[cam];[0:v]crop=ih*9/10:ih,scale=1080:1312[game];[cam][game]vstack,subtitles=clip.ass:fontsdir=fonts[v]" -map "[v]" -map 0:a:0 -c:v h264_nvenc -cq 21 -c:a aac out.mp4`
  Check against the FFmpeg filter docs; I could not reach ffmpeg.org's main pages.
- Use `-c copy` only for a quick "raw save" button, where a second or two of slack is fine. Add padding so nothing important is cut.
- Run FFmpeg as a separate process (`ffmpeg.exe`) with an LGPL build, include its licence and source offer, and let users replace the binary. This is the cleanest setup for a solo developer. Get legal advice before release.
- Bundle a Devanagari-capable font with a licence that allows redistribution, and pass `fontsdir`, so captions do not depend on system fonts.
- With x264 unavailable, machines with no hardware encoder need a fallback. OpenH264 is in the BtbN scripts, but quality is unknown.

### Gaps
- **ffmpeg.org/legal.html refused the connection on both tries**, so I could not read the official LGPL compliance checklist or the patent warnings. The patent position on H.264/HEVC/AAC in a paid app was not researched and needs legal review; relying on GPU encoders may help but I have no source for that.
- The `subtitles`/`ass` filter documentation and libass's licence were not read (ISC from memory). Confirm that the chosen LGPL build has libass with `ffmpeg -buildconf` and `ffmpeg -filters`.
- Confirm that NVENC, AMF and QSV are enabled in the chosen LGPL build with `ffmpeg -encoders`. Availability was shown only at script level.
- Whether smart cut has landed in FFmpeg since 2024 is unknown.
- Nothing measured on export speed for a 60-second 9:16 clip with captions.
- CUDA redistribution terms (NVIDIA EULA for cuBLAS and cuDNN DLLs) were not read. This is a real item to check before bundling or auto-downloading them.

## Which desktop framework fits (Python with pywebview and PyInstaller, Tauri, Electron), what are the package size trade-offs, and how can models download on first run?

### Takeaway
Stay on Python, pywebview, PyInstaller and Inno Setup. The shell is a small part of total size, since ML runtimes and models dominate, and the analysis code is Python anyway. Ship a small installer and download CUDA libraries and models on first run. Tauri's size advantage shrinks to almost nothing once a Python sidecar is attached.

### Cited Findings
- Tauri 2.x vs Electron 43: hello-world bundle 3.2 MB vs 85 MB, complex app 8.6 MB vs 244 MB, idle memory 42 MB vs 168 MB. The OS and hardware are not named — [Tech Insider](https://tech-insider.org/tauri-vs-electron-2026/) (draws on third-party benchmark suites)
- A screen recorder with FFmpeg on macOS: Tauri 57 MB, Electron 323 MB; idle memory Tauri 109 MB (including webview helpers), Electron 128 MB, so the memory gap is small when webview helpers are counted — [Better Stack, July 2026](https://betterstack.com/community/guides/scaling-nodejs/tauri-vs-electron-vs-deno-vs-electrobun/)
- Electron bundles Chromium, adding 80 to 120 MB before app code — [Tech Insider](https://tech-insider.org/tauri-vs-electron-2026/)
- PyTorch with CUDA is around 2.3 GB per maintainers, with a user measuring about 5.7 GB on disk for CUDA 12.6 — [PyTorch forum](https://discuss.pytorch.org/t/pytorch-install-is-that-large-5-gbs/213629). A PyInstaller folder build with torch reached about 4 GB, nearly all in `torch\lib` — [PyTorch forum](https://discuss.pytorch.org/t/how-to-reduce-the-size-of-the-pytorch-package-after-using-pyinstaller-with-d-option-resulting-in-a-3gb-size-for-the-torch-file/194822)
- faster-whisper uses CTranslate2 rather than PyTorch, and PyAV bundles FFmpeg libraries — [faster-whisper README](https://github.com/SYSTRAN/faster-whisper)
- Model disk sizes: whisper.cpp small 466 MiB, medium 1.5 GiB, large 2.9 GiB — [whisper.cpp README](https://github.com/ggml-org/whisper.cpp)

### Inferences
- **Avoid PyTorch at runtime.** CTranslate2 + ONNX Runtime + llama.cpp/whisper.cpp binaries can remove the 2 to 5 GB torch cost. This is the largest size decision in the project.
- **Layout (Python, matching the existing stack):**
  - Installer: UI, Python runtime, ONNX Runtime CPU, YAMNet, LGPL FFmpeg. Target a few hundred MB at most; measure it.
  - First-run packs chosen by a hardware probe: `asr-small` (CPU), `asr-turbo-int8`, `asr-hinglish`, `cuda-runtime` (NVIDIA only), `llm-local` (optional).
  - Packs live in `%LOCALAPPDATA%`, outside the install folder, so app updates do not touch them and need no admin rights.
- **Downloader needs:** resumable HTTP range requests, SHA-256 checks against a signed manifest, a pause during live mode, mirror URLs, offline import of a pack file, and a licence notices screen. Host files on your own storage or pin a Hugging Face revision so upstream changes cannot break users. Preview-stage weights make pinning important.
- Keep the worker as a **separate process** from the UI. Native CUDA or ONNX crashes then do not kill the UI, priority is easy to set, and models can be fully unloaded by exiting the process. This also frees VRAM before a stream.
- PyWebView uses the system WebView2 on Windows like Tauri does, so the UI approach carries over; check the WebView2 runtime is present on Windows 10 (unsourced; confirm in the pywebview docs).
- Move to Tauri later only if a Rust shell has a clear gain. Electron only makes sense if the UI needs a fixed Chromium for preview playback or `getDisplayMedia`-type features, and its cost is about 100 to 250 MB, which is small next to models.
- A video preview in a WebView needs a local file or local server path; test Hybrid MP4 and HEVC/AV1 playback in WebView2, because codec support may vary.

### Gaps
- No measured installer sizes for a pywebview + PyInstaller + CTranslate2 + ONNX Runtime app. The size target above is a design goal, not a measurement.
- Size of cuBLAS and cuDNN Windows DLLs was not found, nor the size of Purfview's archive. Measure them, since these will likely be the largest pack.
- A search snippet reported a Windows 11 benchmark from October 2026 (Tauri installer 1.05 MB, Electron 106.1 MB, private memory 142 vs 149 MB), but I could not pin it to a page, so treat it as unverified. It would support the "memory gap is small" point.
- Not researched: PyInstaller false positives with Windows Defender, code signing cost, Inno Setup size handling with large payloads, Windows 10 support status in late 2026. The user's other apps may already answer the signing and installer questions.
- No published comparison of Python vs Rust orchestration overhead was found; since the heavy work is in native libraries, I expect it to be negligible, but that is unmeasured.
