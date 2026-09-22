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


def _month_year_steps(sequence):
    steps = []
    year = 1
    last = 0
    for x in re.finditer(r'Semester\s+(\d+)\s*\(([^)]+)\)', sequence, re.I):
        detail = x.group(2)
        month = re.search(r'(?:taken\s+in\s+)?(September|January|May)', detail, re.I)
        if not month:
            continue
        month_name = month.group(1).title()
        monthnum = {'January': 1, 'May': 5, 'September': 9}[month_name]
        if monthnum < last:
            year += 1
        last = monthnum
        steps.append({
            'semester': int(x.group(1)), 'month': month_name, 'year': year,
            'project': 'project' in detail.lower(),
            'spansTwoSemesters': bool(re.search(r'spanning\s+2\s+semesters', detail, re.I))
        })
    return steps


def intake_routes(text):
    """Read explicit PG intake sequencing without folding neighbouring delivery blocks together."""
    clean = re.sub(r'^Course .*?·.*$|^Page \d+ of \d+\s*$', ' ', text, flags=re.M)
    flat = ' '.join(clean.split())
    heading_re = re.compile(
        r'(?P<mode>Full[- ]Time|Part[- ]Time)'
        r'(?:\s+On-Campus\s*/\s*Part-Time\s+Online\s+Learning)?\s+Students'
        r'(?:\s*\((?P<site>RGU|MDIS)\))?',
        re.I,
    )
    matches = list(heading_re.finditer(flat))
    result = {}
    for index, match in enumerate(matches):
        site = (match.group('site') or '').upper()
        if site == 'MDIS':
            continue
        mode = 'Full-Time' if match.group('mode').lower().startswith('full') else 'Part-Time'
        end = matches[index + 1].start() if index + 1 < len(matches) else len(flat)
        block = flat[match.end():end]
        by_intake = result.setdefault(mode, {})
        entry_matches = list(re.finditer(r'For\s+(September|January)\s+entry,\s+the\s+sequence\s+of\s+modules\s+will\s+be:\s*', block, re.I))
        for j, entry in enumerate(entry_matches):
            intake = entry.group(1).title()
            stop = entry_matches[j + 1].start() if j + 1 < len(entry_matches) else len(block)
            steps = _month_year_steps(block[entry.end():stop])
            if steps:
                by_intake[intake] = steps
    result = {mode: entries for mode, entries in result.items() if entries}

    # A small number of CADs give the same standard structure and both intake
    # durations, but omit the explicit sequence paragraph. Derive only where the
    # document itself states all of those ingredients.
    if not result and all(phrase in flat for phrase in (
        'Full-time 12 months with a September intake',
        'Full-time 16 months with a January intake',
        'Part-time 28 months with a September intake',
        'Part-time 32 months with a January intake',
    )) and re.search(r'four\s+15\s+credit\s+modules\s+in\s+Semester\s+1.*four\s+15\s+credit\s+modules\s+in\s+semester\s+2', flat, re.I):
        result = {
            'Full-Time': {
                'September': _month_year_steps('Semester 1 (taken in September), Semester 2 (taken in January), Semester 3 (project, taken in May)'),
                'January': _month_year_steps('Semester 2 (taken in January), Semester 1 (taken in September), Semester 3 (project, taken in January)'),
            },
            'Part-Time': {
                'September': _month_year_steps('Semester 1 (taken in September), Semester 2 (taken in January), Semester 3 (taken in September), Semester 4 (taken in January), Semester 5 (project, taken in May and spanning 2 semesters)'),
                'January': _month_year_steps('Semester 2 (taken in January), Semester 1 (taken in September), Semester 4 (taken in January), Semester 3 (taken in September), Semester 5 (project, taken in January and spanning 2 semesters)'),
            },
        }
    return result


def extract_route_names(text):
    """Read lettered route names using either Akari's dash or colon separator."""
    result = {}
    for line in text.splitlines():
        if 'Route ' not in line:
            continue
        for m in re.finditer(r'Route\s+([A-Z])\s*[-:]\s*(.*?)(?=\s+Route\s+[A-Z]\s*[-:]|$)', line, re.I):
            name = m.group(2).strip().rstrip(' .;')
            if name and len(name) < 140:
                result.setdefault(m.group(1).upper(), name)
    return result


def pg_delivery_id(mode, delivery):
    return ('FULL' if mode == 'Full-Time' else 'PART') + ('_ONLINE' if delivery == 'Online' else '_CAMPUS')


def pg_delivery_combinations(text):
    """Read the supported RGU PG mode/attendance combinations from Delivery Range."""
    stage = re.search(r'^\s*Stage\s+1\s*/\s*Semester\s+1\s*$', text, re.M)
    if not stage:
        return {}
    before = text[:stage.start()]
    marker = before.rfind('Delivery Range')
    if marker < 0:
        return {}
    block = ' '.join(before[marker:].split())
    combos = {}
    pattern = re.compile(r'\b(Full|Part)\s+Time\s+(On\s+Campus|Online)(?:\s*\((RGU|MDIS)\))?', re.I)
    for m in pattern.finditer(block):
        if (m.group(3) or '').upper() == 'MDIS':
            continue
        mode = 'Full-Time' if m.group(1).lower() == 'full' else 'Part-Time'
        delivery = 'Online' if m.group(2).lower().startswith('online') else 'On-Campus'
        ident = pg_delivery_id(mode, delivery)
        combos.setdefault(ident, {'mode': mode, 'delivery': delivery})
    return combos


def pg_row_context(lines, row_index, code_column):
    """Recover the wrapped PG Delivery Range cell for one module row."""
    # Mode labels normally start before the code row. Search backwards only as
    # far as the previous module row so a neighbouring delivery cannot leak in.
    mode = None
    for j in range(row_index, max(-1, row_index - 12), -1):
        if j != row_index and CODE_RE.search(lines[j].replace('\f', '')):
            break
        prefix = lines[j].replace('\f', '')[:code_column]
        matches = list(re.finditer(r'\b(Full|Part)\b', prefix, re.I))
        if matches:
            mode = 'Full-Time' if matches[-1].group(1).lower() == 'full' else 'Part-Time'
            break

    # Attendance is usually completed on one or two lines after the code row.
    pieces = []
    for j in range(row_index, min(len(lines), row_index + 16)):
        if j != row_index and CODE_RE.search(lines[j].replace('\f', '')):
            break
        prefix = lines[j].replace('\f', '')[:code_column].strip()
        if re.match(r'^(?:Course\s+\d+|Page\s+\d+)', prefix):
            continue
        if prefix:
            pieces.append(prefix)
    local = ' '.join(pieces)
    delivery = None
    if re.search(r'\bOnline\b', local, re.I):
        delivery = 'Online'
    elif re.search(r'\bOn\s+Campus\b', local, re.I):
        delivery = 'On-Campus'
    site = 'MDIS' if re.search(r'\(MDIS\)', local, re.I) else 'RGU' if re.search(r'\(RGU\)', local, re.I) else None
    return mode, delivery, site


def placement_kind(name):
    value = re.sub(r'[-–—]', ' ', name).lower()
    value = re.sub(r'\s+', ' ', value)
    if 'short placement' in value:
        return 'short'
    if 'long placement' in value or 'year long' in value:
        return 'long'
    if 'non placement' in value or 'no placement' in value:
        return 'none'
    return None


def pg_pathway_label(route_name):
    """Strip placement suffixes so route triplets collapse to one PG pathway."""
    kind = placement_kind(route_name)
    if kind is None:
        return route_name.strip().rstrip(' .:;,')
    label = re.sub(r'(?i)[,:]?\s*(?:non[- ]?placement|no\s+placement|short\s+placement|long\s+placement)\s*$', '', route_name).strip(' ,:;-')
    return label


def pathway_id(label):
    slug = re.sub(r'[^A-Z0-9]+', '_', label.upper()).strip('_')
    return slug or 'GENERAL'

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
    if code == '0573':
        title = re.sub(r'\s*\(RGU and MDIS\)\s*$', '', title).strip()
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
        name = re.sub(r'\s*\[Approved\]\s*$', '', name, flags=re.I).strip()

        route_segments = [x for x in segments if re.match(r'^Routes?\s+[A-Z](?:\s*,\s*[A-Z])*[.]?$', x)]
        notes = ' '.join(route_segments)
        if columns:
            note_start = columns.get('notes')
            if note_start is not None:
                note_end = min((columns[k] for k in ('owner', 'allow', 'version', 'credits', 'module') if k in columns and columns[k] > note_start), default=None)
                table_notes = cell_fragments(lines, i, note_start, note_end, radius=1)
                if table_notes and table_notes not in notes:
                    notes = (notes + ' ' + table_notes).strip()

        pg_contexts = []
        if pg and columns:
            pg_mode, pg_delivery, pg_site = pg_row_context(lines, i, match.start())
            # Business Analytics contains a parallel MDIS schedule. The public
            # atlas intentionally keeps only the RGU delivery requested here.
            if pg_site == 'MDIS':
                continue
            if pg_mode and pg_delivery:
                pg_contexts = [pg_delivery_id(pg_mode, pg_delivery)]

        credits = CREDIT_RE.search(line)
        value = int(credits[1]) if credits else None
        group = 'electives' in c.lower()
        row_routes = parse_route_ids(after + ' ' + notes)
        local = ' '.join(x.strip() for x in lines[max(0, i - 2):min(len(lines), i + 3)])
        row_intakes = sorted(set(
            (['September'] if re.search(r'September\s+Intake', line + ' ' + notes, re.I) else []) +
            (['January'] if re.search(r'January\s+Intake', line + ' ' + notes, re.I) else [])
        ))
        pg_variants = [
            {'deliveryId': ident, 'routeIds': list(row_routes), 'intakeIds': list(row_intakes)}
            for ident in pg_contexts
        ]
        item = {
            'stage': current[0], 'semester': current[1], 'code': c, 'title': name,
            'credits': value, 'type': 'elective' if group else kind, 'page': page,
            'additional': False, 'routeIds': row_routes,
            'deliveryIds': [],
            '_deliveryHints': delivery_ids_near(lines, i, match.start()) if columns else [],
            '_noteDeliveryIds': note_delivery_ids(notes),
            '_pgContexts': pg_contexts,
            '_pgVariants': pg_variants,
            'intakeIds': row_intakes,
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
            old['_pgContexts'] = sorted(set(old.get('_pgContexts', [])) | set(item.get('_pgContexts', [])))
            for variant in item.get('_pgVariants', []):
                if variant not in old.setdefault('_pgVariants', []):
                    old['_pgVariants'].append(variant)
            old['intakeIds'] = sorted(set(old.get('intakeIds', [])) | set(item.get('intakeIds', [])))
            old['spansSemesters'] = max(old.get('spansSemesters', 1), item.get('spansSemesters', 1))
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
        is_pg_placement = bool(
            pg and (m['code'] in {'CEM104', 'CEM105'} or re.search(r'Postgraduate\s+Placement', m['title'], re.I))
        )
        if is_pg_placement:
            m['placementOption'] = True
            if placement_is_additional:
                m['additional'] = True
        elif placement_is_additional and m['semester'] == 3 and m['type'] == 'elective' and (m['credits'] or 0) >= 90:
            m['additional'] = True
        if re.search(r'\b' + re.escape(m['code']) + r'\s+[^.]*?is for additional credit only\.', flat, re.I):
            m['additional'] = True

    route_names = extract_route_names(text)
    used_routes = sorted({r for m in modules for r in m['routeIds']})
    raw_pathways = {r: route_names[r].strip() for r in used_routes if r in route_names}
    missing_route_names = [r for r in used_routes if r not in raw_pathways]
    if missing_route_names:
        raise ValueError('Route names not found for: ' + ', '.join(missing_route_names))

    pathways = dict(raw_pathways)
    if pg:
        # PG CADs frequently multiply a real subject pathway by three placement
        # variants. Collapse those route letters to the meaningful pathway while
        # keeping placement as an optional, additional-credit module.
        route_to_label = {r: pg_pathway_label(name) for r, name in route_names.items()}
        meaningful_labels = sorted({route_to_label[r] for r in used_routes if route_to_label.get(r)})
        if len(meaningful_labels) > 1:
            pathways = {pathway_id(label): label for label in meaningful_labels}
            route_to_path = {
                r: pathway_id(label) for r, label in route_to_label.items()
                if label and pathway_id(label) in pathways
            }
            all_paths = set(pathways)
            # Route notes on some PT rows use inconsistent letter pairs even though
            # the same module is unambiguous in the FT table. Canonicalise subject
            # pathway membership by module code, preferring the FT occurrence when
            # the CAD provides one, then reuse it for the PT occurrence.
            full_routes_by_code = {}
            any_routes_by_code = {}
            for item in modules:
                for variant in item.get('_pgVariants', []):
                    any_routes_by_code.setdefault(item['code'], set()).update(variant.get('routeIds', []))
                    if str(variant.get('deliveryId', '')).startswith('FULL_'):
                        full_routes_by_code.setdefault(item['code'], set()).update(variant.get('routeIds', []))
            for m in modules:
                # Projects and placements are programme-wide. A few CAD route
                # notes omit one pathway on one occurrence, while another
                # occurrence confirms the shared module; treating these as common
                # also matches the declared 180-credit award structure.
                is_project = bool((m.get('credits') or 0) >= 60 and re.search(r'Project', m['title'], re.I))
                if m.get('placementOption') or is_project:
                    m['pathwayIds'] = []
                    continue
                candidate_routes = sorted(full_routes_by_code.get(m['code']) or any_routes_by_code.get(m['code'], set()))
                pids = sorted({route_to_path[r] for r in candidate_routes if r in route_to_path})
                m['pathwayIds'] = [] if not pids or set(pids) == all_paths else pids
        else:
            # Generic Non-/Short-/Long-Placement triplets are not pathways.
            pathways = {}
            for m in modules:
                m['pathwayIds'] = []

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
    routes = intake_routes(text) if pg else {}
    pg_deliveries = pg_delivery_combinations(text) if pg else {}
    flexible_intake = bool(pg and re.search(r'intakes?\s+available\s+throughout\s+the\s+year', flat, re.I))

    if not known:
        warnings.append('Individual module/group credits are not included in this export. They have not been inferred.')
    if any(m['type'] == 'elective' for m in modules):
        warnings.append('Elective groups are shown as slots. Their individual choices are not included in this course PDF.')
    if 'CM1112' in text and any(m['code'] == 'CE1337' for m in modules):
        warnings.append('The delivery table lists CE1337 Programming Bootcamp; a narrative note still refers to CM1112 Introduction to Programming. The diagram follows the table.')
    if pg and code == '0573':
        warnings.append('The MDIS delivery in the CAD is omitted; this atlas shows RGU delivery only.')
    if pg and flexible_intake:
        warnings.append('The CAD states that intakes are available throughout the year; the published flexible module structure is shown rather than a September/January sequence.')
    elif pg and not routes:
        warnings.append('No September/January intake sequence is published; the CAD semester structure is shown as supplied.')
    if pg and re.search(r'The course structure \(Delivery Range\) is for new students', text, re.I):
        warnings.append('The diagram uses the current Delivery Range for new students; transitional arrangements for earlier cohorts are not shown.')

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

    if pg and known:
        if not pg_deliveries:
            raise ValueError('No postgraduate study mode/delivery combinations were recognised from Delivery Range.')

        # Validate every displayable PG combination independently. Placements are
        # deliberately excluded only when the CAD explicitly states that their
        # credits are additional to the 180-credit award.
        for delivery_id, delivery_meta in pg_deliveries.items():
            mode = delivery_meta['mode']
            intake_checks = list(routes.get(mode, {})) or [None]
            pathway_checks = list(pathways) or [None]
            for intake in intake_checks:
                for pathway in pathway_checks:
                    included = []
                    for m in modules:
                        if m['additional'] or m.get('excludedFromAward'):
                            continue
                        variants = [v for v in m.get('_pgVariants', []) if v.get('deliveryId') == delivery_id]
                        if not variants:
                            continue
                        if intake and not any(not v.get('intakeIds') or intake in v.get('intakeIds', []) for v in variants):
                            continue
                        if pathway and m.get('pathwayIds') and pathway not in m['pathwayIds']:
                            continue
                        included.append(m)
                    total = sum(m['credits'] for m in included)
                    if total != int(credit[1]):
                        labels = [mode, delivery_meta['delivery']]
                        if intake:
                            labels.append(intake + ' intake')
                        if pathway:
                            labels.append(pathways[pathway])
                        raise ValueError(
                            f'Listed postgraduate award credits ({total}) do not match declared award credits ({credit[1]}) '
                            f"for {' / '.join(labels)}. Review PG delivery, intake or pathway allocation before publishing."
                        )

    for m in modules:
        m.pop('_deliveryHints', None)
        m.pop('_noteDeliveryIds', None)
        if pg:
            m['pgVariants'] = m.pop('_pgVariants', [])
            m.pop('_pgContexts', None)

    return {
        'id': code, 'title': title, 'level': 'PG' if pg else 'UG',
        'awardCredits': int(credit[1]), 'sourceDate': date.strip(), 'sourceFile': filename,
        'modules': modules, 'routes': routes, 'pathways': pathways,
        'deliveryPathways': delivery_pathways,
        'pgDeliveryCombinations': pg_deliveries,
        'flexibleIntake': flexible_intake,
        'warnings': warnings,
        'duplicatesCollapsed': duplicates,
        'allocationVerified': (not pg) or (known and bool(pg_deliveries)),
        'creditTotalChecked': known and ((not pg) or bool(pg_deliveries))
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
            if c['level'] == 'PG' and (not c.get('creditTotalChecked') or not c.get('allocationVerified')):
                raise ValueError('Postgraduate course is not publishable until delivery allocation and award-credit validation both pass.')
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
    data_script = 'window.COURSE_GALLERY=' + json.dumps(data, ensure_ascii=True).replace('</', '<\\/') + ';\n'
    (out / 'gallery-data.js').write_text(data_script)

    # Keep the published application and its generated data in one atomic HTML
    # response. GitHub Pages/browser caches can otherwise mix versions of
    # index.html, app.js and gallery-data.js after a deployment.
    index_path = out / 'index.html'
    index = index_path.read_text()
    script_tags = '  <script src=\"gallery-data.js\" defer></script>\n  <script src=\"app.js\" defer></script>'
    if script_tags not in index:
        raise ValueError('Website script tags not found; cannot create atomic published page.')
    app_script = (out / 'app.js').read_text().replace('</script', '<\\/script')
    inline = '  <script>\n' + data_script + '  </script>\n  <script>\n' + app_script + '\n  </script>'
    index_path.write_text(index.replace(script_tags, inline))

    # Stable external copies remain in dist only so a previously cached index
    # can still load a matching current pair during the cache transition.
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
