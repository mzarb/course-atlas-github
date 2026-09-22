Course Atlas overlay: sorted course selector + PG elective schedule fix

Copy these files over the corresponding paths in your current repository.
Do NOT replace course-pdfs/.

Changes:
- Course selector order: UG (BSc/BEng), then integrated Masters (MEng/MSci), then PG (MSc).
- Alphabetical within each group.
- Keeps PG exact elective-group reuse across FT/PT semester schedules (e.g. MSc Advanced Computing 0734).
- Keeps deletion-safe PG tests: deleted CADs are not required by the test suite.

Validated against a working tree with MSc Well Design (0330) absent:
- 30 courses built
- 33 tests pass
