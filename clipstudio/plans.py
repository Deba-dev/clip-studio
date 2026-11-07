"""What Free and Premium include, as decided on the freemium review page, and the weekly caps on the free plan.

Nothing is limited while billing is not live (see Account.billing_live): people are never locked out of a feature
they have no way to pay for. Usage is counted on this PC only.
"""
import time

from .account import Account
from .captions import PREMIUM_PRESETS, PRESETS, style_of

DAY = 86400
WEEK = 7 * DAY
# feature: (uses allowed, period, what it is called in messages)
CAPS = {
    "streams": (3, WEEK, "3 streams a week"),
    "long_stream": (1, WEEK, "1 stream a week longer than 2.5 hours"),
    "exports": (10, DAY, "10 exports a day"),
    "styles": (10, WEEK, "10 exports a week with the Pop, Box, Karaoke, One word, Comic and Minimal styles"),
    "extra_styles": (3, WEEK, "3 exports a week with the Neon, Fire and Marker styles"),
    "caption_advanced": (3, WEEK, "3 exports a week with caption fonts, animations and effects"),
    "style_all": (1, WEEK, "using one caption style on all clips for 1 stream a week"),
    "sharpen": (5, WEEK, "5 clips a week with clean-up and sharpening"),
    "weights": (1, WEEK, "changing what to look for once a week"),
}
PREMIUM_ONLY = {
    "english": "English translation captions",
    "1440": "1440p export",
    "60fps": "60 fps export",
    "upscale": "AI upscaling",
    "batch": "exporting all kept clips at once",
    "virality": "virality scores",
    "titles": "title and hashtag suggestions",
    "compilation": "compilations",
}
FREE_HOURS = 2.5
LIMIT_HOURS = 4
PREMIUM_HOURS = 12
ADVANCED = ("font", "animation", "highlight_mode", "tilt", "spacing", "outline_width", "shadow", "outline",
            "shadow_color", "box", "box_color", "box_opacity", "italic")


class Gate:
    def __init__(self, settings, account=None):
        self.settings = settings
        self.account = account or Account(settings)

    def enforced(self):
        return self.account.billing_live()

    def premium(self):
        return self.account.plan() == "premium"

    def free_limits(self):
        return self.enforced() and not self.premium()

    # ---- counting
    def _usage(self, now):
        usage = dict(self.settings.get("usage") or {})
        return {k: [e for e in v if now - e[0] < WEEK + DAY] for k, v in usage.items()}

    def used(self, feature, now=None):
        now = now or time.time()
        limit, period, _ = CAPS[feature]
        return len([e for e in self._usage(now).get(feature, []) if now - e[0] < period])

    def left(self, feature, now=None):
        return max(CAPS[feature][0] - self.used(feature, now), 0)

    def allowed(self, feature, key=None, now=None):
        if not self.free_limits():
            return True
        if feature in PREMIUM_ONLY:
            return False
        now = now or time.time()
        if key is not None and any(e[1] == key for e in self._usage(now).get(feature, []) if now - e[0] < CAPS[feature][1]):
            return True             # the same stream or clip again is not a new use
        return self.left(feature, now) > 0

    def use(self, feature, key=None, now=None):
        """Records one use. A key (a stream or clip id) is counted once per period."""
        if not self.free_limits() or feature not in CAPS:
            return
        now = now or time.time()
        usage = self._usage(now)
        entries = usage.setdefault(feature, [])
        if key is not None and any(e[1] == key and now - e[0] < CAPS[feature][1] for e in entries):
            return
        entries.append([now, key])
        self.settings.set("usage", usage)

    def renews(self, feature, now=None):
        """When the next use frees up, as seconds from now."""
        now = now or time.time()
        limit, period, _ = CAPS[feature]
        times = sorted(e[0] for e in self._usage(now).get(feature, []) if now - e[0] < period)
        return max(times[0] + period - now, 0) if len(times) >= limit else 0

    def why_not(self, feature):
        if feature in PREMIUM_ONLY:
            return PREMIUM_ONLY[feature].capitalize() + " is part of Premium."
        return "The free plan includes %s, and that is used up for now." % CAPS[feature][2]

    # ---- whole decisions
    def stream_check(self, duration, sid):
        """None if this stream may be analysed, else the feature that blocks it."""
        hours = duration / 3600
        if hours > PREMIUM_HOURS:
            return "too_long"
        if not self.free_limits():
            return None
        if hours > LIMIT_HOURS:
            return "long_premium"
        if not self.allowed("streams", sid):
            return "streams"
        if hours > FREE_HOURS and not self.allowed("long_stream", sid):
            return "long_stream"
        return None

    def stream_message(self, reason, duration):
        hours = duration / 3600
        if reason == "too_long":
            return "This stream is %.1f hours long. Clip Studio analyses streams up to %d hours." % (hours, PREMIUM_HOURS)
        if reason == "long_premium":
            return ("This stream is %.1f hours long. The free plan analyses streams up to %d hours; Premium goes up to %d."
                    % (hours, LIMIT_HOURS, PREMIUM_HOURS))
        return self.why_not(reason)

    def record_stream(self, duration, sid):
        self.use("streams", sid)
        if duration / 3600 > FREE_HOURS:
            self.use("long_stream", sid)

    def export_features(self, clip, enhance, default_style=None):
        """The capped features one export would use."""
        style = style_of(clip.get("edit"), default_style)
        base = style_of({"caption_style": {"preset": style["preset"]}})
        used = ["exports"]
        if clip.get("words"):
            if style["preset"] in PREMIUM_PRESETS:
                used.append("extra_styles")
            elif style["preset"] != "classic" and style["preset"] in PRESETS:
                used.append("styles")
            if any(style[k] != base[k] for k in ADVANCED):
                used.append("caption_advanced")
        if enhance == "auto":
            used.append("sharpen")
        return used

    def export_check(self, clip, enhance, default_style=None):
        """The first capped feature this export cannot use, or None."""
        for feature in self.export_features(clip, enhance, default_style):
            if not self.allowed(feature, clip.get("id")):
                return feature
        return None

    def record_export(self, clip, enhance, default_style=None):
        for feature in self.export_features(clip, enhance, default_style):
            self.use(feature, clip.get("id") if feature != "exports" else None)

    def export_options(self, size, fps, enhance):
        """What a free plan exports when Premium-only settings are still chosen: 1080p, up to 30 fps, no AI."""
        if not self.free_limits():
            return size, fps, enhance
        return (min(size, "1080", key=int) if size else "1080", min(fps, 30),
                "auto" if enhance == "ai" else enhance)
