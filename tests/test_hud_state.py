"""Pure state checks for the HUD's cross-chat result guard.

These do not create an AppKit window or call a model/API.  They exercise the small
Python helpers directly with a fake controller, which is enough to catch a stale
main-thread callback being accepted after a session changes.
"""

import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hud import HudController


class FakeController:
    _session_current = HudController._session_current
    _push_session = HudController._push_session
    _apply_session_payload = HudController._apply_session_payload
    _stream_hook = HudController._stream_hook
    _context_key = HudController._context_key
    _advance_session = HudController._advance_session
    _work_inner = HudController._work_inner

    def __init__(self):
        self._paused = False
        self._session_epoch = 4
        self._gen_epoch = 8
        self._stream_rows = {0: 1}
        self._prejudge_req = (4, "old", None, None, "")
        self._prejudge_result = (4, "old", {}, None, "")
        self._pregen_req = (4, "old", None, ())
        self._pregen_result = (4, "old", (), {})
        self.last_seen = "old"
        self.analyzed_text = "old"
        self._last_intent = "闲聊"
        self._last_risk = 3
        self._last_skip_reason = "old"
        self.pushed = []
        self.drawn = []
        self._asked_permission = True
        self._context_id = (10, "聊天", ())
        self._latest_turn = (self._context_id, "me", "已回复", 0.1)
        self._last_full = None
        self._fingerprint = b"old"
        self._win_wid = 10
        self.wechat_win = None
        self._read_region = None
        self._stable_n = 0
        self._burst_left = 3
        self._next_read_ts = 0.0
        self._show_boxes = False
        self.last_change_ts = 0.0
        self._read_once = True
        self.last_analyze_ts = 0.0
        self._analyzing = False
        self._analyzing_epoch = None
        self._prejudging = False
        self._prejudge_event = type("Event", (), {"set": lambda _self: None})()
        self._pregen_event = type("Event", (), {"set": lambda _self: None})()

    def _push(self, selector, payload=None):
        self.pushed.append((selector, payload))

    def applyError_(self, value):
        self.drawn.append(value)

    def _context_text(self, *_args, **_kwargs):
        return None


class HudSessionGuardTests(unittest.TestCase):
    def test_new_session_retires_async_slots_and_queues_reset(self):
        fake = FakeController()
        epoch = HudController._advance_session(fake, clear_panel=True, title="新聊天")

        self.assertEqual(epoch, 5)
        self.assertEqual(fake._gen_epoch, 9)
        self.assertIsNone(fake._prejudge_req)
        self.assertIsNone(fake._prejudge_result)
        self.assertIsNone(fake._pregen_req)
        self.assertIsNone(fake._pregen_result)
        self.assertIsNone(fake.last_seen)
        self.assertEqual(fake.pushed[-1], ("applySession:", (5, "applyReset:", "新聊天")))

    def test_old_main_thread_callback_is_dropped(self):
        fake = FakeController()
        fake._apply_session_payload((3, "applyError:", "旧聊天错误"))
        self.assertEqual(fake.drawn, [])

        fake._apply_session_payload((4, "applyError:", "当前聊天错误"))
        self.assertEqual(fake.drawn, ["当前聊天错误"])

    def test_context_key_accepts_bytes_context_id(self):
        fake = FakeController()
        context = b"window-10|chat-a|region-1"
        self.assertEqual(HudController._context_key(fake, {"context_id": context}), context)

    def test_stale_stream_hook_cannot_replace_current_stream_epoch(self):
        fake = FakeController()
        callback = fake._stream_hook(0.0, session=3)
        callback(0, "高情商话术", "迟到的候选")
        self.assertEqual(fake._gen_epoch, 8)
        self.assertEqual(fake.pushed, [])

    def test_unchanged_fast_path_reuses_cached_title_before_validation(self):
        fake = FakeController()
        cached = {
            "ok": True, "unchanged": False, "chat_title": "聊天",
            "window": {"wid": 10, "x": 0, "y": 0, "w": 800, "h": 600},
            "region": {}, "context_id": fake._context_id,
            "messages": [type("Message", (), {"side": "me", "sender": None, "text": "已回复", "y": .1})()],
            "fingerprint": b"old", "timing_ms": {},
        }
        fake._last_full = cached
        fast = {"ok": True, "unchanged": True, "chat_title": "",
                "window": {"wid": 10, "x": 20, "y": 30, "w": 800, "h": 600},
                "fingerprint": b"old", "messages": []}
        with patch("hud.screen_capture_ok", return_value=True), \
             patch("hud.read_conversation", return_value=fast):
            fake._work_inner()
        self.assertEqual(fake.wechat_win["x"], 20)
        self.assertFalse(any("聊天标题没读到" in str(p) for _s, p in fake.pushed))

    def test_error_with_window_keeps_picker_target_visible(self):
        fake = FakeController()
        failed = {"ok": False, "error": "请先框选聊天区域",
                  "window": {"wid": 11, "x": 7, "y": 8, "w": 900, "h": 700}}
        with patch("hud.screen_capture_ok", return_value=True), \
             patch("hud.read_conversation", return_value=failed):
            fake._work_inner()
        self.assertEqual(fake.wechat_win["wid"], 11)
        selectors = [selector for selector, _payload in fake.pushed]
        self.assertIn("applyPosition:", selectors)
        self.assertIn("applyError:", selectors)


if __name__ == "__main__":
    unittest.main()
