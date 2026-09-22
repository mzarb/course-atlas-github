'use strict';

const $ = id => document.getElementById(id);
const data = window.COURSE_GALLERY;
let course;
let activeRoute = null;
let activeDelivery = null;
let pgMode = null;
let pgIntake = null;
let pgDelivery = null;

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
    return 'Award credits come from the course header. Module-level credit totals cannot be checked from this export.';
  }
  if (course.level === 'PG') {
    const hasPathways = Object.keys(course.pathways || {}).length > 0;
    const scope = hasPathways
      ? 'every published study mode, delivery, intake and pathway view matches'
      : 'every published study mode, delivery and intake view matches';
    return 'Credit check passed: ' + scope + ' the ' + course.awardCredits + '-credit award. Optional placement credits are excluded only where the CAD states that they are additional to the award.';
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

function button(label, selected, action) {
  const element = document.createElement('button');
  element.type = 'button';
  element.textContent = label;
  element.setAttribute('aria-pressed', String(selected));
  element.addEventListener('click', action);
  return element;
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

function initialisePgState() {
  const combinations = course.pgDeliveryCombinations || {};
  const modes = [...new Set(Object.values(combinations).map(item => item.mode))];
  pgMode = modes.includes('Full-Time') ? 'Full-Time' : modes[0] || null;
  const deliveryIds = Object.keys(combinations).filter(id => combinations[id].mode === pgMode);
  pgDelivery = deliveryIds[0] || null;
  const intakes = Object.keys((course.routes || {})[pgMode] || {});
  pgIntake = intakes.includes('September') ? 'September' : intakes[0] || null;
  activeRoute = Object.keys(course.pathways || {})[0] || null;
}

function renderPgControls() {
  const combinations = course.pgDeliveryCombinations || {};
  const modes = [...new Set(Object.values(combinations).map(item => item.mode))];
  $('modes').replaceChildren();
  for (const studyMode of modes) {
    $('modes').append(button(studyMode.replace('-', ' '), pgMode === studyMode, () => {
      pgMode = studyMode;
      const validDeliveries = Object.keys(combinations).filter(id => combinations[id].mode === pgMode);
      if (!validDeliveries.includes(pgDelivery)) pgDelivery = validDeliveries[0] || null;
      const validIntakes = Object.keys((course.routes || {})[pgMode] || {});
      if (!validIntakes.includes(pgIntake)) pgIntake = validIntakes.includes('September') ? 'September' : validIntakes[0] || null;
      renderPgControls();
      renderMap();
    }));
  }

  const deliveryIds = Object.keys(combinations).filter(id => combinations[id].mode === pgMode);
  $('pg-deliveries').replaceChildren();
  for (const id of deliveryIds) {
    const label = combinations[id].delivery === 'On-Campus' ? 'On campus' : combinations[id].delivery;
    $('pg-deliveries').append(button(label, pgDelivery === id, () => {
      pgDelivery = id;
      renderPgControls();
      renderMap();
    }));
  }
  $('delivery-wrap').hidden = deliveryIds.length < 2;

  const intakes = Object.keys((course.routes || {})[pgMode] || {});
  $('intakes').replaceChildren();
  for (const entry of intakes) {
    $('intakes').append(button(entry + ' start', pgIntake === entry, () => {
      pgIntake = entry;
      renderPgControls();
      renderMap();
    }));
  }
  $('intake-wrap').hidden = intakes.length === 0;

  const pathways = course.pathways || {};
  const pathwayWrap = $('pg-pathway-wrap');
  pathwayWrap.replaceChildren();
  if (Object.keys(pathways).length) {
    if (!activeRoute || !pathways[activeRoute]) activeRoute = Object.keys(pathways)[0];
    const field = selectorField('pg-pathway-select', 'Pathway', pathways, value => {
      activeRoute = value;
      renderPgControls();
      renderMap();
    });
    field.querySelector('select').value = activeRoute;
    pathwayWrap.append(field);
    pathwayWrap.hidden = false;
  } else {
    activeRoute = null;
    pathwayWrap.hidden = true;
  }

  const selected = combinations[pgDelivery];
  const context = [];
  if (pgMode) context.push(pgMode.replace('-', ' '));
  if (selected) context.push(selected.delivery === 'On-Campus' ? 'On campus' : selected.delivery);
  if (pgIntake) context.push(pgIntake + ' intake');
  else if (course.flexibleIntake) context.push('Flexible intake');
  if (activeRoute && pathways[activeRoute]) context.push(pathways[activeRoute]);
  $('pg-context').textContent = context.join(' · ');
}

function renderUgPathways() {
  const panel = $('pathway-controls');
  panel.replaceChildren();
  if (course.level === 'PG') {
    panel.hidden = true;
    return;
  }

  const routes = course.pathways || {};
  const deliveries = course.deliveryPathways || {};
  activeRoute = Object.keys(routes)[0] || null;
  activeDelivery = Object.keys(deliveries)[0] || null;
  panel.hidden = !activeRoute && !activeDelivery;

  if (activeDelivery) {
    const field = selectorField('delivery-select', 'Course route', deliveries, value => {
      activeDelivery = value;
      renderMap();
    });
    field.querySelector('select').value = activeDelivery;
    panel.append(field);
  }
  if (activeRoute) {
    const field = selectorField('pathway-select', activeDelivery ? 'Specialism' : 'Study route', routes, value => {
      activeRoute = value;
      renderMap();
    });
    field.querySelector('select').value = activeRoute;
    panel.append(field);
  }
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

  activeRoute = null;
  activeDelivery = null;
  pgMode = null;
  pgIntake = null;
  pgDelivery = null;

  const pg = course.level === 'PG';
  $('pg-controls').hidden = !pg;
  if (pg) {
    initialisePgState();
    renderPgControls();
  }
  renderUgPathways();
  renderMap();

  $('note-list').innerHTML = course.warnings.map(warning => '<li>' + esc(warning) + '</li>').join('');
  $('note-count').textContent = '(' + course.warnings.length + ')';
  $('validation').textContent = validationText();
  $('source-notes').open = false;
  document.title = course.title + ' · Course Atlas';
}

function card(item) {
  const element = document.createElement('button');
  element.type = 'button';
  const kind = item.sourceConflict ? 'conflict' : item.additional ? 'additional' : item.type;
  element.className = 'card ' + kind;
  let creditText = item.credits === null ? 'Credits not listed' : item.credits + ' credits';
  if (item.placementOption) creditText += ' · Optional placement';
  else if (item.additional) creditText += ' · Additional option';
  const statusText = item.sourceConflict ? ' · Source conflict' : item.additional && !item.placementOption ? ' · Outside award' : '';
  element.innerHTML = `<span class="code">${esc(item.code)}</span><span class="name">${esc(item.title)}</span><span class="card-bottom"><span>${creditText}${statusText}</span><span aria-hidden="true">›</span></span>`;

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
    note.textContent = 'Spans two teaching periods · Credits counted once';
    element.append(note);
  }
  element.addEventListener('click', () => showModule(item));
  return element;
}

function awardRows(rows) {
  return rows.filter(item => !item.additional && !item.excludedFromAward);
}

function semesterBlock(rows, semester, options = {}) {
  const block = document.createElement('section');
  block.className = 'semester';
  const counted = awardRows(rows);
  const total = counted.length && counted.every(item => item.credits !== null)
    ? counted.reduce((sum, item) => sum + item.credits, 0)
    : counted.length ? null : 0;
  const title = options.title || 'Semester ' + semester;
  const detail = options.detail ? '<small>' + esc(options.detail) + '</small>' : '';
  block.innerHTML = `<div class="semester-heading"><div><h4>${esc(title)}</h4>${detail}</div><span>${total !== null ? total + ' award credits' : ''}</span></div><div class="cards"></div>`;
  rows.forEach(item => block.querySelector('.cards').append(card(item)));
  return block;
}

function visibleModules() {
  if (course.level === 'PG') {
    return course.modules.filter(item => {
      const variants = (item.pgVariants || []).filter(variant => variant.deliveryId === pgDelivery);
      if (!variants.length) return false;
      if (pgIntake && !variants.some(variant => !variant.intakeIds?.length || variant.intakeIds.includes(pgIntake))) return false;
      if (activeRoute && item.pathwayIds?.length && !item.pathwayIds.includes(activeRoute)) return false;
      return true;
    });
  }
  return course.modules.filter(item =>
    (!activeRoute || !item.routeIds?.length || item.routeIds.includes(activeRoute)) &&
    (!activeDelivery || !item.deliveryIds?.length || item.deliveryIds.includes(activeDelivery))
  );
}

function renderPgMap(mapModules) {
  const stage = document.createElement('article');
  stage.className = 'stage pg-stage' + (course.flexibleIntake && !pgIntake ? ' flexible' : '');
  let cells = [];

  if (course.flexibleIntake && !pgIntake) {
    cells = [{
      semester: 1,
      rows: mapModules,
      title: 'Flexible sequence',
      detail: 'Intakes throughout the year'
    }];
  } else {
    const steps = ((course.routes || {})[pgMode] || {})[pgIntake] || null;
    if (steps?.length) {
      cells = steps.map(step => ({
        semester: step.semester,
        rows: mapModules.filter(item => item.semester === step.semester),
        title: 'Semester ' + step.semester,
        detail: step.month + (step.project ? ' · MSc project' : '') + (step.spansTwoSemesters ? ' · spans two teaching periods' : '')
      }));
    } else {
      cells = [...new Set(mapModules.map(item => item.semester))].sort((a, b) => a - b).map(semester => ({
        semester,
        rows: mapModules.filter(item => item.semester === semester),
        title: 'Semester ' + semester,
        detail: ''
      }));
    }
  }

  $('map').style.setProperty('--pg-semester-count', Math.max(cells.length, 1));
  const counted = awardRows(mapModules);
  const sum = counted.every(item => item.credits !== null) ? counted.reduce((total, item) => total + item.credits, 0) : null;
  stage.innerHTML = `<div class="stage-head"><span class="number" aria-hidden="true">1</span><div><h3>Stage 1</h3><p>${sum === null ? 'Credits not fully stated' : sum + ' award credits'}</p></div></div>`;
  for (const cell of cells) {
    const block = semesterBlock(cell.rows, cell.semester, {title: cell.title, detail: cell.detail});
    if (!cell.rows.length) {
      block.classList.add('empty-semester');
      block.replaceChildren();
      block.setAttribute('aria-hidden', 'true');
    }
    stage.append(block);
  }
  $('map').append(stage);
}

function renderMap() {
  const mapModules = visibleModules();
  const pg = course.level === 'PG';
  $('map').className = 'map' + (pg ? ' pg' : '');
  $('map').replaceChildren();
  $('map-kicker').textContent = 'COURSE STRUCTURE';

  if (pg) {
    renderPgMap(mapModules);
    return;
  }

  // Build columns only from semesters that contain at least one visible row.
  // This removes an empty Semester 3 column without sacrificing alignment when
  // a real summer/placement option is present on the selected route.
  const semesters = [...new Set(mapModules.map(item => item.semester))].sort((a, b) => a - b);
  $('map').style.setProperty('--semester-count', semesters.length);

  for (const stageNumber of [...new Set(mapModules.map(item => item.stage))].sort((a, b) => a - b)) {
    const rows = mapModules.filter(item => item.stage === stageNumber);
    const counted = awardRows(rows);
    const sum = counted.every(item => item.credits !== null) ? counted.reduce((total, item) => total + item.credits, 0) : null;
    const box = document.createElement('article');
    box.className = 'stage';
    box.innerHTML = `<div class="stage-head"><span class="number" aria-hidden="true">${stageNumber}</span><div><h3>Stage ${stageNumber}</h3><p>${sum === null ? 'Credits not fully stated' : sum + ' award credits'}</p></div></div>`;
    for (const semester of semesters) {
      const items = rows.filter(item => item.semester === semester);
      const cell = semesterBlock(items, semester);
      if (!items.length) {
        cell.classList.add('empty-semester');
        cell.replaceChildren();
        cell.setAttribute('aria-hidden', 'true');
      }
      box.append(cell);
    }
    $('map').append(box);
  }
}

function showModule(item) {
  $('detail-kind').textContent = item.sourceConflict
    ? 'Source conflict'
    : item.placementOption
      ? 'Optional placement'
      : item.additional
        ? 'Additional option'
        : item.type === 'elective' ? 'Elective group' : 'Module';
  $('detail-code').textContent = item.code;
  $('detail-title').textContent = item.title;

  let explanation = item.type === 'elective' && !item.placementOption
    ? 'This course document identifies an elective group.'
    : '';
  if (item.sourceConflict) {
    explanation = 'This row has contradictory delivery-route metadata in the source document. It is retained for review but excluded from the validated route totals rather than being silently assigned to a route.';
  }

  const locationLabel = course.level === 'PG' ? 'CAD location' : 'Listed location';
  let body = `<dl><div><dt>${locationLabel}</dt><dd>Stage ${item.stage} · Semester ${item.semester}</dd></div><div><dt>SCQF credits</dt><dd>${item.credits === null ? 'Not in this export' : item.credits}</dd></div></dl>`;
  if (explanation) body += '<p>' + esc(explanation) + '</p>';
  if (item.placementOption) body += '<p>This is an optional placement module. The CAD states that placement credits are additional to the 180-credit MSc award.</p>';
  else if (item.additional) body += '<p>This additional option does not contribute to the award credit total.</p>';
  if (item.spansSemesters === 2) body += '<p>This module spans two teaching periods; its credits are counted once.</p>';
  $('detail-body').innerHTML = body;

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
