import unittest
from scripts.build_gallery import parse, intake_routes

HEADER = "Course 1234 - Example Course · 21 September 2026\nCourse Type Undergraduate\nSCQF Credit Points 20\n"
ROW = "Stage 1 / Semester 1\nCore\nCM1234  Example Module  1.0  20  Level 7\n"

class ParserTests(unittest.TestCase):
 def test_credit_validation(self):
  course=parse(HEADER+ROW, 'example.pdf')
  self.assertEqual(course['modules'][0]['credits'],20)
  self.assertTrue(course['creditTotalChecked'])
  with self.assertRaisesRegex(ValueError,'do not match'):
   parse(HEADER.replace('Points 20','Points 40')+ROW,'example.pdf')
 def test_missing_schedule_rejected(self):
  with self.assertRaisesRegex(ValueError,'No stage'):
   parse(HEADER,'example.pdf')
 def test_repeated_rows_and_conflicts(self):
  self.assertEqual(len(parse(HEADER+ROW+ROW,'example.pdf')['modules']),1)
  with self.assertRaisesRegex(ValueError,'Conflicting'):
   parse(HEADER+ROW+ROW.replace('Example Module','Different Module'),'example.pdf')
 def test_pg_missing_credits_not_invented(self):
  c=parse(HEADER.replace('Undergraduate','Postgraduate')+ROW.replace('  1.0  20  Level 7',''),'example.pdf')
  self.assertIsNone(c['modules'][0]['credits'])
  self.assertFalse(c['allocationVerified'])
 def test_january_sequence_crosses_year(self):
  text='Full-Time Students For January entry, the sequence of modules will be: Semester 2 (taken in January) Semester 1 (taken in September) Semester 3 (project taken in January) Part-Time Students Online Learning'
  steps=intake_routes(text)['Full-Time']['January']
  self.assertEqual([s['semester'] for s in steps],[2,1,3])
  self.assertEqual([s['year'] for s in steps],[1,1,2])

if __name__=='__main__': unittest.main()
