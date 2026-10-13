"""Regression tests from real official-site collection failures."""
import unittest

from airworthiness.acquire import extract_html


class AcquisitionResilienceTests(unittest.TestCase):
    def test_nested_hidden_elements_do_not_abort_other_article_content(self):
        html = '<html><title>条例</title><div hidden><span style="display:none">隐藏导航</span></div><div class="TRS_Editor"><p>第一条 适用范围。</p><p>第二条 ' + '真实公开正文。' * 80 + '</p></div></html>'
        result = extract_html(html.encode(), 'https://www.caac.gov.cn/test.html')
        self.assertEqual(result.content_kind, 'fulltext')
        self.assertIn('第一条', result.markdown)
        self.assertNotIn('隐藏导航', result.markdown)


if __name__ == '__main__':
    unittest.main()
