import unittest

from network_analysis import (
    build_company_projection,
    build_shareholder_summary,
    records_to_dataframe,
)


class NetworkAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.df = records_to_dataframe(
            [
                {
                    "symbol": "AAA",
                    "company_name": "AAA PUBLIC COMPANY LIMITED",
                    "shareholder": "SHARED HOLDER",
                    "rank": 1,
                    "shares": 100,
                    "percent": 10.0,
                    "as_of": "2026-01-01",
                    "ca_type": "XM",
                    "source_url": "https://example.test/AAA",
                },
                {
                    "symbol": "BBB",
                    "company_name": "BBB PUBLIC COMPANY LIMITED",
                    "shareholder": "SHARED HOLDER",
                    "rank": 2,
                    "shares": 50,
                    "percent": 5.0,
                    "as_of": "2026-01-01",
                    "ca_type": "XM",
                    "source_url": "https://example.test/BBB",
                },
                {
                    "symbol": "BBB",
                    "company_name": "BBB PUBLIC COMPANY LIMITED",
                    "shareholder": "LOCAL HOLDER",
                    "rank": 1,
                    "shares": 70,
                    "percent": 7.0,
                    "as_of": "2026-01-01",
                    "ca_type": "XM",
                    "source_url": "https://example.test/BBB",
                },
            ]
        )

    def test_shareholder_summary_counts_distinct_companies(self):
        summary = build_shareholder_summary(self.df)
        shared = summary[summary["shareholder"] == "SHARED HOLDER"].iloc[0]

        self.assertEqual(shared["company_count"], 2)
        self.assertEqual(shared["total_percent"], 15.0)
        self.assertEqual(shared["companies"], "AAA, BBB")

    def test_company_projection_uses_shared_holder(self):
        projection = build_company_projection(self.df)

        self.assertEqual(len(projection), 1)
        self.assertEqual(projection.iloc[0]["company_a"], "AAA")
        self.assertEqual(projection.iloc[0]["company_b"], "BBB")
        self.assertEqual(projection.iloc[0]["shared_count"], 1)


if __name__ == "__main__":
    unittest.main()
