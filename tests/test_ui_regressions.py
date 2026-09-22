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

    def test_published_page_is_atomic_and_cache_compatible(self):
        builder = (ROOT / 'scripts' / 'build_gallery.py').read_text(encoding='utf8')
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf8')
        self.assertIn("data_script = 'window.COURSE_GALLERY='", builder)
        self.assertIn("index = index.replace(script_tags, data_inline)", builder)
        self.assertIn("index.replace('</body>', app_inline + '</body>')", builder)
        # A stale pre-PG app.js looked this element up unconditionally. Keeping a
        # hidden compatibility target prevents a mixed-cache transition from
        # crashing the page while the new atomic index propagates.
        self.assertIn('id="timelines" hidden', html)


if __name__ == '__main__':
    unittest.main()

class PGUIRegressionTests(unittest.TestCase):
    def test_pg_ui_uses_verified_structure_not_combined_schedule_warning(self):
        app = (ROOT / 'web' / 'app.js').read_text()
        html = (ROOT / 'web' / 'index.html').read_text()
        self.assertNotIn('COMBINED SOURCE SCHEDULE', app)
        self.assertNotIn('Module allocation needs review', html)
        self.assertIn('pgDeliveryCombinations', app)
        self.assertIn('course.routes', app)

    def test_pg_has_mode_delivery_intake_and_pathway_controls(self):
        html = (ROOT / 'web' / 'index.html').read_text()
        for element_id in ('modes', 'pg-deliveries', 'intakes', 'pg-pathway-wrap'):
            self.assertIn(f'id="{element_id}"', html)
