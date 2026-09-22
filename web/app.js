'use strict';

const $ = id => document.getElementById(id);
const data = window.COURSE_GALLERY;
let course;
let activeRoute = null;
let activeDelivery = null;
let mode = 'Full-Time';
let intake = 'Compare';

const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[character]));

for (const item of data.courses) {
  const option = document.createElement('option');
  option.value = item.id;
  option.textContent = item.level + ' · ' + item.title;
  $('course-select').append(option);
}
$('course-count').textContent = data.courses.length + ' courses';

function validationText() {
  if (!course.creditTotalChecked) {
    return 'Award credits come from the course header. Module-level credit totals and route allocations cannot be checked from this export.';
  }
  const hasRoutes = Object.keys(course.pathways || {}).length > 0;
  const hasDelivery = Object.keys(course.deliveryPathways || {}).length > 0;
  let scope = 'the scheduled award credits match';
  if (hasRoutes && hasDelivery) scope = 'every delivery route and specialism combination matches';
  else if (hasDelivery) scope = 'every delivery route matches';
  else if (hasRoutes) scope = 'each study route matches';
  const hasConflict = course.modules.some(item => item.sourceConflict);
  return 'Credit check passed: ' + scope + ' the ' + course.awardCredits + '-credit award. Additional options' +
    (hasConflict ? ' and explicitly flagged source-data conflicts' : '') + ' are excluded from award totals.';
}

function selectCourse(id) {
  course = data.courses.find(item => item.id === id) || data.courses[0];
  $('course-select').value = course.id;
  const url = new URL(location.href);
  url.searchParams.set('course', course.id);
  history.replaceState(null, '', url);
  $('course-title').textContent = course.title;
  $('course-meta').textContent = course.level + ' · Course ' + course.id;
  $('source-date').textContent = 'Source export · ' + course.sourceDate;
  $('award-credits').textContent = course.awardCredits;
  $('pg-controls').hidden = course.level !== 'PG' || !Object.keys(course.routes || {}).length;

  renderPathways();
  mode = Object.keys(course.routes || {})[0] || 'Full-Time';
  intake = 'Compare';
  renderRoutes();
  renderMap();

  $('note-list').innerHTML = course.warnings.map(warning => '<li>' + esc(warning) + '</li>').join('');
  $('note-count').textContent = '(' + course.warnings.length + ')';
  $('validation').textContent = validationText();
  $('source-notes').open = false;
  document.title = course.title + ' · Course Atlas';
}

function button(label, selected, action) {
  const element = document.createElement('button');
  element.type = 'button';
  element.textContent = label;
  element.setAttribute('aria-pressed', String(selected));
  element.addEventListener('click', action);
  return element;
}

function renderRoutes() {
  $('modes').replaceChildren();
  $('intakes').replaceChildren();
  $('timelines').replaceChildren();
  if (!Object.keys(course.routes || {}).length) return;

  for (const studyMode of Object.keys(course.routes)) {
    $('modes').append(button(studyMode.replace('-', ' '), mode === studyMode, () => {
      mode = studyMode;
      renderRoutes();
    }));
  }

  const available = Object.keys(course.routes[mode]);
  const choices = available.length > 1 ? [...available, 'Compare'] : available;
  if (!choices.includes(intake)) intake = choices.at(-1);
  for (const entry of choices) {
    $('intakes').append(button(entry === 'Compare' ? 'Compare both' : entry + ' start', intake === entry, () => {
      intake = entry;
      renderRoutes();
    }));
  }

  const show = intake === 'Compare' ? available : [intake];
  $('timelines').classList.toggle('single', show.length === 1);
  for (const entry of show) {
    const box = document.createElement('article');
    box.className = 'timeline';
    box.innerHTML = '<h3>' + esc(entry) + ' start</h3>';
    const steps = course.routes[mode][entry];
    const base = {January: 1, May: 5, September: 9}[steps[0].month];
    for (const step of steps) {
      const offset = (step.year - 1) * 12 + {January: 1, May: 5, September: 9}[step.month] - base;
      const element = document.createElement('div');
      element.className = 'timeline-step';
      element.innerHTML = `<div class="when">${esc(step.month)}<small>${offset ? '+' + offset + ' months' : 'Intake begins'}</small></div><div class="step-block ${step.project ? 'project-block' : ''}"><strong>${step.project ? 'MSc project' : 'Taught block'}</strong><span>CAD Semester ${step.semester}</span>${step.spansTwoSemesters ? '<span>Spans two semesters</span>' : ''}</div>`;
      box.append(element);
    }
    $('timelines').append(box);
  }
}

function card(item) {
  const element = document.createElement('button');
  element.type = 'button';
  const project = /capstone project|msc project/i.test(item.title);
  const kind = item.sourceConflict ? 'conflict' : item.additional ? 'additional' : item.type;
  element.className = 'card ' + kind + (project ? ' project' : '');
  const creditText = item.credits === null
    ? 'Credits not listed'
    : item.credits + (item.additional ? ' group credits' : ' credits');
  const statusText = item.sourceConflict ? ' · Source conflict' : item.additional ? ' · Outside award' : '';
  element.innerHTML = `<span class="code">${esc(item.code)}</span><span class="name">${esc(item.title)}</span>${project && item.credits !== null ? '<span class="big-credit">' + item.credits + ' credits</span>' : ''}<span class="card-bottom"><span>${creditText}${statusText}</span><span aria-hidden="true">›</span></span>`;

  if (item.choices) {
    element.title = 'Choose one from: ' + item.choices.map(choice => choice.code + ' — ' + choice.title).join('; ');
    const hint = document.createElement('span');
    hint.className = 'choice-hint';
    hint.textContent = 'Choose one from ' + item.choices.length + ' modules · View choices';
    element.append(hint);
  }
  if (item.spansSemesters === 2) {
    const note = document.createElement('span');
    note.className = 'choice-hint';
    note.textContent = 'Runs across Semesters 1 and 2 · Credits counted once';
    element.append(note);
  }
  element.addEventListener('click', () => showModule(item));
  return element;
}

function awardRows(rows) {
  return rows.filter(item => !item.additional && !item.excludedFromAward);
}

function semesterBlock(rows, semester) {
  const block = document.createElement('section');
  block.className = 'semester';
  const counted = awardRows(rows);
  const total = counted.length && counted.every(item => item.credits !== null)
    ? counted.reduce((sum, item) => sum + item.credits, 0)
    : counted.length ? null : 0;
  block.innerHTML = `<div class="semester-heading"><h4>Semester ${semester}</h4><span>${total !== null ? total + ' award credits' : ''}</span></div><div class="cards"></div>`;
  rows.forEach(item => block.querySelector('.cards').append(card(item)));
  return block;
}

function selectorField(id, labelText, values, onChange) {
  const wrapper = document.createElement('div');
  wrapper.className = 'pathway-field';
  const label = document.createElement('label');
  label.htmlFor = id;
  label.textContent = labelText;
  const select = document.createElement('select');
  select.id = id;
  for (const [value, name] of Object.entries(values)) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = name;
    select.append(option);
  }
  select.addEventListener('change', () => onChange(select.value));
  wrapper.append(label, select);
  return wrapper;
}

function renderPathways() {
  let panel = $('pathway-controls');
  if (!panel) {
    panel = document.createElement('section');
    panel.id = 'pathway-controls';
    panel.className = 'control-row pathway-controls';
    $('map').before(panel);
  }
  panel.replaceChildren();

  const routes = course.pathways || {};
  const deliveries = course.deliveryPathways || {};
  activeRoute = Object.keys(routes)[0] || null;
  activeDelivery = Object.keys(deliveries)[0] || null;
  panel.hidden = !activeRoute && !activeDelivery;

  if (activeDelivery) {
    panel.append(selectorField('delivery-select', 'Course route', deliveries, value => {
      activeDelivery = value;
      renderMap();
    }));
  }
  if (activeRoute) {
    panel.append(selectorField('pathway-select', activeDelivery ? 'Specialism' : 'Study route', routes, value => {
      activeRoute = value;
      renderMap();
    }));
  }
}

function visibleModules() {
  return course.modules.filter(item =>
    (!activeRoute || !item.routeIds?.length || item.routeIds.includes(activeRoute)) &&
    (!activeDelivery || !item.deliveryIds?.length || item.deliveryIds.includes(activeDelivery))
  );
}

function renderMap() {
  const mapModules = visibleModules();
  const pg = course.level === 'PG';
  $('map').className = 'map' + (pg ? ' pg' : '');
  $('map').replaceChildren();
  $('map-kicker').textContent = pg ? 'COMBINED SOURCE SCHEDULE' : 'COURSE STRUCTURE';

  if (pg) {
    for (const semester of [...new Set(mapModules.map(item => item.semester))].sort((a, b) => a - b)) {
      const box = document.createElement('article');
      box.className = 'stage';
      box.append(semesterBlock(mapModules.filter(item => item.semester === semester), semester));
      $('map').append(box);
    }
    return;
  }

  // Build columns only from semesters that contain at least one visible row.
  // This removes an empty Semester 3 column without sacrificing alignment when
  // a real summer/placement option is present on the selected route.
  const semesters = [...new Set(mapModules.map(item => item.semester))].sort((a, b) => a - b);
  $('map').style.setProperty('--semester-count', semesters.length);

  for (const stage of [...new Set(mapModules.map(item => item.stage))].sort((a, b) => a - b)) {
    const rows = mapModules.filter(item => item.stage === stage);
    const counted = awardRows(rows);
    const sum = counted.every(item => item.credits !== null) ? counted.reduce((total, item) => total + item.credits, 0) : null;
    const box = document.createElement('article');
    box.className = 'stage';
    box.innerHTML = `<div class="stage-head"><span class="number" aria-hidden="true">${stage}</span><div><h3>Stage ${stage}</h3><p>${sum === null ? 'Credits not fully stated' : sum + ' award credits'}</p></div></div>`;
    for (const semester of semesters) {
      const items = rows.filter(item => item.semester === semester);
      const cell = semesterBlock(items, semester);
      if (!items.length) {
        cell.classList.add('empty-semester');
        cell.querySelector('.semester-heading span').textContent = '';
        cell.querySelector('.cards').innerHTML = '<p class="empty-note">No modules listed</p>';
      }
      box.append(cell);
    }
    $('map').append(box);
  }
}

function showModule(item) {
  $('detail-kind').textContent = item.sourceConflict ? 'Source conflict' : item.additional ? 'Additional option' : item.type === 'elective' ? 'Elective group' : 'Module';
  $('detail-code').textContent = item.code;
  $('detail-title').textContent = item.title;

  let explanation = item.type === 'elective'
    ? 'This course document identifies an elective group.'
    : 'Module-level outcomes, assessments and prerequisites are not included in this course export.';
  if (item.sourceConflict) {
    explanation = 'This row has contradictory delivery-route metadata in the source document. It is retained for review but excluded from the validated route totals rather than being silently assigned to a route.';
  }

  $('detail-body').innerHTML = `<dl><div><dt>Listed location</dt><dd>Stage ${item.stage} · Semester ${item.semester}</dd></div><div><dt>SCQF credits</dt><dd>${item.credits === null ? 'Not in this export' : item.credits}</dd></div></dl><p>${esc(explanation)}</p>${item.additional ? '<p>Additional placement / study-abroad options do not contribute to the award credit total.</p>' : ''}${course.level === 'PG' ? '<p class="notice">This is a row from the combined schedule. Its full-time / part-time allocation is not identified in the PDF.</p>' : ''}`;

  if (item.choices) {
    $('detail-body').innerHTML = '<h3>Choose one from</h3><ul class="choice-list">' + item.choices.map(choice => '<li><strong>' + esc(choice.code) + ' · ' + esc(choice.title) + '</strong><span>' + choice.credits + ' credits</span></li>').join('') + '</ul><p>' +
      (item.additional ? 'These are alternative additional options. Their credits are outside the award total.' : 'Select one module to fill this elective slot.') + '</p>' +
      (item.groupNote ? '<p class="notice">' + esc(item.groupNote) + '</p>' : '');
  }
  $('detail').showModal();
}

$('course-select').onchange = event => selectCourse(event.target.value);
$('close').onclick = () => $('detail').close();
$('detail').addEventListener('click', event => {
  const rect = $('detail').getBoundingClientRect();
  if (event.target === $('detail') && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) {
    $('detail').close();
  }
});
selectCourse(new URL(location.href).searchParams.get('course'));
