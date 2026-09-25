import unittest
from datetime import datetime, timezone
from parse_cme import parse_view, validate_snapshot

TEXT = '''PROBABILITIES
EASE\tNO CHANGE\tHIKE
0.0 %\t31.4 %\t68.6 %
Target Rate Probabilities for 28 Oct 2026 Fed Meeting
Current target rate is 375-400
TARGET RATE (BPS)\tPROBABILITY(%)
NOW *\t1 DAY
350-375\t0.0%\t0.0%
375-400 (Current)\t31.4%\t29.1%
400-425\t68.6%\t70.9%
* Data as of 24 Sep 2026 10:43:49 CT
'''

class ParserTests(unittest.TestCase):
    def test_observed_values_and_chicago_timezone(self):
        data = parse_view(TEXT, '28 Oct26')
        self.assertEqual(data['hold'], 31.4)
        self.assertEqual(data['sourceAsOf'], '2026-09-24T15:43:49+00:00')
        self.assertEqual(data['date'], '2026-10-28')

    def test_reject_wrong_meeting(self):
        with self.assertRaises(ValueError): parse_view(TEXT, '9 Dec26')

    def test_reject_missing_now_not_zero(self):
        with self.assertRaises(ValueError): parse_view(TEXT.replace('31.4%\t29.1%', '\t29.1%'), '28 Oct26')

    def test_reject_bad_sum(self):
        with self.assertRaises(ValueError): parse_view(TEXT.replace('68.6%\t70.9%', '6.6%\t70.9%'), '28 Oct26')

    def test_reject_missing_timestamp(self):
        with self.assertRaises(ValueError): parse_view(TEXT.split('* Data as of')[0], '28 Oct26')

    def test_reject_duplicate_meetings(self):
        view = {'text': TEXT, 'tabLabel': '28 Oct26'}
        with self.assertRaises(ValueError): validate_snapshot([view, view], datetime(2026, 9, 25, tzinfo=timezone.utc))

    def test_reject_future_timestamp(self):
        with self.assertRaises(ValueError): validate_snapshot([{'text': TEXT, 'tabLabel': '28 Oct26'}], datetime(2026, 9, 1, tzinfo=timezone.utc))

    def test_old_source_time_is_preserved_not_relabelled(self):
        snapshot = validate_snapshot([{'text': TEXT, 'tabLabel': '28 Oct26'}], datetime(2026, 9, 25, tzinfo=timezone.utc))
        self.assertNotEqual(snapshot['collectedAt'], snapshot['meetings'][0]['sourceAsOf'])

if __name__ == '__main__': unittest.main()
