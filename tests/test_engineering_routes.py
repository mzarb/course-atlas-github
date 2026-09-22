import unittest
from pathlib import Path
from scripts.build_gallery import extract, parse

ROOT = Path(__file__).resolve().parents[1]
PDFS = ROOT / 'course-pdfs'


def course_pdf(code):
    matches = sorted(PDFS.glob(f'Course  {code} - *.pdf'))
    if not matches:
        matches = sorted(PDFS.glob(f'Course {code} - *.pdf'))
    if len(matches) != 1:
        raise AssertionError(f'Expected one PDF for course {code}, found {len(matches)}')
    return matches[0]


class EngineeringRouteTests(unittest.TestCase):
    def test_meng_delivery_routes_and_specialisms_are_preserved(self):
        path = course_pdf('0470')
        course = parse(extract(path), path.name)
        self.assertEqual(course['deliveryPathways'], {
            'FAST_TRACK': 'Fast Track',
            'FIVE_YEAR': 'Five Year',
        })
        self.assertEqual(set(course['pathways']), {'A', 'B', 'C'})
        self.assertTrue(course['creditTotalChecked'])

    def test_engineering_design_conflict_is_explicit_but_validation_stays_on(self):
        path = course_pdf('0723')
        text = extract(path)
        course = parse(text, path.name)
        row = next(module for module in course['modules'] if module['code'] == 'CE5004' and module['stage'] == 3)
        self.assertTrue(row['sourceConflict'])
        self.assertTrue(row['excludedFromAward'])
        self.assertTrue(course['creditTotalChecked'])
        self.assertTrue(any('source conflict' in warning.lower() for warning in course['warnings']))

        # A changed declared award total must still block publication. The source
        # conflict is not a switch that disables route credit validation.
        bad = text.replace('SCQF Credit Points                    600', 'SCQF Credit Points                    601', 1)
        with self.assertRaisesRegex(ValueError, 'do not match'):
            parse(bad, path.name)

    def test_msci_lettered_routes_remain_available(self):
        path = course_pdf('0593')
        course = parse(extract(path), path.name)
        self.assertEqual(course['pathways'], {
            'A': 'Industrial Placement',
            'B': 'Study Abroad',
            'C': 'Research Placement',
        })
        self.assertTrue(course['creditTotalChecked'])


if __name__ == '__main__':
    unittest.main()
