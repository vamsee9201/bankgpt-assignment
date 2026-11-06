"""Synthetic regression tests: no supplied website data or memorized answers."""
import unittest
from dataclasses import asdict
from knowledge.io import Page, Snapshot
from solution import build


BASE = 'https://credit-union.test'


def page(path, text, title='Rates'):
    return Page(BASE + path, title, text, '2026-01-01')


def snap(day, *pages):
    return Snapshot('snapshot-' + day, day, list(pages))


def cert(standard='2.75', jumbo='3.25'):
    return f'''# Certificates
| Certificate | Dividend Rate | APY | Min. to Earn |
| --- | --- | --- | --- |
| 10 Month Fixed Certificate Special | 2.72% | {standard}% | $1,000 |
| 10 Month Fixed Jumbo Certificate Special | 3.20% | {jumbo}% | $100,000 |
'''


def savings():
    return '''# Savings
| Account Type | Balance Tier | Dividend Rate | APY | Min. to Open | Min. to Earn |
| --- | --- | --- | --- | --- | --- |
| Share Savings | $0 - $999.99 | 0.04% | 0.05% | $5 | $0 |
| Share Savings | $1,000+ | 0.14% | 0.15% | $5 | $1,000 |
| Bright Savings | $0.01+ | 2.10% | 2.12% | $0 | $0.01 |
'''


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.ks = build()
        self.ks.ingest(snap('2026-01-10', page('/personal/savings-account', cert())))
        self.ks.ingest(snap('2026-03-10', page('/personal/savings-account', cert('4.75', '5.25'))))

    def test_current_and_historical_do_not_mix(self):
        old = self.ks.answer('10-month jumbo certificate APY', '2026-02-01')
        new = self.ks.answer('10-month jumbo certificate APY')
        self.assertIn('3.25%', old.text)
        self.assertNotIn('5.25%', old.text)
        self.assertIn('5.25%', new.text)
        self.assertEqual(old.sources[0].snapshot_id, 'snapshot-2026-01-10')

    def test_date_in_question(self):
        self.assertIn('3.25%', self.ks.answer('10-month jumbo certificate APY as of January 2026').text)

    def test_pre_history_abstains(self):
        self.assertFalse(self.ks.answer('certificate APY', '2025-12-01').confident)

    def test_invalid_date_abstains(self):
        self.assertFalse(self.ks.answer('certificate APY', '2026-99-99').confident)

    def test_removed_page_does_not_resurrect(self):
        self.ks.ingest(snap('2026-04-01', page('/contact', 'Call our team for assistance.')))
        self.assertFalse(self.ks.answer('10-month certificate APY').confident)
        self.assertIn('5.25%', self.ks.answer('10-month jumbo certificate APY', '2026-03-31').text)

    def test_out_of_order_ingestion(self):
        self.ks.ingest(snap('2026-02-01', page('/personal/savings-account', cert('3.75', '4.25'))))
        self.assertIn('5.25%', self.ks.answer('10-month jumbo certificate APY').text)

    def test_same_date_reingestion_replaces(self):
        self.ks.ingest(snap('2026-03-10', page('/personal/savings-account', cert('6.75', '7.25'))))
        self.assertIn('7.25%', self.ks.answer('10-month jumbo certificate APY').text)

    def test_no_conflict_between_rate_and_apy_or_jumbo_and_standard(self):
        ks = build()
        ks.ingest(snap('2026-01-01', page('/personal/savings-account', cert())))
        self.assertEqual(ks.conflicts(), [])

    def test_history_conflicts_cite_both_versions(self):
        report = self.ks.conflicts()
        found = [c for c in report if c.resolution == '5.25%']
        self.assertEqual(len(found), 1)
        self.assertEqual(set(found[0].values), {'3.25%', '5.25%'})
        self.assertEqual(len({s.snapshot_id for s in found[0].sources}), 2)

    def test_non_jumbo_is_not_jumbo(self):
        a = self.ks.answer('10-month non-jumbo certificate APY')
        self.assertIn('4.75%', a.text)
        self.assertNotIn('5.25%', a.text)

    def test_unknown_term_abstains(self):
        self.assertFalse(self.ks.answer('72-month jumbo certificate APY').confident)

    def test_metric_selection(self):
        a = self.ks.answer('10-month standard certificate dividend rate')
        self.assertIn('2.72%', a.text)
        self.assertNotIn('4.75%', a.text)

    def test_spellings_and_paraphrases(self):
        a = self.ks.answer('Current APY on a ten month jumbo CD')
        b = self.ks.answer('10-month jumbo certificate APY')
        self.assertEqual(a.text, b.text)

    def test_source_quote_is_grounded(self):
        for s in self.ks.answer('10-month certificate APY').sources:
            self.assertIn(s.quote, cert('4.75', '5.25'))

    def test_unknown_arm_and_construction_do_not_borrow_fixed_rate(self):
        for q in ['7/1 ARM rate', 'construction loan interest rate']:
            self.assertFalse(self.ks.answer(q).confident)

    def test_repeats_are_identical(self):
        a = asdict(self.ks.answer('10-month jumbo certificate APY'))
        self.assertEqual(a, asdict(self.ks.answer('10-month jumbo certificate APY')))

    def test_expired_offer_is_not_current(self):
        ks = build()
        ks.ingest(snap('2026-03-01', page('/promo', '6-month certificate APY 8.75% (offer ended 2025-09-30)')))
        self.assertFalse(ks.answer('6-month certificate APY').confident)

    def test_narrative_certificate_order_and_expired_secondary_source(self):
        ks = build()
        ks.ingest(snap('2026-03-01',
            page('/rates/certificates', '# Certificates\n\n6-month certificate APY: 3.75%'),
            page('/promo', '# Promo\n\n6-month certificate APY 8.75% (offer ended 2025-09-30)')))
        a = ks.answer('6-month certificate APY')
        self.assertIn('3.75%', a.text)
        self.assertNotIn('8.75%', a.text)

    def test_balance_tier_and_entity_are_distinct(self):
        ks = build()
        ks.ingest(snap('2026-03-01', page('/personal/savings-account', savings())))
        a = ks.answer('Share Savings APY with a $500 balance')
        self.assertIn('0.05%', a.text)
        self.assertNotIn('0.15%', a.text)
        self.assertNotIn('2.12%', a.text)
        self.assertEqual(ks.conflicts(), [])

    def test_same_rank_disagreement_abstains(self):
        ks = build()
        ks.ingest(snap('2026-03-01', page('/personal/savings-account', cert()),
                       page('/personal/certificates', cert('6.75', '7.25'))))
        a = ks.answer('10-month jumbo certificate APY')
        self.assertFalse(a.confident)
        self.assertTrue(any(c.resolution is None for c in ks.conflicts()))

    def test_unknown_question_abstains(self):
        self.assertFalse(self.ks.answer('What is the annual cost of interplanetary teleportation?').confident)

class SourcePolicyTests(unittest.TestCase):
    def test_overlapping_auto_bands_prefer_official_and_report_conflict(self):
        ks = build()
        def auto(band, value):
            return f'''# Auto Loan Rates
| Loan Program | Term | APR |
| --- | --- | --- |
| {band} Model Year | 60 Months | {value}% APR |
'''
        ks.ingest(snap('2026-03-01',
            page('/personal/loans/auto-motorcycle-loans', auto('2024-27', '6.25')),
            page('/calculators/vehicle-affordability', auto('2023-26', '5.75'))))
        a = ks.answer('APR on a 60-month auto loan for a 2025 car')
        self.assertIn('6.25%', a.text)
        self.assertNotIn('5.75%', a.text)
        self.assertTrue(a.conflict_note)
        report = ks.conflicts()
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0].resolution, '6.25%')
        self.assertEqual(set(report[0].values), {'5.75%', '6.25%'})

    def test_disjoint_model_years_are_not_conflicts(self):
        ks = build()
        ks.ingest(snap('2026-03-01', page('/personal/loans/auto-loans', '''# Auto Loans
| Loan Program | Term | APR |
| --- | --- | --- |
| 2024-27 Model Year | 60 Months | 6.25% |
| 2021-23 Model Year | 60 Months | 7.25% |
''')))
        self.assertEqual(ks.conflicts(), [])

    def test_formatting_does_not_create_conflicts(self):
        ks = build()
        ks.ingest(snap('2026-01-01', page('/personal/savings-account', cert('2.75', '3.25'))))
        ks.ingest(snap('2026-02-01', page('/personal/savings-account', cert('2.750', '3.250'))))
        self.assertEqual(ks.conflicts(), [])

    def test_fee_formatting_and_explanatory_conditions_are_not_price_conflicts(self):
        ks = build()
        ks.ingest(snap('2026-02-01',
            page('/fees/a', '| Service | Fee |\n| --- | --- |\n| Consumer overdrafts | $25.00 per item |'),
            page('/fees/b', '| Service | Fee |\n| --- | --- |\n| Consumer overdrafts | $25.00 per item * Maximum one fee per day. |')))
        self.assertEqual(ks.conflicts(), [])
        a = ks.answer('What is the consumer overdraft fee?')
        self.assertIn('Maximum one fee per day', a.text)
        self.assertTrue(a.confident)

    def test_missing_debit_replacement_does_not_use_rush_delivery_fee(self):
        ks = build()
        ks.ingest(snap('2026-02-01', page('/fees', '# Fees\n\nRush fee for debit card $45.00')))
        self.assertFalse(ks.answer('What is the fee to replace a lost debit card?').confident)

    def test_no_article_teaser_leakage(self):
        ks = build()
        ks.ingest(snap('2026-02-01', page('/newsroom/story', '''# A bank story
A short story about community gardens.

## Handpicked for You

The interplanetary teleportation annual fee is $900.
''')))
        self.assertFalse(ks.answer('What is the annual fee for interplanetary teleportation?').confident)

    def test_header_mismatch_retains_explicit_apr_unit(self):
        ks = build()
        ks.ingest(snap('2026-02-01', page('/personal/loans/auto-loans', '''# Auto Loans
| Loan Program | Term | APY |
| --- | --- | --- |
| 2024-27 Model Year | 60 Months | 6.25% APR |
''')))
        a = ks.answer('APR for a 2025 car on a 60-month loan')
        self.assertIn('6.25% APR', a.text)
        self.assertNotIn('APY', a.text)


class HistoricalProseTests(unittest.TestCase):
    def test_requested_volunteer_year_is_not_replaced_by_newest_count(self):
        ks = build()
        ks.ingest(snap('2026-06-01',
            page('/newsroom/older', '# Volunteers\n\nApril 01, 2024\n\n135 employees used Volunteer Time Off in 2023.'),
            page('/newsroom/newer', '# Volunteers\n\nApril 01, 2025\n\n165 employees used Volunteer Time Off in 2024.')))
        a = ks.answer('How many employees used Volunteer Time Off in 2023?')
        self.assertIn('135', a.text)
        self.assertNotIn('165', a.text)
        self.assertFalse(ks.answer('How many employees used Volunteer Time Off last year?').confident)

    def test_news_counts_use_publication_time_not_fetch_order(self):
        ks = build()
        ks.ingest(snap('2026-06-01',
            page('/newsroom/newer', '# Company update\n\nMay 01, 2026\n\nWe have 18 branch office locations.'),
            page('/newsroom/older', '# Company update\n\nMay 01, 2020\n\nWe have 12 branch office locations.')))
        self.assertIn('18 branch', ks.answer('How many branches are there?').text)
        self.assertEqual(ks.conflicts()[0].resolution, '18')


if __name__ == '__main__':
    unittest.main()
