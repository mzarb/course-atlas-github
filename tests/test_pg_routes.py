import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_gallery', ROOT / 'scripts' / 'build_gallery.py')
bg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bg)


def pg_pdf(code):
    return next((ROOT / 'course-pdfs').glob(f'Course  {code} - MSc*.pdf'), None)


class PostgraduateRouteTests(unittest.TestCase):
    def require_pg_pdf(self, code):
        path = pg_pdf(code)
        if path is None:
            self.skipTest(f'MSc CAD {code} is not present in course-pdfs')
        return path

    def parse_code(self, code):
        path = self.require_pg_pdf(code)
        return bg.parse(bg.extract(path), path.name)

    def test_all_msc_cads_pass_delivery_and_credit_validation(self):
        courses = []
        for path in sorted((ROOT / 'course-pdfs').glob('Course*.pdf')):
            text = bg.extract(path)
            if not re.search(r'Course Type\s+Postgraduate', text):
                continue
            course = bg.parse(text, path.name)
            self.assertTrue(course['allocationVerified'], path.name)
            self.assertTrue(course['creditTotalChecked'], path.name)
            self.assertTrue(course['pgDeliveryCombinations'], path.name)
            courses.append(course)
        # The PDFs in course-pdfs are the source of truth. Courses may be
        # intentionally removed without requiring the test suite to be edited.
        self.assertTrue(courses, 'No postgraduate CADs were found')

    def test_pg_credit_validation_still_blocks_a_bad_award_total(self):
        path = self.require_pg_pdf('0558')
        text = bg.extract(path).replace('SCQF Credit Points                    180', 'SCQF Credit Points                    181', 1)
        with self.assertRaisesRegex(ValueError, 'postgraduate award credits'):
            bg.parse(text, path.name)

    def test_it_programme_collapses_placement_routes_to_four_pathways(self):
        course = self.parse_code('0548')
        self.assertEqual(
            {'IT', 'IT with Artificial Intelligence', 'IT with Business Intelligence', 'IT with Cyber Security'},
            set(course['pathways'].values()),
        )
        self.assertFalse(any('Placement' in value for value in course['pathways'].values()))

    def test_renewable_energy_collapses_to_two_subject_pathways(self):
        course = self.parse_code('0657')
        self.assertEqual({'Design and Innovation', 'Operation and Maintenance'}, set(course['pathways'].values()))

    def test_placement_modules_are_optional_and_outside_award(self):
        course = self.parse_code('0502')
        placements = [m for m in course['modules'] if m.get('placementOption')]
        self.assertEqual({'CEM104', 'CEM105'}, {m['code'] for m in placements})
        self.assertTrue(all(m['additional'] for m in placements))

    def test_games_keeps_special_part_time_january_sequence(self):
        course = self.parse_code('0733')
        sequence = course['routes']['Part-Time']['January']
        self.assertEqual([1, 3, 2, 4, 5], [step['semester'] for step in sequence])
        self.assertEqual(['January', 'September', 'January', 'September', 'January'], [step['month'] for step in sequence])

    def test_intake_restrictions_remain_delivery_specific(self):
        course = self.parse_code('0733')
        studio = next(m for m in course['modules'] if m['code'] == 'CEM007' and m['semester'] == 1)
        by_delivery = {v['deliveryId']: v['intakeIds'] for v in studio['pgVariants']}
        self.assertEqual(['September'], by_delivery['FULL_CAMPUS'])
        self.assertEqual([], by_delivery['PART_CAMPUS'])

    def test_business_analytics_omits_mdis(self):
        course = self.parse_code('0573')
        self.assertEqual('MSc Business Analytics', course['title'])
        self.assertIn('The MDIS delivery in the CAD is omitted; this atlas shows RGU delivery only.', course['warnings'])
        self.assertEqual({'FULL_CAMPUS', 'PART_CAMPUS', 'PART_ONLINE'}, set(course['pgDeliveryCombinations']))

    def test_legacy_well_courses_use_flexible_intake(self):
        # 0329 is the remaining flexible-intake legacy well course in the
        # current source set. If it is deliberately removed later, skip this
        # source-specific regression rather than blocking course deletion.
        self.assertTrue(self.parse_code('0329')['flexibleIntake'])

    def test_pg_elective_group_can_move_between_ft_and_pt_semesters(self):
        course = {'level': 'PG'}
        group = {
            'code': '0734 - Electives 1',
            'members': [
                {'stage': 1, 'semester': 1, 'code': 'CMM999', 'title': 'Example Option', 'credits': 15, 'page': 1},
            ],
        }
        pt_slot = {'stage': 1, 'semester': 3, 'code': '0734 - Electives 1', 'additional': False}
        self.assertEqual(group['members'], bg.resolve_group_members(course, pt_slot, group))

    def test_advanced_computing_reuses_exact_groups_across_ft_pt_schedule(self):
        course = self.parse_code('0734')
        group1 = {
            'code': '0734 - Electives 1',
            'members': [
                {'stage': 1, 'semester': 1, 'code': 'CMM999', 'title': 'Example Option 1', 'credits': 15, 'page': 1},
            ],
        }
        group2 = {
            'code': '0734 - Electives 2',
            'members': [
                {'stage': 1, 'semester': 2, 'code': 'CMM998', 'title': 'Example Option 2', 'credits': 15, 'page': 1},
            ],
        }
        slots1 = [m for m in course['modules'] if m['code'] == '0734 - Electives 1']
        slots2 = [m for m in course['modules'] if m['code'] == '0734 - Electives 2']
        self.assertEqual({1, 3}, {m['semester'] for m in slots1})
        self.assertEqual({2, 4}, {m['semester'] for m in slots2})
        self.assertTrue(all(bg.resolve_group_members(course, m, group1) for m in slots1))
        self.assertTrue(all(bg.resolve_group_members(course, m, group2) for m in slots2))

    def test_ug_elective_group_still_requires_matching_semester(self):
        course = {'level': 'UG'}
        group = {
            'code': 'PS0071 - Electives 1',
            'members': [
                {'stage': 1, 'semester': 1, 'code': 'CM1122', 'title': 'AI, Data and Society', 'credits': 15, 'page': 1},
            ],
        }
        wrong_semester = {'stage': 1, 'semester': 2, 'code': 'PS0071 - Electives 1', 'additional': False}
        self.assertEqual([], bg.resolve_group_members(course, wrong_semester, group))


if __name__ == '__main__':
    unittest.main()
