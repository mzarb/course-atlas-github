# Course Atlas

Public course diagrams generated from Akari CAD PDFs. Maintain the source PDFs in the repository; GitHub validates them, rebuilds the gallery, and publishes the generated site.

## One-time setup

1. Create a **public GitHub repository** called `course-atlas`, with a README so it has a `main` branch.
2. Unzip this package. In the repository, choose **Add file → Upload files** and upload the contents of the extracted folder (not the ZIP or its enclosing folder). Include `course-pdfs`, `scripts`, `web`, `tests`, and `README.md`.
3. The `.github` folder may be hidden on your computer. If it did not upload, choose **Add file → Create new file**, enter `.github/workflows/publish.yml` as the filename, and paste the contents of `WORKFLOW-COPY.txt` from this package. Commit to `main`.
4. Open **Settings → Pages → Build and deployment → Source**, and select **GitHub Actions**.
5. Open **Actions → Build course diagrams and publish → Run workflow**. Choose `main`.

The package contains the workflow in both `.github/workflows/publish.yml` and `WORKFLOW-COPY.txt` to make browser uploading easier.

## Updating courses

Open **course-pdfs → Add file → Upload files**, upload a new or replacement CAD PDF, and commit. Use the same filename when replacing a course and keep only one PDF per course code. GitHub regenerates the whole gallery after the checks pass.

To remove a course, delete its PDF and commit. At least one course PDF must remain.

The PDFs are build inputs only. The generated `dist` site does **not** copy them, expose source-PDF links, or require live Akari access, an API key, or a paid AI service.

## Included behaviour

- Undergraduate stages are rows and semesters are aligned columns.
- A Semester 3 column is only created when the selected route actually contains a Semester 3 row.
- Elective group PDFs are expanded as **Choose one from** choices.
- MSci lettered routes are retained and independently credit-validated.
- Postgraduate courses are intake-aware: the selected September/January intake reorders the CAD semesters into the sequence actually published for that intake.
- Postgraduate Full-Time/Part-Time and On-Campus/Online delivery combinations are read from the CAD rather than inferred from course duration.
- PG subject pathways are shown separately from placement variants. Short and year-long postgraduate placements appear as optional module cards instead of top-level course routes.
- PG courses with intakes throughout the year are shown as a flexible sequence rather than being forced into September/January.
- The MDIS delivery embedded in MSc Business Analytics is intentionally omitted; Course Atlas shows the RGU delivery only.
- Engineering BEng additional placement/study-abroad options are retained but excluded from the award total only where the CAD explicitly states they are additional credits.
- Engineering MEng **Fast Track** and **Five Year** routes are reconstructed from the route structure documented in the CAD and independently credit-validated. Courses that also have lettered specialisms validate every delivery-route/specialism combination.
- Click a module or elective group to inspect its details and choices. The public gallery does not link back to the source PDFs.
- Responsive layout and print styling are included.

## Engineering source-data handling

The engineering PDFs wrap delivery-range, notes, module-level and credit fields across multiple lines and sometimes across page breaks. The importer reassembles those fields rather than treating each wrapped line as a separate module row.

The supplied MEng Engineering Design CAD contains one internally contradictory row: **CE5004 Industrial Automation and Robotics** has a `Five Year` delivery range while its Notes field says `Fast Track Only`. Course Atlas keeps that row visible as a **source conflict** instead of silently forcing it into a route. It is excluded from route totals, and both published route totals still have to match the declared award credits for the build to succeed.

## Validation

Validation is deliberately blocking. A build fails for an unreadable file, no recognised schedule, conflicting duplicate row, duplicate course code, missing route name, an invalid supplied elective-group mapping, or an inconsistent award-credit total. If an elective-group PDF has not been supplied at all, the credit-bearing slot remains visible and is explicitly flagged as unexpanded rather than inventing its choices.

For routes, the checks are performed independently:

- ordinary lettered routes: each route must match the declared award credits;
- engineering integrated masters: Fast Track and Five Year must each match;
- engineering courses with specialisms: every delivery-route/specialism combination must match.

Additional-credit options are excluded only when the source text explicitly identifies them as outside the award total. A flagged source-data contradiction is handled explicitly and does not switch credit checking off. The build emits `validation-report.json` with warnings and errors.

Postgraduate validation is also blocking. Each published Full-Time/Part-Time + On-Campus/Online combination is validated against the declared MSc award credits. Where September/January intake-specific rows exist, both intakes are checked independently; where genuine subject pathways exist, every pathway is checked too. Placement modules are excluded from the 180-credit total only because these CADs explicitly state that their credits are additional. Missing PG delivery allocation or missing module credits prevents publication.

Some CADs repeat pathway route letters inconsistently in later part-time rows. Course Atlas preserves the row-level delivery/intake data, but canonicalises a module's subject-pathway membership from its unambiguous full-time occurrence of the same module code where available. This is still subject to the independent 180-credit validation for every displayed PG combination.

## Local use / development

Requires Python 3 and Poppler (`pdftotext`). On macOS: `brew install poppler`. On Ubuntu: `sudo apt-get install poppler-utils`.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_gallery.py
node --check web/app.js
```

The published `dist/index.html` embeds the generated course data and application script together, preventing browser/GitHub Pages cache mismatches between releases. Stable external script copies remain only for compatibility with an already-cached older page.

The generated website is in `dist`. For a local preview, run:

```sh
python3 -m http.server 8000 --directory dist
```

Then open `http://localhost:8000`. All published paths are relative, so project-based GitHub Pages addresses work. `web/` contains the interface; `scripts/build_gallery.py` extracts and validates PDFs.
