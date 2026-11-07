"""The free plan's caps, Premium, and the rule that nothing is limited before billing is live."""
import time

import pytest

from clipstudio.account import Account
from clipstudio.plans import Gate
from clipstudio.settings import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(str(tmp_path / "s.json"))


def signed(settings, plan="free", billing=True, until=None, checked=None):
    settings.set("account_token", "t" * 64)
    settings.set("account_cache", {"plan": plan, "until": until or time.time() + 86400, "billing": billing,
                                   "checked": checked or time.time()})
    return Gate(settings)


def clip(cid=1, preset="classic", words=True, **style):
    return {"id": cid, "words": [{"w": "hi", "s": 0, "e": 1}] if words else [],
            "edit": {"caption_style": {"preset": preset, **style}}}


def test_nothing_is_limited_before_billing_is_live(settings):
    gate = Gate(settings)
    assert not gate.enforced()
    for _ in range(20):
        assert gate.allowed("exports") and gate.allowed("upscale")
        gate.use("exports")
    assert gate.stream_check(11 * 3600, 1) is None
    assert gate.export_options("1440", 60, "ai") == ("1440", 60, "ai")


def test_free_plan_counts_exports_per_day(settings):
    gate = signed(settings)
    t = 1_000_000.0
    for i in range(10):
        assert gate.allowed("exports", now=t)
        gate.use("exports", now=t + i)
    assert not gate.allowed("exports", now=t + 20)
    assert gate.allowed("exports", now=t + 86400 + 20)        # a new day


def test_the_same_stream_or_clip_is_counted_once(settings):
    gate = signed(settings)
    for sid in (1, 2, 3):
        gate.record_stream(3600, sid)
    assert gate.stream_check(3600, 4) == "streams"
    assert gate.stream_check(3600, 2) is None                 # analysing stream 2 again is free


def test_stream_length_rules(settings):
    gate = signed(settings)
    assert gate.stream_check(2 * 3600, 1) is None
    assert gate.stream_check(3.5 * 3600, 1) is None           # one longer stream a week
    gate.record_stream(3.5 * 3600, 1)
    assert gate.stream_check(3.5 * 3600, 2) == "long_stream"
    assert gate.stream_check(5 * 3600, 3) == "long_premium"
    assert gate.stream_check(13 * 3600, 3) == "too_long"
    premium = signed(settings, "premium")
    assert premium.stream_check(11 * 3600, 9) is None


def test_export_uses_the_right_caps(settings):
    gate = signed(settings)
    assert gate.export_features(clip(), "off") == ["exports"]
    assert gate.export_features(clip(preset="pop"), "auto") == ["exports", "styles", "sharpen"]
    assert gate.export_features(clip(preset="neon"), "off") == ["exports", "extra_styles"]
    assert "caption_advanced" in gate.export_features(clip(font="Impact"), "off")
    assert gate.export_features(clip(preset="neon", words=False), "off") == ["exports"]   # no captions, no style used
    for i in range(3):
        gate.record_export(clip(cid=i, preset="fire"), "off")
    assert gate.export_check(clip(cid=9, preset="neon"), "off") == "extra_styles"
    assert gate.export_check(clip(cid=0, preset="fire"), "off") is None       # re-exporting a clip already counted


def test_premium_only_features_and_export_clamp(settings):
    gate = signed(settings)
    assert not gate.allowed("upscale") and "Premium" in gate.why_not("upscale")
    assert gate.export_options("1440", 60, "ai") == ("1080", 30, "auto")
    premium = signed(settings, "premium")
    assert premium.allowed("upscale") and premium.export_options("1440", 60, "ai") == ("1440", 60, "ai")


def test_premium_lapses_offline_after_a_week_and_at_its_end(settings):
    week_ago = time.time() - 8 * 86400
    assert Account(signed(settings, "premium", checked=week_ago).settings).plan() == "free"
    assert Account(signed(settings, "premium", until=time.time() - 5).settings).plan() == "free"
    assert Account(signed(settings, "premium").settings).plan() == "premium"


def test_sign_in_comes_back_through_a_local_port(settings, monkeypatch):
    import threading
    import urllib.parse
    import urllib.request
    account = Account(settings)
    monkeypatch.setattr(account, "refresh", lambda: {"email": "drxshi@example.com", "plan": "free"})

    def browser(url):           # stands in for Google and the server redirecting back to the app
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        back = "http://127.0.0.1:%s/done?state=%s&token=%s" % (q["port"][0], q["state"][0], "a" * 64)
        threading.Thread(target=lambda: urllib.request.urlopen(back, timeout=5).read(), daemon=True).start()

    assert account.sign_in(open_url=browser, wait=10)["email"] == "drxshi@example.com"
    assert settings.get("account_token") == "a" * 64
