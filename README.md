# Course Atlas

Public course diagrams generated from Akari CAD PDFs. You maintain a folder of PDFs; GitHub builds and publishes the gallery. Visitors simply choose a course.

## One-time setup (no GitHub plugin required)

1. Create a **public GitHub repository** called `course-atlas`, with a README so it has a `main` branch.
2. Unzip this package. In the repository, choose **Add file → Upload files** and upload the contents of the extracted folder (not the ZIP or its enclosing folder). Include `course-pdfs`, `scripts`, `web`, `tests`, and README.md.
3. The `.github` folder may be hidden on your computer. If it did not upload, choose **Add file → Create new file**, enter `.github/workflows/publish.yml` as the filename, and paste the entire contents of `WORKFLOW-COPY.txt` from this package. Commit to `main`.
4. Open **Settings → Pages → Build and deployment → Source**, and select **GitHub Actions**.
5. Open **Actions → Build course diagrams and publish → Run workflow**. Choose `main`. When it finishes, the deployment links to your public gallery. The usual address is `https://YOUR-USERNAME.github.io/course-atlas/`.

The package contains the complete workflow in both `.github/workflows/publish.yml` and the visible `WORKFLOW-COPY.txt` to make browser uploading easier. Edit the actual workflow file if you need changes.

## Updating courses

Open **course-pdfs → Add file → Upload files**, upload a new or replacement CAD PDF, and commit. Use the same filename when replacing a course. Keep only one PDF per course code. GitHub regenerates the whole gallery and publishes automatically after successful checks.

To remove a course, delete its PDF and commit. At least one PDF must remain.

No manual module entry, live Akari access, API key or paid AI service is required. This is a saved snapshot: download a fresh CAD when the course changes. The original PDFs are publicly downloadable alongside the diagrams.

## Included views

- **BSc (Hons) Computer Science:** four stages with semester cards, core modules, elective slots, credits and separate additional options. Award credits total 480.
- **MSc Advanced Computing:** September / January / Compare views, with full-time and part-time sequences extracted from the narrative.
- Click a module to see details and a link to its source PDF page.
- Responsive layout and print styling.

## What the source does not tell us

The Advanced Computing public PDF repeats module rows without labelling their full-time/part-time allocation or their individual credits. The gallery therefore shows the confirmed intake timelines above a **combined source schedule**. It does not claim to give a verified module-by-module timetable for each intake. A fuller CAD identifying those allocations is needed to finish that part.

Elective groups remain slots when the PDF does not enumerate their choices. Source warnings are visible in the gallery. The UG table and narrative disagree about CE1337/CM1112; the diagram follows the table and flags that discrepancy.

## Supported PDFs and validation

This initial parser has been checked against the two supplied RGU Akari formats. It is not a universal parser for every university's CAD. It needs a text-based PDF with recognised course headers and stage/semester tables; scanned PDFs are unsupported. Additional formats may require a parser adjustment.

An unreadable file, no recognised schedule, conflicting duplicate row, duplicate course code or inconsistent UG award credit total stops the build. The previous published website remains available. Read the failed run's summary under Actions for the file and error, then replace or remove that PDF.

Missing PG route allocations and individual credits are visible source limitations, not values the importer invents. A successful build does not certify all academic content: inspect each new course against its PDF.

## Local use / development

Requires Python 3 and Poppler (`pdftotext`). On macOS: `brew install poppler`. On Ubuntu: `sudo apt-get install poppler-utils`.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_gallery.py
```

The generated website is in `dist`. For a local web preview, run `python3 -m http.server 8000 --directory dist` and open http://localhost:8000. All paths are relative, so project-based GitHub Pages addresses work. No server-side importer is needed once the site is built.

`web/` contains the interface; `scripts/build_gallery.py` extracts and validates PDFs. The build emits `validation-report.json` with source limitations and errors. No npm dependencies are required.
