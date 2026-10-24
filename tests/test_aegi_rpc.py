import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aegi_rpc
from common import DEFAULTS, read_config, validate_config, write_config

ASS = """\ufeff[Script Info]
Title: Episode 1 (TV)

[Aegisub Project Garbage]
Video File: C:\\videos\\[Group] Show - 01.mkv

[Events]
Title: not this one
"""


def make_fd(name="a.ass", title="", video="", is_srt=False):
    return {"file_name": name, "title": title, "video_file": video, "is_srt": is_srt, "path": name}


class ParseAssTest(unittest.TestCase):
    def test_title_and_video(self):
        with tempfile.NamedTemporaryFile("w", suffix=".ass", delete=False, encoding="utf-8") as f:
            f.write(ASS)
        try:
            video, title = aegi_rpc.parse_ass_file(f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual(title, "Episode 1 (TV)")
        self.assertEqual(video, "C:\\videos\\[Group] Show - 01.mkv")


class PresenceTest(unittest.TestCase):
    def setUp(self):
        self.config = DEFAULTS.copy()

    def test_single_file_uses_filename(self):
        p = aegi_rpc.build_presence(self.config, [make_fd("ep1.ass")], 123)
        self.assertEqual(p["details"], "Project: ep1.ass")
        self.assertEqual(p["start"], 123)

    def test_title_source_falls_back_to_default_details(self):
        self.config["project_name_source"] = "ass_title"
        p = aegi_rpc.build_presence(self.config, [make_fd("ep1.ass")], 1)
        self.assertEqual(p["details"], self.config["default_details"])

    def test_srt_ignores_title_source(self):
        self.config["project_name_source"] = "ass_title"
        p = aegi_rpc.build_presence(self.config, [make_fd("ep1.srt", is_srt=True)], 1)
        self.assertEqual(p["details"], "Project: ep1.srt")

    def test_windows_video_path_on_any_os(self):
        p = aegi_rpc.build_presence(self.config, [make_fd(video="C:\\v\\ep1.mkv")], 1)
        self.assertEqual(p["state"], "Video: ep1.mkv")

    def test_multi(self):
        files = [make_fd("a.ass"), make_fd("b.ass"), make_fd("c.ass")]
        self.assertEqual(aegi_rpc.build_presence(self.config, files[:2], 1)["details"], "Editing a.ass and b.ass")
        self.assertEqual(aegi_rpc.build_presence(self.config, files, 1)["details"], "Editing a.ass and 2 others")

    def test_button_and_tooltip(self):
        self.config["tooltip_enabled"] = True
        p = aegi_rpc.build_presence(self.config, [make_fd()], 1)
        self.assertIn("large_text", p)
        self.assertEqual(p["buttons"][0]["url"], self.config["button_url"])

        self.config["button_enabled"] = False
        self.assertNotIn("buttons", aegi_rpc.build_presence(self.config, [make_fd()], 1))

    def test_hide_file_names(self):
        self.config["hide_file_names"] = True
        files = [make_fd("secret_ep1.ass", video="C:\\v\\secret.mkv", title="Secret"), make_fd("b.ass")]
        for selection in (files[:1], files):
            p = aegi_rpc.build_presence(self.config, selection, 1)
            self.assertEqual(p["details"], self.config["default_details"])
            self.assertEqual(p["state"], self.config["default_state"])
            self.assertNotIn("secret", str(p).lower())

    def test_file_names_shown_by_default(self):
        self.assertFalse(DEFAULTS["hide_file_names"])

    def test_long_text_is_truncated(self):
        p = aegi_rpc.build_presence(self.config, [make_fd("x" * 500)], 1)
        self.assertLessEqual(len(p["details"]), 128)


class ConfigTest(unittest.TestCase):
    def test_roundtrip(self):
        config = DEFAULTS.copy()
        config.update(button_label="Café & <site>", tooltip_enabled=True, hide_console=False)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.xml")
            write_config(path, config)
            self.assertEqual(read_config(path), config)

    def test_missing_keys_use_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.xml")
            with open(path, "w") as f:
                f.write("<config><client_id>42</client_id></config>")
            config = read_config(path)
        self.assertEqual(config["client_id"], "42")
        self.assertEqual(config["button_label"], DEFAULTS["button_label"])

    def test_validation(self):
        self.assertEqual(validate_config(DEFAULTS.copy()), [])
        self.assertTrue(validate_config({**DEFAULTS, "client_id": "abc"}))
        self.assertTrue(validate_config({**DEFAULTS, "button_label": "x" * 33}))
        self.assertTrue(validate_config({**DEFAULTS, "button_url": "ftp://example.com"}))
        self.assertEqual(validate_config({**DEFAULTS, "button_enabled": False, "button_url": "nope"}), [])


if __name__ == "__main__":
    unittest.main()
