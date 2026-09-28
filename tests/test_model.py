import unittest

import _support  # noqa: F401  (path bootstrap)
from oflit_activity import model


def v(payload, chars=200):
    return model.validate_event(payload, max_content_chars=chars, schema_version=1)


class TestValidation(unittest.TestCase):
    def test_submitted_search_accepted(self):
        e = v({"event_type": "submitted_search", "source": "browser_extension",
               "site": "www.google.com", "content": "pecahan campuran",
               "submitted": True})
        self.assertEqual(e.event_type, "submitted_search")
        self.assertEqual(e.site, "google.com")
        self.assertEqual(e.evidence, model.EVIDENCE_DIRECT_USER_ACTION)
        self.assertEqual(e.content, "pecahan campuran")

    def test_submitted_prompt_accepted(self):
        e = v({"event_type": "submitted_prompt", "source": "browser_extension",
               "site": "chatgpt.com", "content": "Apa itu pecahan?", "submitted": True})
        self.assertEqual(e.evidence, model.EVIDENCE_DIRECT_USER_ACTION)

    def test_chat_openai_alias_normalizes(self):
        e = v({"event_type": "submitted_prompt", "source": "browser_extension",
               "site": "chat.openai.com", "content": "x", "submitted": True})
        self.assertEqual(e.site, "chatgpt.com")

    def test_unknown_event_type_rejected(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "keystroke", "source": "browser_extension",
               "site": "google.com", "content": "a"})

    def test_unknown_source_rejected(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_search", "source": "mystery",
               "site": "google.com", "content": "a", "submitted": True})

    def test_unsupported_site_rejected(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_search", "source": "browser_extension",
               "site": "evil.example", "content": "a", "submitted": True})

    def test_disallowed_pair_rejected(self):
        # prompt event on google is not an allowed pair
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_prompt", "source": "browser_extension",
               "site": "google.com", "content": "a", "submitted": True})

    def test_empty_submitted_content_rejected(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_search", "source": "browser_extension",
               "site": "google.com", "content": "   ", "submitted": True})


class TestSensitiveRejection(unittest.TestCase):
    def test_password_input_type(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_search", "source": "browser_extension",
               "site": "google.com", "content": "hunter2", "input_type": "password"})

    def test_explicit_sensitive_flag(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_prompt", "source": "browser_extension",
               "site": "chatgpt.com", "content": "x", "sensitive": True})

    def test_draft_not_submitted(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_prompt", "source": "browser_extension",
               "site": "chatgpt.com", "content": "bagaimana car", "submitted": False})

    def test_jwt_like_rejected(self):
        tok = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "a" * 40 + "." + "b" * 20
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_prompt", "source": "browser_extension",
               "site": "chatgpt.com", "content": tok, "submitted": True})

    def test_credit_card_like_rejected(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_search", "source": "browser_extension",
               "site": "google.com", "content": "4111111111111111", "submitted": True})

    def test_api_token_prefix_rejected(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_prompt", "source": "browser_extension",
               "site": "chatgpt.com", "content": "sk-abcdefghijklmnopqrstuvwx",
               "submitted": True})

    def test_sensitive_field_name(self):
        with self.assertRaises(model.RejectedEvent):
            v({"event_type": "submitted_search", "source": "browser_extension",
               "site": "google.com", "content": "x", "field_name": "user_password",
               "submitted": True})


class TestEvidenceAndTruncation(unittest.TestCase):
    def test_navigation_cannot_be_promoted(self):
        e = v({"event_type": "navigation", "source": "browser_extension",
               "site": "google.com", "url": "https://google.com/search",
               "evidence": "direct_user_action"})
        self.assertEqual(e.evidence, model.EVIDENCE_VISITED_RESOURCE)

    def test_truncation_marked(self):
        long = "a" * 500
        e = v({"event_type": "submitted_search", "source": "browser_extension",
               "site": "google.com", "content": long, "submitted": True}, chars=100)
        self.assertTrue(e.content_truncated)
        self.assertLessEqual(len(e.content), 100)

    def test_control_chars_stripped(self):
        e = v({"event_type": "submitted_search", "source": "browser_extension",
               "site": "google.com", "content": "a\x00b\tc", "submitted": True})
        self.assertNotIn("\x00", e.content)


if __name__ == "__main__":
    unittest.main()
