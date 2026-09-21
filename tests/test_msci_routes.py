import unittest
from scripts.build_gallery import parse
class RouteTests(unittest.TestCase):
 def test_each_route_checked(self):
  text="Course 1234 - Example · Today\nCourse Type Undergraduate\nSCQF Credit Points 60\nRoute A - Placement. Route B - Abroad.\nCE2020 Short Placement is for additional credit only.\nStage 1 / Semester 1\nCore\nCM1000  Common Module  1.0  15\nCM1001  Placement  Route A  Yes  1.0  45\nCM1002  Abroad  Route B  Yes  1.0  45\nStage 1 / Semester 3\nElective\nCE2020  Short Placement  1.0  15\n"
  c=parse(text,'test.pdf')
  self.assertEqual(set(c['pathways']),{'A','B'})
  self.assertTrue(c['modules'][-1]['additional'])
  with self.assertRaisesRegex(ValueError,'Route B'):
   parse(text.replace('Abroad  Route B  Yes  1.0  45','Abroad  Route B  Yes  1.0  30'),'test.pdf')
