import unittest
from scripts.build_gallery import parse, parse_group, group_key

HEADER='Course 1234 - Example · 21 September 2026\nCourse Type Undergraduate\nSCQF Credit Points 15\n'
class UGRegressionTests(unittest.TestCase):
 def test_module_after_page_break(self):
  c=parse(HEADER+'Stage 1 / Semester 1\nCore\nTime   CM1120   Database Systems    Yes   3.0  15 Level 7\n','test.pdf')
  self.assertEqual(c['modules'][0]['code'],'CM1120')
 def test_group_code_without_space(self):
  c=parse(HEADER+'Stage 1 / Semester 1\nElective\nPS1234 - Electives10   Choice group   1.0   15\n','test.pdf')
  self.assertEqual(group_key(c['modules'][0]['code']),group_key('PS1234 - Electives 10'))
 def test_additional_90_credit_group(self):
  c=parse(HEADER+'credits accumulated do not contribute to the award total\nStage 1 / Semester 1\nCore\nCM1120   Database Systems   1.0   15\nStage 2 / Semester 3\nElective\n1234 - Electives 5   Placement group   1.0   90\n','test.pdf')
  self.assertTrue(c['modules'][1]['additional'])
 def test_wrapped_group_semester(self):
  g=parse_group('Group Code  PS1234 - Electives 7\nGroup Title  Choice group\n3  Semester  Elective  CM3152  Artificial Intelligence  Yes  2.0  15\n   2\n','test.pdf')
  self.assertEqual(g['members'][0]['semester'],2)
 def test_unreadable_semester_is_not_guessed(self):
  with self.assertRaisesRegex(ValueError,'Wrapped semester'):
   parse_group('Group Code  PS1234 - Electives 7\nGroup Title  Choice group\n3  Semester  Elective  CM3152  Artificial Intelligence  Yes  2.0  15\n','test.pdf')
