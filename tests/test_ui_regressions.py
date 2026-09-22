from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'web' / 'app.js').read_text(encoding='utf8')
STYLE = (ROOT / 'web' / 'style.css').read_text(encoding='utf8')


class UIRegressionTests(unittest.TestCase):
    def test_all_module_cards_use_the_same_card_layout(self):
        self.assertNotIn('big-credit', APP)
        self.assertNotIn("' project'", APP)
        self.assertNotIn('.card.project', STYLE)
        self.assertNotIn('.project .name', STYLE)

    def test_empty_semester_cells_do_not_render_a_heading_or_placeholder(self):
        self.assertIn("cell.replaceChildren();", APP)
        self.assertIn("cell.setAttribute('aria-hidden', 'true');", APP)
        self.assertNotIn('No modules listed', APP)
        # Columns themselves are still created only from semesters that have
        # visible rows on the selected course route.
        self.assertIn('new Set(mapModules.map(item => item.semester))', APP)

    def test_removed_module_export_disclaimer_stays_removed(self):
        self.assertNotIn(
            'Module-level outcomes, assessments and prerequisites are not included in this course export.',
            APP,
        )


if __name__ == '__main__':
    unittest.main()
