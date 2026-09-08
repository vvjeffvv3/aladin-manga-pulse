from django.test import SimpleTestCase

from dashboard.service.formatting import format_release_date


class FormattingTests(SimpleTestCase):
    def test_formats_month_only_release_date(self):
        """연·월 발매일을 화면 형식으로 변환"""
        self.assertEqual(format_release_date("2026-08"), "2026.08")

    def test_formats_full_release_date_as_month_only(self):
        """일자가 포함된 발매일도 월까지만 표시"""
        self.assertEqual(format_release_date("2026-08-12"), "2026.08")

    def test_formats_empty_release_date_as_dash(self):
        """빈 발매일을 하이픈으로 표시"""
        self.assertEqual(format_release_date(None), "-")
        self.assertEqual(format_release_date(""), "-")

    def test_keeps_unrecognized_release_date(self):
        """형식이 다른 발매일은 원문 유지"""
        self.assertEqual(format_release_date("미정"), "미정")
        self.assertEqual(format_release_date("2026-13"), "2026-13")


if __name__ == "__main__":
    import unittest

    unittest.main()
