"""Build a static course gallery from Akari PDF exports. Requires pdftotext (Poppler)."""
from pathlib import Path
import argparse, datetime, hashlib, json, re, shutil, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
CODE = r'(?:PS\d+\s*-\s*Electives\s*\d+|\d{4}\s*-\s*Electives\s*\d+|[A-Z]{2,4}\d{3,4})'
CODE_RE = re.compile(r'(?<!\S)(' + CODE + r')(?=\s{2,}|\s*$)')
CREDIT_RE = re.compile(r'(?:Yes|No)?\s*\d+\.\d+\s+(\d+)(?:\s+(?:Level(?:\s+\d+)?|\d+))?\s*$')
DELIVERY_NAMES = {'FAST_TRACK': 'Fast Track', 'FIVE_YEAR': 'Five Year'}


def extract(path):
    p = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, text=True, check=True)
    return p.stdout


def intake_routes(text):
    clean = re.sub(r'^Course .*?·.*$|^Page \d+ of \d+\s*$', '', text, flags=re.M)
    flat = ' '.join(clean.split())
    result = {}
    for mode, following in [('Full-Time', 'Part-Time'), ('Part-Time', 'Online Learning')]:
        m = re.search(re.escape(mode) + r' Students(.*?)' + re.escape(following), flat)
        if not m:
            continue
        result[mode] = {}
        for match in re.finditer(r'For (September|January) entry, the sequence of modules will be:\s*(.*?)(?=For (?:September|January) entry|$)', m[1]):
            steps = []
            year = 1
            last = 0
            for x in re.finditer(r'Semester (\d+)\s*\(([^)]+)\)', match[2]):
                month = re.search(r'taken in (September|January|May)', x[2])
                if not month:
                    continue
                monthnum = {'January': 1, 'May': 5, 'September': 9}[month[1]]
                if monthnum < last:
                    year += 1
                last = monthnum
                steps.append({
                    'semester': int(x[1]), 'month': month[1], 'year': year,
                    'project': 'project' in x[2].lower(),
                    'spansTwoSemesters': 'spanning 2 semesters' in x[2]
                })
            if steps:
                result[mode][match[1]] = steps
    return {k: v for k, v in result.items() if v}


def extract_route_names(text):
    """Read lettered course routes from headings, whether or not Akari ends them with full stops."""
    result = {}
    for line in text.splitlines():
        if 'Route ' not in line:
            continue
        for m in re.finditer(r'Route\s+([A-Z])\s*-\s*(.*?)(?=\s+Route\s+[A-Z]\s*-|$)', line):
            name = m.group(2).strip().rstrip(' .;')
            if name and len(name) < 120:
                result.setdefault(m.group(1), name)
    return result


def table_columns(line):
    """Return character starts for the Akari delivery-table columns."""
    code = line.find('Code')
    title = line.find('Title')
    if code < 0 or title <= code:
        return None
    result = {'code': code, 'title': title}
    for label, key in [('Notes', 'notes'), ('Owner', 'owner'), ('Allow', 'allow'), ('Version', 'version'), ('Credits', 'credits'), ('Module', 'module')]:
        pos = line.find(label)
        if pos >= 0:
            result[key] = pos
    return result


def cell_fragments(lines, row_index, start, end, radius=2):
    """Reassemble wrapped text in a table cell around a module row."""
    parts = []
    lo = max(0, row_index - radius)
    hi = min(len(lines), row_index + radius + 1)
    for j in range(lo, hi):
        line = lines[j]
        if j != row_index and CODE_RE.search(line):
            continue
        if re.match(r'^\s*(?:Stage \d+ / Semester \d+|Course \d+ -|Page \d+ of \d+|Core\s*$|Elective\s*$|Optional\s*$)', line):
            continue
        piece = line[start:end].strip() if end else line[start:].strip()
        if not piece or piece in {'Title', 'Notes', 'Owner', 'Allow', 'Mapping', 'Version', 'Credits', 'Module', 'Level'}:
            continue
        if piece not in parts:
            parts.append(piece)
    return ' '.join(parts).strip()


def delivery_ids_near(lines, row_index, code_column):
    """Read the wrapped Delivery Range cell for an engineering MEng row.

    Akari renders Delivery Range vertically to the *left* of the module code,
    while Notes (including phrases such as "Fast Track Only") sits to the
    right. Restricting this scan to the left-hand prefix keeps those two source
    fields independent, which is important when the PDF itself contradicts
    them.
    """
    lo = max(0, row_index - 4)
    hi = min(len(lines), row_index + 6)
    prefixes = []
    for j in range(lo, hi):
        line = lines[j].replace('\f', '')
        if j != row_index and CODE_RE.search(line):
            continue
        prefixes.append(line[:code_column].strip())
    local = ' '.join(x for x in prefixes if x)
    found = []
    if re.search(r'\bFast\b', local, re.I) and re.search(r'\bTrack\b', local, re.I):
        found.append('FAST_TRACK')
    if ((re.search(r'\bFive\b', local, re.I) or re.search(r'\b5\b', local))
            and re.search(r'\bYear\b', local, re.I)):
        found.append('FIVE_YEAR')
    return found


def parse_route_ids(notes):
    ids = []
    for m in re.finditer(r'\bRoutes?\s+([A-Z](?:\s*,\s*[A-Z])*)\b', notes):
        ids.extend(re.findall(r'[A-Z]', m.group(1)))
    return sorted(set(ids))


def note_delivery_ids(notes):
    result = []
    if re.search(r'Fast\s*Track\s*Only', notes, re.I):
        result.append('FAST_TRACK')
    if re.search(r'(?:Five[- ]Year|5\s*Year)\s*Only', notes, re.I):
        result.append('FIVE_YEAR')
    return result


def parse(text, filename):
    head = re.search(r'^Course\s+(\d+)\s*-\s*(.*?)\s*·\s*(.+)$', text, re.M)
    if not head:
        raise ValueError('Course code, title or export date not recognised')
    code, title, date = head.groups()
    pg = bool(re.search(r'Course Type\s+Postgraduate', text))
    credit = re.search(r'SCQF Credit Points\s+(\d+)', text)
    if not credit:
        raise ValueError('Award credit total not found')

    lines = text.split('\n')
    modules = []
    current = None
    kind = 'core'
    seen = {}
    page = 1
    duplicates = 0
    columns = None

    for i, raw_line in enumerate(lines):
        page += raw_line.count('\f')
        line = raw_line.replace('\f', '')
        if line.strip() == 'Course Deliveries':
            break

        heading = re.match(r'^\s*Stage\s+(\d+)\s*/\s*Semester\s+(\d+)\s*$', line)
        if heading:
            current = tuple(map(int, heading.groups()))
            columns = None
            continue
        if not current:
            continue
        if line.strip() in ('Core', 'Elective', 'Optional'):
            kind = line.strip().lower()
            continue

        found_columns = table_columns(line)
        if found_columns:
            columns = found_columns
            continue

        match = CODE_RE.search(line)
        if not match:
            continue
        c = match.group(1).strip()

        # Most Akari rows keep the title directly after the code even when the
        # page-break geometry shifts. Prefer that textual structure. Only fall
        # back to the table column when a long title has wrapped off the code row.
        # The no-column branch also keeps the small synthetic regression fixtures
        # useful without weakening validation of real PDF tables.
        after = line[match.end():]
        segments = [x.strip() for x in re.split(r'\s{2,}', after) if x.strip()]
        name = ''
        if not columns:
            if segments and not re.match(r'^(?:Routes?\b|Yes$|No$|Level\b|\d+(?:\.\d+)?$)', segments[0]):
                name = segments[0]
        elif segments:
            candidate = segments[0]
            leading = len(after) - len(after.lstrip())
            candidate_pos = match.end() + leading
            owner_pos = columns.get('owner', 10**9)
            structural = bool(re.match(r'^(?:Routes?\b|Yes$|No$|Level\b|\d+(?:\.\d+)?$)', candidate))
            if not structural and candidate_pos < owner_pos - 4 and candidate_pos - match.end() < 60:
                name = candidate

        if columns and not name:
            title_start = columns['title']
            title_end = min((columns[k] for k in ('notes', 'owner', 'allow', 'version', 'credits', 'module') if k in columns and columns[k] > title_start), default=None)
            name = cell_fragments(lines, i, max(columns['code'] + 1, title_start - 4), title_end, radius=1)
        if not name:
            raise ValueError('Empty module title for ' + c)

        route_segments = [x for x in segments if re.match(r'^Routes?\s+[A-Z](?:\s*,\s*[A-Z])*$', x)]
        notes = ' '.join(route_segments)
        if columns and not notes:
            note_start = columns.get('notes')
            if note_start is not None:
                note_end = min((columns[k] for k in ('owner', 'allow', 'version', 'credits', 'module') if k in columns and columns[k] > note_start), default=None)
                notes = cell_fragments(lines, i, note_start, note_end, radius=1)
            else:
                notes = ''

        credits = CREDIT_RE.search(line)
        value = int(credits[1]) if credits else None
        group = 'electives' in c.lower()
        row_routes = parse_route_ids(notes)
        local = ' '.join(x.strip() for x in lines[max(0, i - 2):min(len(lines), i + 3)])
        item = {
            'stage': current[0], 'semester': current[1], 'code': c, 'title': name,
            'credits': value, 'type': 'elective' if group else kind, 'page': page,
            'additional': False, 'routeIds': row_routes,
            'deliveryIds': [],
            '_deliveryHints': delivery_ids_near(lines, i, match.start()) if columns else [],
            '_noteDeliveryIds': note_delivery_ids(notes),
            'spansSemesters': 2 if re.search(r'Undertaken over two semesters', local, re.I) else 1
        }

        key = (current, c)
        if key in seen:
            old = modules[seen[key]]
            if old['title'] != name or old['credits'] != value:
                raise ValueError('Conflicting repeated row: ' + c)
            old['routeIds'] = sorted(set(old['routeIds']) | set(row_routes))
            old['_deliveryHints'] = sorted(set(old['_deliveryHints']) | set(item['_deliveryHints']))
            old['_noteDeliveryIds'] = sorted(set(old['_noteDeliveryIds']) | set(item['_noteDeliveryIds']))
            duplicates += 1
            continue
        seen[key] = len(modules)
        modules.append(item)

    if not modules:
        raise ValueError('No stage/semester module rows found; scanned or unsupported PDF')

    warnings = []
    flat = ' '.join(text.split())
    flat_lower = flat.lower()

    # Some CADs explicitly state that credits accumulated in a standalone
    # Semester 3 option do not contribute to the award total. Preserve the older
    # format rule as well as the engineering-specific wording below.
    non_award_credit_statement = 'credits accumulated do not contribute to the award total' in flat_lower
    if non_award_credit_statement and not pg:
        for m in modules:
            peers = [x for x in modules if (x['stage'], x['semester']) == (m['stage'], m['semester'])]
            if m['semester'] == 3 and len(peers) == 1 and m['type'] == 'elective':
                m['additional'] = True

    # Engineering CADs state that placement/study-abroad credits are additional to
    # taught-stage credits. Their Semester 3 elective group can contain 15, 30 or
    # 120-credit choices, so exclude the group from award validation while retaining it.
    placement_is_additional = bool(
        re.search(r'credits (?:awarded|achieved) for (?:the )?(?:placement|study abroad|placement or study abroad)[^.]{0,180}\bin addition to\b', flat_lower)
        or re.search(r'credits achieved for (?:placement|study abroad)[^.]{0,180}\bin addition to\b', flat_lower)
    )
    for m in modules:
        if placement_is_additional and m['semester'] == 3 and m['type'] == 'elective' and (m['credits'] or 0) >= 90:
            m['additional'] = True
        if re.search(r'\b' + re.escape(m['code']) + r'\s+[^.]*?is for additional credit only\.', flat, re.I):
            m['additional'] = True

    route_names = extract_route_names(text)
    used_routes = sorted({r for m in modules for r in m['routeIds']})
    pathways = {r: route_names[r].strip() for r in used_routes if r in route_names}
    missing_route_names = [r for r in used_routes if r not in pathways]
    if missing_route_names:
        raise ValueError('Route names not found for: ' + ', '.join(missing_route_names))

    # Engineering integrated masters expose two delivery routes. The PDFs describe
    # Fast Track as completing Stage 5 through the summer periods after Stages 3
    # and 4, while the conventional route uses a fifth academic year. Akari's
    # row-level delivery labels are heavily wrapped (and can straddle page breaks),
    # so reconstruct the two routes from that documented stage/semester structure.
    # Credit validation below then independently proves that every route still
    # reaches the declared award total.
    has_both_engineering_routes = bool(
        re.search(r'Fast\s*Track', text, re.I)
        and re.search(r'(?:\b5|Five)\s*Year', text, re.I)
        and re.search(r'4\s+(?:calendar|academic)\s+years?\s*\(10 semesters\)', text, re.I)
    )
    delivery_pathways = {}
    if has_both_engineering_routes:
        delivery_pathways = {'FAST_TRACK': DELIVERY_NAMES['FAST_TRACK'], 'FIVE_YEAR': DELIVERY_NAMES['FIVE_YEAR']}
        for m in modules:
            if m['stage'] >= 5:
                m['deliveryIds'] = ['FIVE_YEAR']
            elif m['semester'] == 3:
                m['deliveryIds'] = ['FIVE_YEAR'] if m['additional'] else ['FAST_TRACK']
            else:
                m['deliveryIds'] = ['FAST_TRACK', 'FIVE_YEAR']

        # A contradictory Akari row cannot be assigned to either published route
        # without breaking the declared award total. Keep it visible and explicit,
        # but do not silently force it into a route. This is a source-data conflict,
        # not a disabled credit check.
        for m in modules:
            hints = set(m.get('_deliveryHints', []))
            notes_only = set(m.get('_noteDeliveryIds', []))
            if hints and notes_only and hints.isdisjoint(notes_only):
                m['sourceConflict'] = True
                m['excludedFromAward'] = True
                m['deliveryIds'] = ['FAST_TRACK', 'FIVE_YEAR']
                hint_names = ', '.join(DELIVERY_NAMES[x] for x in sorted(hints))
                note_names = ', '.join(DELIVERY_NAMES[x] for x in sorted(notes_only))
                warnings.append(
                    f"{m['code']}: source conflict — delivery range says {hint_names}, while Notes says {note_names} Only. "
                    'The row is shown but excluded from route credit totals; both published routes are still validated against the declared award credits.'
                )

    known = all(m['credits'] is not None for m in modules)
    if not known:
        warnings.append('Individual module/group credits are not included in this export. They have not been inferred.')
    if pg:
        warnings.append('This export does not identify the full-time/part-time allocation of each schedule row. Intake sequences are confirmed from the narrative; the module lists are a combined source schedule, not a verified route timetable.')
    if any(m['type'] == 'elective' for m in modules):
        warnings.append('Elective groups are shown as slots. Their individual choices are not included in this course PDF.')
    if 'CM1112' in text and any(m['code'] == 'CE1337' for m in modules):
        warnings.append('The delivery table lists CE1337 Programming Bootcamp; a narrative note still refers to CM1112 Introduction to Programming. The diagram follows the table.')

    if known and not pg:
        route_checks = list(pathways) or [None]
        delivery_checks = list(delivery_pathways) or [None]
        for route in route_checks:
            for delivery in delivery_checks:
                included = [
                    m for m in modules
                    if not m['additional'] and not m.get('excludedFromAward')
                    and (route is None or not m['routeIds'] or route in m['routeIds'])
                    and (delivery is None or not m['deliveryIds'] or delivery in m['deliveryIds'])
                ]
                total = sum(m['credits'] for m in included)
                if total != int(credit[1]):
                    labels = []
                    if route:
                        labels.append('Route ' + route)
                    if delivery:
                        labels.append(DELIVERY_NAMES.get(delivery, delivery))
                    suffix = ' for ' + ' / '.join(labels) if labels else ''
                    raise ValueError(
                        f'Listed award credits ({total}) do not match declared award credits ({credit[1]}){suffix}. '
                        'Review delivery variants or optional modules before publishing.'
                    )

    for m in modules:
        m.pop('_deliveryHints', None)
        m.pop('_noteDeliveryIds', None)

    routes = intake_routes(text) if pg else {}
    if pg and not routes:
        warnings.append('No intake sequences were recognised. Only the published semester schedule is shown.')

    return {
        'id': code, 'title': title, 'level': 'PG' if pg else 'UG',
        'awardCredits': int(credit[1]), 'sourceDate': date.strip(), 'sourceFile': filename,
        'modules': modules, 'routes': routes, 'pathways': pathways,
        'deliveryPathways': delivery_pathways, 'warnings': warnings,
        'duplicatesCollapsed': duplicates, 'allocationVerified': not pg,
        'creditTotalChecked': known and not pg
    }


def group_key(code):
    return re.sub(r'\s+', '', code.upper())


def parse_group(text, filename):
    code = re.search(r'^\s*Group Code\s+(.+)$', text, re.M)
    title = re.search(r'^\s*Group Title\s+(.+)$', text, re.M)
    if not code or not title:
        raise ValueError('Group code or title not found')
    members = []
    page = 1
    lines = text.split('\n')
    for index, line in enumerate(lines):
        if re.match(r'^\s*\d+\s+Semester\s+Elective\s+', line):
            following = lines[index + 1] if index + 1 < len(lines) else ''
            number = re.fullmatch(r'\s*(\d+)\s*', following)
            if not number:
                raise ValueError('Wrapped semester number not recognised')
            line = line.replace('Semester', 'Semester ' + number[1], 1)
        page += line.count('\f')
        m = re.match(r'^\s*(\d+)\s+Semester\s+(\d+)\s+Elective\s+([A-Z]{2,4}\d{3,4})\s{2,}(.+?)\s{2,}(?:Yes|No)\s+\d+\.\d+\s+(\d+)\s*$', line)
        if m:
            stage, sem, c, name, credits = m.groups()
            members.append({'stage': int(stage), 'semester': int(sem), 'code': c, 'title': name.strip(), 'credits': int(credits), 'page': page})
    if not members:
        raise ValueError('No elective module rows recognised')
    return {
        'code': code[1].strip(), 'title': re.sub(r'\s+APPROVED$', '', title[1].strip()),
        'rule': 'Choose one from', 'members': members, 'sourceFile': filename
    }


def build(source, out):
    for asset in ('index.html', 'app.js', 'style.css'):
        if not (ROOT / 'web' / asset).is_file():
            raise ValueError('Missing website file: web/' + asset + '. Restore it before publishing.')
    pdfs = sorted(p for p in source.rglob('*') if p.suffix.lower() == '.pdf')
    if not pdfs:
        raise ValueError('No PDFs found in ' + str(source))

    courses = []
    groups = {}
    errors = []
    for p in pdfs:
        try:
            text = extract(p)
            if re.search(r'^\s*Group Code\s+', text, re.M):
                g = parse_group(text, p.name)
                key = group_key(g['code'])
                if key in groups:
                    old = groups[key]
                    if ' '.join(text.split()) == old['_text']:
                        print('Identical group copy ignored: ' + p.name)
                        continue
                    raise ValueError('Conflicting duplicate elective group: ' + g['code'])
                g['_text'] = ' '.join(text.split())
                g['_path'] = p
                groups[key] = g
                continue
            c = parse(text, p.name)
            c['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
            c['_path'] = p
            courses.append(c)
        except Exception as e:
            errors.append(f'{p.name}: {e}')

    if not courses:
        errors.append('No course PDFs found')

    for c in courses:
        unresolved = []
        for m in c['modules']:
            if m['type'] != 'elective' or 'electives' not in m['code'].lower():
                continue
            g = groups.get(group_key(m['code']))
            if not g:
                unresolved.append(m['code'])
                continue
            members = [x for x in g['members'] if x['stage'] == m['stage'] and x['semester'] == m['semester']]
            if not members and m['additional']:
                members = g['members']
                m['groupNote'] = (
                    'The course references this additional group here; the group PDF lists its choices under ' +
                    ', '.join(sorted({f"Stage {x['stage']} / Semester {x['semester']}" for x in members})) +
                    '. Confirm availability with the course team.'
                )
                c['warnings'].append(m['code'] + ': ' + m['groupNote'])
            if not members:
                errors.append(f"{c['id']}: {m['code']} has no choices for this stage/semester")
                continue
            if not m['additional'] and m['credits'] is not None and any(x['credits'] != m['credits'] for x in members):
                errors.append(f"{c['id']}: {m['code']} choice credits differ from the course slot")
                continue
            m['choices'] = members
            m['selectionRule'] = 'Choose one from'
        c['warnings'] = list(dict.fromkeys(w for w in c['warnings'] if not w.startswith('Elective groups are shown')))
        if unresolved:
            c['warnings'].append('Group PDFs not yet supplied for: ' + ', '.join(sorted(set(unresolved))) + '. These remain unexpanded slots.')

    ids = [c['id'] for c in courses]
    if len(ids) != len(set(ids)):
        errors.append('More than one PDF has the same course code. Replace the old PDF instead of retaining two versions.')

    report = {'courses': [{'id': c['id'], 'title': c['title'], 'warnings': c['warnings']} for c in courses], 'errors': errors}
    ROOT.joinpath('validation-report.json').write_text(json.dumps(report, indent=2))
    if errors:
        raise ValueError('\n'.join(errors))

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / 'web', out)
    for c in courses:
        c.pop('_path')
        # PDFs stay in the source repository for rebuilding, but the generated site
        # does not publish or link to PDF copies.
        c.pop('sourceFile', None)
        for m in c['modules']:
            m.pop('groupSource', None)
    data = {'builtAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'courses': courses}
    (out / 'gallery-data.js').write_text('window.COURSE_GALLERY=' + json.dumps(data, ensure_ascii=True).replace('</', '<\\/') + ';\n')
    (out / '.nojekyll').write_text('')
    print(f'Built {len(courses)} courses; {sum(len(c["modules"]) for c in courses)} scheduled entries.')
    for c in courses:
        print(f'{c["id"]}: {c["title"]}; ' + ('credit total checked' if c['creditTotalChecked'] else 'source limitations flagged'))
    return data


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=ROOT / 'course-pdfs')
    ap.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = ap.parse_args()
    try:
        build(args.source, args.output)
    except Exception as e:
        print('BUILD BLOCKED: ' + str(e), file=sys.stderr)
        sys.exit(1)
