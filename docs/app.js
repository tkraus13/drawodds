// NM Big Game Draw Odds — Client-side application
// Ports filtering, aggregation, and odds logic from draw_odds.py

// ---- Global state ----

let RAW_RECORDS = [];
let SPECIES_LIST = [];
let YEARS_LIST = [];

const COL_MAP = {
  y:'year', hc:'hunt_code', sp:'species', ud:'unit_desc',
  u:'units', b:'bag', l:'licenses',
  t1:'total_1st', t2:'total_2nd', t3:'total_3rd',
  r1:'res_1st', r2:'res_2nd', r3:'res_3rd',
  n1:'nr_1st', n2:'nr_2nd', n3:'nr_3rd',
  o1:'out_1st', o2:'out_2nd', o3:'out_3rd',
  dr1:'drawn_res', dr2:'drawn_res_2nd', dr3:'drawn_res_3rd',
  dn1:'drawn_nr', dn2:'drawn_nr_2nd', dn3:'drawn_nr_3rd',
  do1:'drawn_out', do2:'drawn_out_2nd', do3:'drawn_out_3rd',
  rp:'r_pct', np:'nr_pct', op:'o_pct',
};

// ---- Data loading ----

async function loadData() {
  const resp = await fetch('data.json');
  const arr = await resp.json();
  const headers = arr[0];

  RAW_RECORDS = [];
  for (let i = 1; i < arr.length; i++) {
    const row = arr[i];
    const rec = {};
    for (let j = 0; j < headers.length; j++) {
      rec[COL_MAP[headers[j]] || headers[j]] = row[j];
    }
    RAW_RECORDS.push(rec);
  }

  SPECIES_LIST = [...new Set(RAW_RECORDS.map(r => r.species))].sort();
  YEARS_LIST = [...new Set(RAW_RECORDS.map(r => r.year))].sort((a, b) => a - b);
}

// ---- Hunt type mapping (mirrors HUNT_TYPES in draw_odds.py) ----

const HUNT_TYPES = {
  'bull elk':             { species: 'ELK', bags: ['MB'] },
  'mature bull elk':      { species: 'ELK', bags: ['MB'] },
  'any elk':              { species: 'ELK', bags: ['A'] },
  'either sex elk':       { species: 'ELK', bags: ['ES'] },
  'cow elk':              { species: 'ELK', bags: ['ES'] },
  'antlerless elk':       { species: 'ELK', bags: ['APRE/6', 'APRE/6/A'] },
  'fork antlered deer':           { species: 'DEER', bags: ['FAD'] },
  'fork antlered mule deer':      { species: 'DEER', bags: ['FAMD'] },
  'fork antlered whitetail deer': { species: 'DEER', bags: ['FAWTD'] },
  'either sex whitetail deer':    { species: 'DEER', bags: ['ESWTD'] },
  'any deer':                     { species: 'DEER', bags: ['A'] },
  'mule deer':                    { species: 'DEER', bags: ['FAD', 'FAMD'] },
  'whitetail deer':               { species: 'DEER', bags: ['FAWTD', 'ESWTD'] },
  'buck pronghorn':           { species: 'PRONGHORN', bags: ['MB'] },
  'mature buck pronghorn':    { species: 'PRONGHORN', bags: ['MB'] },
  'either sex pronghorn':     { species: 'PRONGHORN', bags: ['ES'] },
  'doe pronghorn':            { species: 'PRONGHORN', bags: ['F-IM'] },
  'barbary sheep':            { species: 'BARBARY SHEEP', bags: ['ES', 'F-IM'] },
  'barbary ram':              { species: 'BARBARY SHEEP', bags: ['ES'] },
  'barbary ewe':              { species: 'BARBARY SHEEP', bags: ['F-IM'] },
  'bighorn ram':              { species: 'BIGHORN SHEEP', bags: ['RAM'] },
  'bighorn ewe':              { species: 'BIGHORN SHEEP', bags: ['EWE'] },
  'bighorn sheep':            { species: 'BIGHORN SHEEP', bags: ['RAM', 'EWE'] },
  'ibex':                     { species: 'IBEX', bags: ['ES', 'F-IM'] },
  'javelina':                 { species: 'JAVELINA', bags: ['ES'] },
  'oryx':                     { species: 'ORYX', bags: ['ES', 'BHO'] },
};

// ---- Filtering ----

function filterSpecies(records, speciesList) {
  const upper = speciesList.map(s => s.toUpperCase());
  return records.filter(r => upper.some(s => r.species.toUpperCase().includes(s)));
}

function filterUnits(records, unitList) {
  return records.filter(r => unitList.some(u => r.units.includes(u)));
}

function filterYears(records, yearList) {
  return records.filter(r => yearList.includes(r.year));
}

function filterBag(records, bags) {
  const bagSet = new Set(bags);
  return records.filter(r =>
    bagSet.has(r.bag) || r.bag.split('/').some(part => bagSet.has(part))
  );
}

function isRestricted(unitDesc) {
  const dl = unitDesc.toLowerCase();
  return (
    dl.includes('youth')
    || dl.includes('mobility')
    || dl.includes('impair')
    || dl.includes('wsmr') || dl.includes('white sands') || dl.includes('missile')
    || dl.includes('private land')
    || dl.includes('military only')
    || dl.includes('veteran only')
  );
}

function filterRestricted(records, include) {
  if (include) return records;
  return records.filter(r => !isRestricted(r.unit_desc));
}

// ---- Odds calculation (port of HuntRecord.draw_odds) ----

function drawOdds(rec, hunterType, choice) {
  let apps, drawn;

  if (choice === 1) {
    if (hunterType === 'resident') { apps = rec.res_1st; drawn = rec.drawn_res; }
    else if (hunterType === 'nonresident') { apps = rec.nr_1st; drawn = rec.drawn_nr; }
    else if (hunterType === 'outfitter') { apps = rec.out_1st; drawn = rec.drawn_out; }
    else { apps = rec.total_1st; drawn = rec.drawn_res + rec.drawn_nr + rec.drawn_out; }
  } else if (choice === 2) {
    if (hunterType === 'resident') { apps = rec.res_2nd; drawn = rec.drawn_res_2nd; }
    else if (hunterType === 'nonresident') { apps = rec.nr_2nd; drawn = rec.drawn_nr_2nd; }
    else if (hunterType === 'outfitter') { apps = rec.out_2nd; drawn = rec.drawn_out_2nd; }
    else { apps = rec.total_2nd; drawn = rec.drawn_res_2nd + rec.drawn_nr_2nd + rec.drawn_out_2nd; }
  } else if (choice === 3) {
    if (hunterType === 'resident') { apps = rec.res_3rd; drawn = rec.drawn_res_3rd; }
    else if (hunterType === 'nonresident') { apps = rec.nr_3rd; drawn = rec.drawn_nr_3rd; }
    else if (hunterType === 'outfitter') { apps = rec.out_3rd; drawn = rec.drawn_out_3rd; }
    else { apps = rec.total_3rd; drawn = rec.drawn_res_3rd + rec.drawn_nr_3rd + rec.drawn_out_3rd; }
  } else {
    return null;
  }

  if (apps <= 0) return null;
  return Math.min(Math.round(drawn / apps * 1000) / 10, 100.0);
}

// ---- Aggregation (port of aggregate()) ----

function aggregate(records, hunterType) {
  const groups = {};
  for (const r of records) {
    if (!groups[r.hunt_code]) groups[r.hunt_code] = [];
    groups[r.hunt_code].push(r);
  }

  const results = [];
  for (const [huntCode, recs] of Object.entries(groups)) {
    recs.sort((a, b) => a.year - b.year);
    const latest = recs[recs.length - 1];

    const allOdds = recs.map(r => drawOdds(r, hunterType, 1));
    const validOdds = allOdds.filter(o => o !== null);
    const avgOdds = validOdds.length > 0
      ? Math.round(validOdds.reduce((a, b) => a + b, 0) / validOdds.length * 10) / 10
      : null;

    let latestApps, latestApps2, latestApps3, typeLic;
    if (hunterType === 'resident') {
      latestApps = latest.res_1st; latestApps2 = latest.res_2nd; latestApps3 = latest.res_3rd;
      typeLic = Math.round(latest.licenses * latest.r_pct / 100);
    } else if (hunterType === 'nonresident') {
      latestApps = latest.nr_1st; latestApps2 = latest.nr_2nd; latestApps3 = latest.nr_3rd;
      typeLic = Math.round(latest.licenses * latest.nr_pct / 100);
    } else if (hunterType === 'outfitter') {
      latestApps = latest.out_1st; latestApps2 = latest.out_2nd; latestApps3 = latest.out_3rd;
      typeLic = Math.round(latest.licenses * latest.o_pct / 100);
    } else {
      latestApps = latest.total_1st; latestApps2 = latest.total_2nd; latestApps3 = latest.total_3rd;
      typeLic = latest.licenses;
    }

    results.push({
      hunt_code: huntCode,
      species: latest.species,
      unit_desc: latest.unit_desc,
      units: latest.units,
      bag: latest.bag,
      latest_year: latest.year,
      licenses: latest.licenses,
      type_licenses: typeLic,
      latest_applicants: latestApps,
      latest_applicants_2nd: latestApps2,
      latest_applicants_3rd: latestApps3,
      latest_odds: drawOdds(latest, hunterType, 1),
      latest_odds_2nd: drawOdds(latest, hunterType, 2),
      latest_odds_3rd: drawOdds(latest, hunterType, 3),
      avg_odds: avgOdds,
      year_count: recs.length,
    });
  }

  return results;
}

// ---- Sorting ----

function sortHunts(hunts, sortBy) {
  const cmp = {
    latest_odds: (a, b) => (b.latest_odds ?? -1) - (a.latest_odds ?? -1),
    avg_odds: (a, b) => (b.avg_odds ?? -1) - (a.avg_odds ?? -1),
    licenses: (a, b) => b.licenses - a.licenses,
    unit: (a, b) => a.unit_desc.localeCompare(b.unit_desc),
  };
  return [...hunts].sort(cmp[sortBy] || cmp.latest_odds);
}

// ---- Rendering ----

function titleCase(str) {
  return str.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

function fmtOdds(val) {
  return val !== null ? val.toFixed(1) + '%' : 'N/A';
}

function oddsClass(val) {
  if (val === null) return 'odds-na';
  if (val >= 50) return 'odds-high';
  if (val >= 15) return 'odds-mid';
  return 'odds-low';
}

function fmtVal(v) {
  return v > 0 ? String(v) : '\u2014';
}

function renderTable(hunts, hunterType, numYears) {
  const thead = document.querySelector('#results-table thead tr');
  const tbody = document.querySelector('#results-table tbody');

  const typeAbbr = { resident: 'Res', nonresident: 'NR', outfitter: 'Out', total: 'Tot' };
  const licLabel = (typeAbbr[hunterType] || 'Tot') + ' Lic';

  thead.innerHTML = [
    '#', 'Hunt Code', 'Species', 'Unit / Description',
    'Bag', licLabel,
    '1st Apps', '1st Odds',
    '2nd Apps', '2nd Odds',
    '3rd Apps', '3rd Odds',
    'Yr', 'Avg 1st (' + numYears + 'yr)',
  ].map(h => '<th>' + h + '</th>').join('');

  if (hunts.length === 0) {
    tbody.innerHTML = '<tr class="loading-row"><td colspan="14">No matching hunts found.</td></tr>';
    return;
  }

  tbody.innerHTML = hunts.map((h, i) =>
    '<tr>' +
    '<td>' + (i + 1) + '</td>' +
    '<td class="mono">' + h.hunt_code + '</td>' +
    '<td>' + titleCase(h.species) + '</td>' +
    '<td><span class="unit-desc" title="' + escAttr(h.unit_desc) + '">' + escHtml(h.unit_desc) + '</span></td>' +
    '<td>' + escHtml(h.bag) + '</td>' +
    '<td>' + fmtVal(h.type_licenses) + '</td>' +
    '<td>' + fmtVal(h.latest_applicants) + '</td>' +
    '<td class="odds ' + oddsClass(h.latest_odds) + '">' + fmtOdds(h.latest_odds) + '</td>' +
    '<td>' + fmtVal(h.latest_applicants_2nd) + '</td>' +
    '<td class="odds ' + oddsClass(h.latest_odds_2nd) + '">' + fmtOdds(h.latest_odds_2nd) + '</td>' +
    '<td>' + fmtVal(h.latest_applicants_3rd) + '</td>' +
    '<td class="odds ' + oddsClass(h.latest_odds_3rd) + '">' + fmtOdds(h.latest_odds_3rd) + '</td>' +
    '<td>' + h.latest_year + '</td>' +
    '<td class="odds ' + oddsClass(h.avg_odds) + '">' + fmtOdds(h.avg_odds) + '</td>' +
    '</tr>'
  ).join('');

  updatePinnedWidth();
}

function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escAttr(s) {
  return escHtml(s).replace(/"/g, '&quot;');
}

function updatePinnedWidth() {
  const firstTh = document.querySelector('#results-table thead th:nth-child(1)');
  if (firstTh) {
    document.querySelector('#results-table').style.setProperty(
      '--col1-w', firstTh.offsetWidth + 'px'
    );
  }
}

// ---- Strategy rendering ----

function populateStrategySelect() {
  const sel = document.getElementById('strategy-select');
  // Group hunt types by species
  const bySpecies = {};
  for (const [name, { species }] of Object.entries(HUNT_TYPES)) {
    if (!bySpecies[species]) bySpecies[species] = [];
    bySpecies[species].push(name);
  }
  for (const species of Object.keys(bySpecies).sort()) {
    const optgroup = document.createElement('optgroup');
    optgroup.label = titleCase(species);
    for (const name of bySpecies[species].sort()) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = titleCase(name);
      optgroup.appendChild(opt);
    }
    sel.appendChild(optgroup);
  }
}

function renderStrategy(records, huntTypeName, hunterType) {
  const cfg = HUNT_TYPES[huntTypeName];
  if (!cfg) return;

  // Get latest year per hunt code
  const latest = {};
  for (const r of records) {
    if (!latest[r.hunt_code] || r.year > latest[r.hunt_code].year) {
      latest[r.hunt_code] = r;
    }
  }
  const recs = Object.values(latest);
  if (recs.length === 0) {
    document.getElementById('strategy-results').innerHTML =
      '<p class="strategy-empty">No matching hunts found for this strategy.</p>';
    return;
  }

  const year = Math.max(...recs.map(r => r.year));
  const typeAbbr = { resident: 'Resident', nonresident: 'Nonresident', outfitter: 'Outfitter', total: 'All' };
  const bagLabel = cfg.bags.join(', ');

  let html = '<div class="strategy-header">' +
    '<h2>' + escHtml(titleCase(huntTypeName)) + '</h2>' +
    '<p>' + titleCase(cfg.species) + ' (bag: ' + escHtml(bagLabel) + ') &middot; ' +
    (typeAbbr[hunterType] || 'All') + ' &middot; ' + year + '</p></div>';

  const choices = [[1, '1st'], [2, '2nd'], [3, '3rd']];
  for (const [choice, label] of choices) {
    const ranked = [];
    for (const r of recs) {
      const odds = drawOdds(r, hunterType, choice);
      if (odds !== null && odds > 0) {
        let apps;
        if (hunterType === 'resident') apps = [r.res_1st, r.res_2nd, r.res_3rd][choice - 1];
        else if (hunterType === 'nonresident') apps = [r.nr_1st, r.nr_2nd, r.nr_3rd][choice - 1];
        else if (hunterType === 'outfitter') apps = [r.out_1st, r.out_2nd, r.out_3rd][choice - 1];
        else apps = [r.total_1st, r.total_2nd, r.total_3rd][choice - 1];
        ranked.push({ odds, apps, rec: r });
      }
    }
    ranked.sort((a, b) => b.odds - a.odds);
    const shown = ranked.slice(0, 3);

    html += '<div class="strategy-tier"><h3>Best ' + label + ' Choice Options</h3>';

    if (shown.length === 0) {
      html += '<p class="strategy-empty">No hunts with draws in this tier.</p>';
    } else {
      html += '<table class="strategy-table"><thead><tr>' +
        '<th>#</th><th>Hunt Code</th><th>Unit / Description</th>' +
        '<th>Bag</th><th>Licenses</th><th>Apps</th><th>Draw %</th>' +
        '</tr></thead><tbody>';
      for (let i = 0; i < shown.length; i++) {
        const s = shown[i];
        html += '<tr>' +
          '<td>' + (i + 1) + '</td>' +
          '<td class="mono">' + escHtml(s.rec.hunt_code) + '</td>' +
          '<td><span class="unit-desc" title="' + escAttr(s.rec.unit_desc) + '">' + escHtml(s.rec.unit_desc) + '</span></td>' +
          '<td>' + escHtml(s.rec.bag) + '</td>' +
          '<td>' + s.rec.licenses + '</td>' +
          '<td>' + s.apps + '</td>' +
          '<td class="odds ' + oddsClass(s.odds) + '">' + s.odds.toFixed(1) + '%</td>' +
          '</tr>';
      }
      html += '</tbody></table>';
    }
    html += '</div>';
  }

  document.getElementById('strategy-results').innerHTML = html;
}

// ---- CSV export ----

function exportCSV(hunts, hunterType) {
  const headers = [
    'hunt_code', 'species', 'unit_desc', 'bag',
    'total_licenses', hunterType + '_licenses',
    hunterType + '_1st_apps', hunterType + '_2nd_apps', hunterType + '_3rd_apps',
    '1st_odds_pct', '2nd_odds_pct', '3rd_odds_pct',
    'avg_1st_odds_pct', 'years_of_data',
  ];

  const csvEsc = v => {
    const s = String(v);
    return s.includes(',') || s.includes('"') || s.includes('\n')
      ? '"' + s.replace(/"/g, '""') + '"'
      : s;
  };

  const rows = hunts.map(h => [
    h.hunt_code, h.species, csvEsc(h.unit_desc), h.bag,
    h.licenses, h.type_licenses,
    h.latest_applicants, h.latest_applicants_2nd, h.latest_applicants_3rd,
    h.latest_odds !== null ? h.latest_odds.toFixed(1) : '',
    h.latest_odds_2nd !== null ? h.latest_odds_2nd.toFixed(1) : '',
    h.latest_odds_3rd !== null ? h.latest_odds_3rd.toFixed(1) : '',
    h.avg_odds !== null ? h.avg_odds.toFixed(1) : '',
    h.year_count,
  ]);

  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'nm_draw_odds_' + hunterType + '.csv';
  a.click();
  URL.revokeObjectURL(url);
}

// ---- Multi-select widget ----

function populateSpeciesSelect() {
  const dropdown = document.getElementById('species-dropdown');
  const toggle = document.getElementById('species-toggle');

  let html = '<div class="ms-actions"><button type="button" id="ms-all">All</button><button type="button" id="ms-none">None</button></div>';
  for (const sp of SPECIES_LIST) {
    html += '<label class="ms-option"><input type="checkbox" value="' + sp + '" checked>' + titleCase(sp) + '</label>';
  }
  dropdown.innerHTML = html;

  toggle.addEventListener('click', () => dropdown.classList.toggle('open'));

  document.addEventListener('click', e => {
    if (!e.target.closest('#species-ms')) dropdown.classList.remove('open');
  });

  dropdown.querySelector('#ms-all').addEventListener('click', () => {
    dropdown.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
    updateSpeciesLabel();
    applyFilters();
  });

  dropdown.querySelector('#ms-none').addEventListener('click', () => {
    dropdown.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
    updateSpeciesLabel();
    applyFilters();
  });

  dropdown.addEventListener('change', () => {
    updateSpeciesLabel();
    applyFilters();
  });
}

function updateSpeciesLabel() {
  const toggle = document.getElementById('species-toggle');
  const checked = getSelectedSpecies();
  if (checked.length === 0) toggle.textContent = 'None selected';
  else if (checked.length === SPECIES_LIST.length) toggle.textContent = 'All Species';
  else if (checked.length <= 2) toggle.textContent = checked.map(titleCase).join(', ');
  else toggle.textContent = checked.length + ' selected';
}

function getSelectedSpecies() {
  const cbs = document.querySelectorAll('#species-dropdown input[type="checkbox"]:checked');
  return [...cbs].map(cb => cb.value);
}

// ---- Year toggles ----

function populateYearToggles() {
  const container = document.getElementById('year-toggles');
  // Default: only latest year active
  const latestYear = YEARS_LIST[YEARS_LIST.length - 1];
  container.innerHTML = YEARS_LIST.map(y =>
    '<button type="button" class="year-btn' + (y === latestYear ? ' active' : '') + '" data-year="' + y + '">' + y + '</button>'
  ).join('');

  container.addEventListener('click', e => {
    const btn = e.target.closest('.year-btn');
    if (!btn) return;
    btn.classList.toggle('active');
    // If none active, activate all
    const anyActive = container.querySelector('.year-btn.active');
    if (!anyActive) {
      container.querySelectorAll('.year-btn').forEach(b => b.classList.add('active'));
    }
    applyFilters();
  });
}

function getSelectedYears() {
  const btns = document.querySelectorAll('.year-btn.active');
  return [...btns].map(b => parseInt(b.dataset.year, 10));
}

// ---- URL hash state ----

function stateToHash() {
  const params = new URLSearchParams();
  const strategy = document.getElementById('strategy-select').value;
  if (strategy) params.set('strat', strategy);
  const sp = getSelectedSpecies();
  if (sp.length > 0 && sp.length < SPECIES_LIST.length) params.set('sp', sp.join(','));
  const yrs = getSelectedYears();
  if (yrs.length > 0 && yrs.length < YEARS_LIST.length) params.set('y', yrs.join(','));
  const ht = document.getElementById('hunter-type-select').value;
  if (ht !== 'resident') params.set('ht', ht);
  const u = document.getElementById('unit-input').value.trim();
  if (u) params.set('u', u);
  const sort = document.getElementById('sort-select').value;
  if (sort !== 'latest_odds') params.set('sort', sort);
  const top = document.getElementById('top-select').value;
  if (top !== '25') params.set('n', top);
  if (document.getElementById('include-restricted').checked) params.set('restricted', '1');
  const str = params.toString();
  history.replaceState(null, '', str ? '#' + str : location.pathname);
}

function hashToState() {
  if (!location.hash || location.hash.length < 2) return;
  const params = new URLSearchParams(location.hash.slice(1));

  if (params.has('strat')) document.getElementById('strategy-select').value = params.get('strat');

  if (params.has('sp')) {
    const sp = params.get('sp').split(',');
    document.querySelectorAll('#species-dropdown input[type="checkbox"]').forEach(cb => {
      cb.checked = sp.includes(cb.value);
    });
    updateSpeciesLabel();
  }

  if (params.has('y')) {
    const yrs = params.get('y').split(',').map(Number);
    document.querySelectorAll('.year-btn').forEach(btn => {
      btn.classList.toggle('active', yrs.includes(parseInt(btn.dataset.year, 10)));
    });
  }

  if (params.has('ht')) document.getElementById('hunter-type-select').value = params.get('ht');
  if (params.has('u')) document.getElementById('unit-input').value = params.get('u');
  if (params.has('sort')) document.getElementById('sort-select').value = params.get('sort');
  if (params.has('n')) document.getElementById('top-select').value = params.get('n');
  if (params.has('restricted')) document.getElementById('include-restricted').checked = true;
}

// ---- Main filter pipeline ----

function applyFilters() {
  let records = RAW_RECORDS;

  // Restricted hunt filter (applied first, globally)
  const includeRestricted = document.getElementById('include-restricted').checked;
  records = filterRestricted(records, includeRestricted);

  // Year filter
  const selectedYears = getSelectedYears();
  if (selectedYears.length > 0 && selectedYears.length < YEARS_LIST.length) {
    records = filterYears(records, selectedYears);
  }

  const hunterType = document.getElementById('hunter-type-select').value;
  const strategyKey = document.getElementById('strategy-select').value;
  const unitInput = document.getElementById('unit-input').value.trim();

  // Strategy mode
  if (strategyKey) {
    const cfg = HUNT_TYPES[strategyKey];
    if (cfg) {
      records = filterSpecies(records, [cfg.species]);
      records = filterBag(records, cfg.bags);
      if (unitInput) {
        records = filterUnits(records, unitInput.split(/[,\s]+/).filter(Boolean));
      }

      // Show strategy view, hide table view
      document.getElementById('results').style.display = 'none';
      document.getElementById('strategy-results').style.display = '';
      document.getElementById('sort-group').style.display = 'none';
      document.getElementById('top-group').style.display = 'none';

      renderStrategy(records, strategyKey, hunterType);
      document.getElementById('result-count').textContent = records.length + ' matching records';

      window._currentHunts = null;
      window._currentHunterType = hunterType;
      stateToHash();
      return;
    }
  }

  // Normal table mode
  document.getElementById('results').style.display = '';
  document.getElementById('strategy-results').style.display = 'none';
  document.getElementById('sort-group').style.display = '';
  document.getElementById('top-group').style.display = '';

  // Species filter
  const selectedSpecies = getSelectedSpecies();
  if (selectedSpecies.length > 0 && selectedSpecies.length < SPECIES_LIST.length) {
    records = filterSpecies(records, selectedSpecies);
  }

  // Unit filter
  if (unitInput) {
    const unitList = unitInput.split(/[,\s]+/).filter(Boolean);
    records = filterUnits(records, unitList);
  }

  // Aggregate
  let hunts = aggregate(records, hunterType);

  // Sort
  const sortBy = document.getElementById('sort-select').value;
  hunts = sortHunts(hunts, sortBy);

  // Top N
  const top = parseInt(document.getElementById('top-select').value, 10);
  const totalCount = hunts.length;
  if (top > 0) hunts = hunts.slice(0, top);

  const numYears = new Set(records.map(r => r.year)).size;

  renderTable(hunts, hunterType, numYears);

  document.getElementById('result-count').textContent =
    hunts.length + ' of ' + totalCount + ' hunts shown';

  window._currentHunts = hunts;
  window._currentHunterType = hunterType;

  stateToHash();
}

// ---- Event binding ----

function bindEvents() {
  ['hunter-type-select', 'sort-select', 'top-select', 'strategy-select'].forEach(id => {
    document.getElementById(id).addEventListener('change', applyFilters);
  });

  document.getElementById('include-restricted').addEventListener('change', applyFilters);

  let unitTimer;
  document.getElementById('unit-input').addEventListener('input', () => {
    clearTimeout(unitTimer);
    unitTimer = setTimeout(applyFilters, 300);
  });

  document.getElementById('export-csv-btn').addEventListener('click', () => {
    if (window._currentHunts) exportCSV(window._currentHunts, window._currentHunterType);
  });
}

// ---- Init ----

async function init() {
  const tbody = document.querySelector('#results-table tbody');
  tbody.innerHTML = '<tr class="loading-row"><td colspan="14">Loading data...</td></tr>';

  await loadData();
  populateSpeciesSelect();
  populateStrategySelect();
  populateYearToggles();
  bindEvents();
  hashToState();
  applyFilters();
}

document.addEventListener('DOMContentLoaded', init);
