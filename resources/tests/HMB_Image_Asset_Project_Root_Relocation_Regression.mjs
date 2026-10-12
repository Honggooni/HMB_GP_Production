import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const option = (name) => {
  const index = process.argv.indexOf(name);
  return index < 0 ? '' : process.argv[index + 1] || '';
};
const libraryRoot = path.resolve(option('--library-root') || fileURLToPath(new URL('../..', import.meta.url)));
const sourcePath = path.join(libraryRoot, 'widgets/HMBImageAssetLibraryWidget.js');
const sourceBytes = fs.readFileSync(sourcePath);
const source = sourceBytes.toString('utf8');
const sha = (value) => crypto.createHash('sha256').update(value).digest('hex');
const widget = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const old = '//fin-rcomp1/Composite_Team/projects_AI';
const next = '//192.168.200.19/v/projects/Ai_Ct_image';
for (const prefix of [old, old.toUpperCase(), old.replaceAll('/', '\\')]) {
  assert.equal(widget.hmbRelocateImageProjectPath(prefix + '/superwings12/캐릭터/Hero.png'), next + '/superwings12/캐릭터/Hero.png');
}
for (const path of [old + '_archive/Hero.png', '//artist-server/custom-projects', 'D:/MyProject', 'https://example.com/hero.png']) {
  assert.equal(widget.hmbRelocateImageProjectPath(path), path);
}
const raw = {catalog_root: old, project_root: old+'/superwings12',project_id:'superwings12',project_uid:'project-uid',
  projects:[{path:old+'/superwings12',project_id:'superwings12',name:'superwings12'}],
  assets:[{asset_library_id:'hero',asset_id:'Hero',image_name:'Hero',source_uid:'project:hero',source_kind:'project',
    registered:true,selected:true,selection_order:1,path:old+'/superwings12/Character/Hero.png',relative_path:'Character/Hero.png'}]};
raw.shot_routing = widget.hmbNormalizeImageAssetState({}).shot_routing;
const before = JSON.stringify(raw);
const moved = widget.hmbNormalizeImageAssetState(raw);
assert.equal(moved.catalog_root,next);
assert.equal(moved.project_root,next+'/superwings12');
assert.equal(moved.projects[0].path,moved.project_root);
assert.equal(moved.assets[0].path,next+'/superwings12/Character/Hero.png');
for (const key of ['asset_library_id','source_uid','asset_id','selected','selection_order']) assert.equal(moved.assets[0][key],raw.assets[0][key]);
assert.deepEqual(widget.hmbNormalizeImageAssetState(JSON.parse(before.replaceAll(old,next))),moved);
assert.deepEqual(widget.hmbNormalizeImageAssetState(moved),moved);
assert.equal(JSON.stringify(raw),before);
assert.equal(widget.hmbNormalizeImageAssetState({}).catalog_root,next);
assert.match(source,/const nativePath = hmbRelocateImageProjectPath\(nativeProjectRootValue\(container\)\)/);
console.log('ImageAsset UI share relocation, saved state and native-root echo: PASS');

// A scan deliberately clears project_id/UID/cache until the backend resolves
// authority. Its catalog name is display evidence only, never a replacement ID.
const pending = {
  project_root: 'C:/fixture/ProjectB', project_id: '', project_uid: '', project_cache_uid: '',
  projects: [
    { path: 'C:/fixture/ProjectA', name: 'Project A', project_id: 'A' },
    { path: 'C:/fixture/ProjectB', name: 'Project B', project_id: 'B' },
    { path: 'C:/fixture/ProjectB_archive', name: 'Archive', project_id: 'Archive' },
  ],
};
const pendingBefore = JSON.stringify(pending);
assert.equal(widget.hmbImageAssetProjectDisplayName(pending), 'Project B');
assert.equal(widget.hmbImageAssetProjectDisplayName({ ...pending, project_root: 'c:\\FIXTURE\\projectb' }), 'Project B');
assert.equal(widget.hmbImageAssetProjectDisplayName({ ...pending, project_id: 'Resolved B' }), 'Resolved B');
assert.equal(widget.hmbImageAssetProjectDisplayName({ ...pending, project_root: '' }), '');
assert.equal(widget.hmbImageAssetProjectDisplayName({ ...pending, project_root: 'C:/fixture/Project' }), '');
assert.equal(widget.hmbImageAssetProjectDisplayName({ ...pending, project_root: 'C:/fixture/Unknown' }), '');
assert.equal(widget.hmbImageAssetProjectDisplayName({ ...pending, projects: [{ path: pending.project_root, name: ' ', project_id: 'ID fallback' }] }), 'ID fallback');
assert.equal(widget.hmbImageAssetProjectDisplayName({ ...pending, projects: [pending.projects[1], { path: pending.project_root.toUpperCase(), name: 'Duplicate' }] }), 'Project B');
assert.equal(JSON.stringify(pending), pendingBefore, 'Resolving a display name must not serialize invented project authority.');
console.log('ImageAsset selected project display authority, exact paths, duplicate ordering and unchanged state: PASS');

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); }
catch {
  try { playwright = require(path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
  catch { /* Hostless relocation/display checks do not require Chrome. */ }
}
const executablePath = process.env.HMB_IMAGE_ASSET_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const requireBrowser = process.argv.includes('--require-browser') || process.env.HMB_IMAGE_ASSET_REQUIRE_BROWSER === '1';
if (!playwright || !fs.existsSync(executablePath)) {
  assert.equal(requireBrowser, false, 'Required project-selection Chrome fixture is unavailable.');
  console.log('ImageAsset project-selection full mount Chrome: NOT RUN (browser unavailable)');
} else {
  const evidenceDir = option('--evidence-dir') || process.env.HMB_IMAGE_ASSET_PROJECT_LABEL_EVIDENCE_DIR;
  if (evidenceDir) fs.mkdirSync(evidenceDir, { recursive: true });
  const evidence = {
    schema: 'hmb-image-project-label-regression', version: 1, observed_at: new Date().toISOString(),
    source_root: libraryRoot, source_sha256_before: sha(sourceBytes),
    scope: 'Actual headless Chrome full widget, simulated transport/busy/final/error responses; no live engine or paid API',
    engine_disconnected_reproduced: false,
    engine_disconnected_scope: 'No engine connection in this fixture; disconnect toast is not tested here',
    catalog_rows: 500, cases: [], screenshots: [],
  };
  const browser = await playwright.chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', (route) => route.abort());
  const screenshot = async (name) => {
    if (!evidenceDir) return;
    const file = path.join(evidenceDir, name);
    await page.locator('#widget').screenshot({ path: file });
    evidence.screenshots.push({ file: name, sha256: sha(fs.readFileSync(file)) });
  };
  try {
    await page.setContent('<meta charset="utf-8"><style>body{margin:0;background:#111}#widget{width:1100px;height:780px}</style><div id="widget"></div>');
    await page.evaluate(async (uri) => {
      const widget = await import(uri);
      const pixel = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j14sAAAAASUVORK5CYII=';
      const base = widget.hmbNormalizeImageAssetState({
        edit_transport_schema: 'hmb-image-asset-edit-v1', catalog_root: 'C:/fixture',
        project_root: 'C:/fixture/ProjectA', project_id: 'Project A', project_uid: 'project-a',
        project_cache_uid: 'cache-a', manifest_signature: 'manifest-a', folder_signature: 'folder-a',
        scan_revision: 7, ui_edit_revision: 10, language: 'ko',
        projects: ['A', 'B', 'C'].map((letter) => ({ path: `C:/fixture/Project${letter}`, name: `Project ${letter}`, project_id: `Project${letter}`, project_uid: `project-${letter.toLowerCase()}` })),
        assets: Array.from({ length: 500 }, (_, i) => ({ asset_library_id: `library-${i}`, source_uid: `project:asset-${i}`,
          source_kind: 'project', registered: true, asset_id: `asset-${i}`, image_name: `Image ${i}`,
          path: `C:/fixture/ProjectA/Image${i}.png`, relative_path: `Image${i}.png`, thumbnail_url: pixel,
          selected: i < 2, selection_order: i + 1 })),
      });
      const fixture = { widget, base };
      fixture.mount = (state = base, compact = false) => {
        fixture.controller?.cleanup();
        const previous = document.getElementById('widget'), container = document.createElement('div');
        container.id = 'widget'; previous.replaceWith(container);
        fixture.container = container; fixture.writes = [];
        fixture.onChange = (value) => {
          const entry = { value, state: JSON.parse(value), at: performance.now() };
          fixture.writes.push(entry);
          return new Promise((resolve, reject) => { entry.resolve = resolve; entry.reject = reject; });
        };
        fixture.props = (state) => ({ value: JSON.stringify(state), onChange: fixture.onChange });
        fixture.controller = widget.default(container, fixture.props(state));
        if (compact) widget.hmbSetImageAssetLibraryCompact(container, true, { geometry: false });
      };
      fixture.snap = () => {
        const container = fixture.container, state = container.__hmbImageAssetLatestState;
        const expanded = container.querySelector('[data-library-expanded]') || container.__hmbImageAssetExpandedElement;
        return { select_value: container.querySelector('[data-project-select]').value,
          select_label: container.querySelector('[data-project-select] option:checked')?.textContent,
          header: container.querySelector('.heading span')?.textContent,
          folder_root: expanded?.querySelector('.tree-row.root span')?.textContent.trim(),
          sidebar: expanded?.querySelector('.tree-panel .panel-title b')?.textContent,
          error: expanded?.querySelector('[data-transport-status]')?.textContent || '',
          project_root: state.project_root, project_id: state.project_id, project_uid: state.project_uid,
          project_cache_uid: state.project_cache_uid, busy: container.__hmbImageAssetBusy,
          compact: Boolean(container.__hmbImageAssetCompact),
          scan_revision: state.scan_revision, ui_edit_revision: state.ui_edit_revision };
      };
      fixture.select = async (letter) => {
        const path = `C:/fixture/Project${letter}`, started = performance.now(), from = fixture.writes.length;
        const control = fixture.container.querySelector('[data-project-select]');
        control.value = path; control.dispatchEvent(new Event('change', { bubbles: true }));
        for (let i = 0; i < 100; i++) {
          const entry = fixture.writes.slice(from).find((entry) => entry.state.project_root === path);
          if (entry) return { index: fixture.writes.indexOf(entry), elapsed: entry.at - started };
          await new Promise((resolve) => setTimeout(resolve, 10));
        }
        throw Error('Selected project was not published');
      };
      fixture.update = (state) => { fixture.controller.update(fixture.props(state)); return fixture.snap(); };
      window.fixture = fixture;
    }, 'data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
    const labels = (view, name) => {
      assert.ok(view.header.endsWith(` → ${name}`), JSON.stringify(view));
      if (view.compact) return; // Expanded DOM is intentionally deferred while detached.
      assert.equal(view.folder_root, name, JSON.stringify(view));
      assert.equal(view.sidebar, name, JSON.stringify(view));
    };
    for (const compact of [false, true]) {
      await page.evaluate((compact) => fixture.mount(fixture.base, compact), compact);
      const initial = await page.evaluate(() => fixture.snap());
      labels(initial, 'Project A');
      if (!compact) await screenshot('01-before.png');
      const selection = await page.evaluate(() => fixture.select('B'));
      const busy = await page.evaluate((index) => {
        const f = fixture, entry = f.writes[index];
        f.busy = { ...entry.state, scan_busy: true, scan_request_id: 'fixture-scan-b' };
        const wire = { bytes: new TextEncoder().encode(entry.value).length, asset_rows: entry.state.assets.length,
          id: entry.state.project_id, uid: entry.state.project_uid, cache: entry.state.project_cache_uid,
          shot_identity_preserved: JSON.stringify(entry.state.shot_routing) === JSON.stringify(f.base.shot_routing) };
        return { view: f.update(f.busy), wire };
      }, selection.index);
      labels(busy.view, 'Project B');
      assert.equal(busy.view.select_label, 'Project B');
      assert.equal(busy.view.busy, true);
      assert.deepEqual([busy.wire.id, busy.wire.uid, busy.wire.cache], ['', '', '']);
      assert.equal(busy.wire.asset_rows, 500);
      assert.equal(busy.wire.shot_identity_preserved, true);
      if (!compact) await screenshot('02-busy-selected-project.png');
      const acknowledged = await page.evaluate(async (index) => { fixture.writes[index].resolve(); await Promise.resolve(); return fixture.snap(); }, selection.index);
      labels(acknowledged, 'Project B');
      assert.equal(acknowledged.busy, true, 'Transport ACK cannot invent completed project authority.');
      const final = await page.evaluate(() => fixture.update({ ...fixture.busy, scan_busy: false, scan_revision: 8,
        project_id: 'Resolved Project B', project_uid: 'project-b', project_cache_uid: 'cache-b', assets: [] }));
      labels(final, 'Resolved Project B');
      assert.equal(final.project_uid, 'project-b');
      assert.equal(final.busy, false);
      if (!compact) await screenshot('03-final.png');
      const stale = await page.evaluate(() => fixture.update(fixture.base));
      labels(stale, 'Resolved Project B');
      let expandedAfterCompletion;
      if (compact) {
        expandedAfterCompletion = await page.evaluate(() => {
          fixture.container.querySelector('.heading b').dispatchEvent(new MouseEvent('dblclick', { bubbles: true, button: 0 }));
          return fixture.snap();
        });
        assert.equal(expandedAfterCompletion.compact, false);
        labels(expandedAfterCompletion, 'Resolved Project B');
      }
      evidence.cases.push({ case: 'busy-ack-final-stale', compact, initial, busy, acknowledged, final, stale,
        expandedAfterCompletion, click_to_wire_ms: selection.elapsed });
    }
    await page.evaluate(() => fixture.mount());
    const failedSelection = await page.evaluate(() => fixture.select('B'));
    const error = await page.evaluate(async (index) => {
      // A busy backend echo already owns the command. Transport rollback is
      // exercised before that acceptance, when the original publication owns it.
      fixture.writes[index].reject(new Error('fixture project transport failed'));
      await Promise.resolve(); await Promise.resolve();
      return fixture.snap();
    }, failedSelection.index);
    labels(error, 'Project A');
    assert.equal(error.project_uid, 'project-a');
    assert.equal(error.busy, false);
    assert.ok(error.error.includes('fixture project transport failed'));
    await screenshot('04-transport-error-restored-project.png');
    evidence.cases.push({ case: 'transport-failure-restores-canonical-project', view: error });

    // The canonical error snapshot can retain the selected path with unresolved
    // authority; its display follows that path and still leaves UID/cache empty.
    const scanError = await page.evaluate(() => fixture.update({ ...fixture.base, project_root: 'C:/fixture/ProjectB',
      project_id: '', project_uid: '', project_cache_uid: '', scan_revision: 8, scan_busy: false, error: 'fixture scan failed' }));
    labels(scanError, 'Project B');
    assert.deepEqual([scanError.project_id, scanError.project_uid, scanError.project_cache_uid], ['', '', '']);
    await screenshot('05-scan-error-selected-project.png');
    evidence.cases.push({ case: 'scan-error-retains-selected-path-without-authority', view: scanError });

    await page.evaluate(() => fixture.mount());
    const oldSelection = await page.evaluate(() => fixture.select('B'));
    await page.evaluate((index) => fixture.update({ ...fixture.writes[index].state, scan_revision: 8, scan_busy: false,
      project_id: 'Project B', project_uid: 'project-b', project_cache_uid: 'cache-b' }), oldSelection.index);
    const newSelection = await page.evaluate(() => fixture.select('C'));
    const fast = await page.evaluate(async ({ oldIndex, newIndex }) => {
      const f = fixture;
      f.update({ ...f.writes[newIndex].state, scan_busy: true, scan_request_id: 'fixture-scan-c' });
      f.writes[oldIndex].reject(new Error('late old project failure'));
      await Promise.resolve(); await Promise.resolve();
      const lateReject = f.snap();
      f.update({ ...f.writes[oldIndex].state, project_id: 'Project B', project_uid: 'project-b', scan_revision: 8, scan_busy: false });
      const staleFinal = f.snap();
      const final = f.update({ ...f.writes[newIndex].state, project_id: 'Project C', project_uid: 'project-c',
        project_cache_uid: 'cache-c', scan_revision: 9, scan_busy: false, assets: [] });
      return { lateReject, staleFinal, final };
    }, { oldIndex: oldSelection.index, newIndex: newSelection.index });
    for (const view of [fast.lateReject, fast.staleFinal, fast.final]) labels(view, 'Project C');
    assert.equal(fast.final.project_uid, 'project-c');
    evidence.cases.push({ case: 'new-selection-owns-late-failure-and-lower-revision-echo', ...fast });

    await page.evaluate(() => fixture.mount());
    const retiringSelection = await page.evaluate(() => fixture.select('B'));
    const replacement = await page.evaluate(async (index) => {
      const oldEntry = fixture.writes[index];
      fixture.mount({ ...fixture.base, project_root: 'C:/fixture/ProjectC', project_id: 'Project C', project_uid: 'project-c' });
      oldEntry.reject(new Error('retired widget failure'));
      await Promise.resolve(); await Promise.resolve(); return fixture.snap();
    }, retiringSelection.index);
    labels(replacement, 'Project C');
    evidence.cases.push({ case: 'cleanup-replacement-retains-own-display', view: replacement });

    const escaped = await page.evaluate(() => {
      const name = 'Project <img src=x onerror=alert(1)> & "quoted"';
      fixture.mount({ ...fixture.base, project_root: 'C:/fixture/ProjectB', project_id: '', project_uid: '', project_cache_uid: '',
        projects: [{ path: 'C:/fixture/ProjectB', name, project_id: 'B' }] });
      return { view: fixture.snap(), name, markup_elements: fixture.container.querySelectorAll('.heading img,.tree-row.root img,.tree-panel .panel-title img').length };
    });
    labels(escaped.view, escaped.name);
    assert.equal(escaped.markup_elements, 0, 'Display fallback remains escaped in every rendered label.');
    evidence.cases.push({ case: 'catalog-display-is-escaped', ...escaped });

    // Browser selectOption makes option selectedness dirty. A retained select
    // must be synchronized after its children are reordered/renamed/removed,
    // and a temporarily missing catalog cannot erase a selected project path.
    await page.evaluate(() => {
      const f = fixture, root = '//192.168.200.19/v/projects/Ai_Ct_image';
      f.uncProjects = ['Dinoster5', 'Katuri8', 'superwings12'].map((name) => ({
        path: `${root}/${name}`, name, project_id: name, project_uid: `uid-${name}`,
      }));
      f.uncMount = (from, compact, catalog) => {
        const projects = catalog === 'retained-selected-row'
          ? [{ path: `${root}/Other`, name: 'Other', project_id: 'Other', project_uid: 'uid-Other' }, f.uncProjects[0]]
          : f.uncProjects;
        const selected = projects.find((row) => row.name === from);
        f.mount({ ...f.base, catalog_root: root, projects, assets: [],
          project_root: selected?.path || '', project_id: selected?.name || '',
          project_uid: selected?.project_uid || '', project_cache_uid: selected ? `cache-${from}` : '',
          scan_busy: false, scan_revision: 20, ui_edit_revision: 20 }, compact);
        f.dropdownTimeline = [];
      };
      f.dropdownSnap = (stage) => {
        const view = f.snap(), select = f.container.querySelector('[data-project-select]');
        const sample = { stage, at: performance.now(), ...view,
          selected_index: select.selectedIndex,
          options: [...select.options].map((option) => ({ value: option.value, text: option.textContent,
            selected: option.selected, default_selected: option.defaultSelected })),
        };
        f.dropdownTimeline.push(sample);
        return sample;
      };
      f.dropdownFrames = async (stage) => {
        for (let frame = 0; frame < 3; frame++) {
          await new Promise((resolve) => requestAnimationFrame(() => {
            f.dropdownSnap(`${stage}-raf-${frame}`); resolve();
          }));
        }
      };
    });
    const pathIdentity = (value) => String(value || '').replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase();
    const dropdownFailures = [];
    const checkDropdown = (caseName, timeline, expectedPath, expectedName) => {
      const failures = timeline.filter((view) => (
        pathIdentity(view.select_value) !== pathIdentity(expectedPath)
        || view.select_label !== expectedName
      ));
      if (failures.length) dropdownFailures.push({ case: caseName, failures });
      return failures.length;
    };
    const dropdownConfigs = [
      { name: 'empty-first-option', from: '', to: 'Dinoster5', catalog: 'stable' },
      { name: 'reverse-existing-selection', from: 'superwings12', to: 'Dinoster5', catalog: 'reversed' },
      { name: 'cased-catalog-paths', from: '', to: 'Dinoster5', catalog: 'cased' },
      { name: 'temporarily-empty-catalog', from: 'superwings12', to: 'Dinoster5', catalog: 'empty' },
      { name: 'trailing-catalog-paths', from: '', to: 'Dinoster5', catalog: 'trailing' },
      { name: 'updated-catalog-members', from: 'superwings12', to: 'Dinoster5', catalog: 'replacement' },
      { name: 'retained-selected-row-removal', from: 'Other', to: 'Dinoster5', catalog: 'retained-selected-row' },
    ];
    for (const compact of [false, true]) {
      for (const config of dropdownConfigs) {
        await page.evaluate(({ config, compact }) => fixture.uncMount(config.from, compact, config.catalog), { config, compact });
        const expectedPath = `//192.168.200.19/v/projects/Ai_Ct_image/${config.to}`;
        await page.selectOption('#widget [data-project-select]', expectedPath);
        await page.evaluate(async () => { fixture.dropdownSnap('selected-immediate'); await fixture.dropdownFrames('selected'); });
        await page.waitForFunction(() => fixture.writes.length > 0);
        const busy = await page.evaluate(async (config) => {
          const f = fixture, entry = f.writes.at(-1);
          f.dropdownEntry = entry;
          f.dropdownBusy = { ...entry.state, scan_busy: true, scan_request_id: `dropdown-${config.name}` };
          if (config.catalog === 'reversed') f.dropdownBusy.projects = [...f.uncProjects].reverse();
          if (config.catalog === 'cased') f.dropdownBusy.projects = f.uncProjects.map((row) => ({ ...row, path: row.path.toUpperCase() }));
          if (config.catalog === 'trailing') f.dropdownBusy.projects = f.uncProjects.map((row) => ({ ...row, path: `${row.path}/` }));
          if (config.catalog === 'empty') f.dropdownBusy.projects = [];
          if (config.catalog === 'retained-selected-row') f.dropdownBusy.projects = [f.uncProjects[0]];
          if (config.catalog === 'replacement') f.dropdownBusy.projects = [
            { path: '//192.168.200.19/v/projects/Ai_Ct_image/NewProject', name: 'NewProject', project_id: 'NewProject' },
            ...f.uncProjects.filter((row) => row.name !== config.to),
          ];
          f.update(f.dropdownBusy); f.dropdownSnap('busy-immediate'); await f.dropdownFrames('busy');
          entry.resolve(); await Promise.resolve(); await Promise.resolve();
          f.dropdownSnap('transport-ack'); await f.dropdownFrames('ack');
          return { authority: [entry.state.project_id, entry.state.project_uid, entry.state.project_cache_uid],
            canonical_paths: f.dropdownBusy.projects.map((row) => row.path),
            actual_canonical_paths: f.container.__hmbImageAssetLatestState.projects.map((row) => row.path) };
        }, config);
        assert.deepEqual(busy.authority, ['', '', ''], 'Display continuity cannot invent project authority.');
        assert.deepEqual(busy.actual_canonical_paths, busy.canonical_paths,
          'A display-only option cannot add or change canonical catalog entries.');
        if (!compact && config.catalog === 'retained-selected-row') await screenshot('06-dropdown-busy-retained-selected-row.png');
        await page.evaluate(async (config) => {
          const f = fixture, selected = f.uncProjects.find((row) => row.name === config.to);
          f.update({ ...f.dropdownBusy, projects: f.uncProjects, scan_busy: false, scan_revision: 21,
            project_id: selected.name, project_uid: selected.project_uid, project_cache_uid: `cache-${selected.name}` });
          f.dropdownSnap('final-immediate'); await f.dropdownFrames('final');
        }, config);
        const timeline = await page.evaluate(() => fixture.dropdownTimeline);
        const name = `dropdown-${config.name}-${compact ? 'compact' : 'expanded'}`;
        const failedSamples = checkDropdown(name, timeline, expectedPath, config.to);
        evidence.cases.push({ case: name, compact, config, busy, timeline, failed_samples: failedSamples });
      }

      // Repeated changes on one retained select cover dirty option state that
      // cannot be reproduced by remounting a clean fixture for every selection.
      await page.evaluate((compact) => fixture.uncMount('', compact), compact);
      const roundtrips = [];
      for (const [index, name] of ['Dinoster5', 'superwings12', 'Dinoster5', 'superwings12'].entries()) {
        const expectedPath = `//192.168.200.19/v/projects/Ai_Ct_image/${name}`;
        await page.selectOption('#widget [data-project-select]', expectedPath);
        await page.evaluate(async () => { fixture.dropdownTimeline = []; fixture.dropdownSnap('selected-immediate'); await fixture.dropdownFrames('selected'); });
        await page.waitForFunction((count) => fixture.writes.length > count, index);
        await page.evaluate(async ({ index, name }) => {
          const f = fixture, entry = f.writes[index], selected = f.uncProjects.find((row) => row.name === name);
          f.update({ ...entry.state, scan_busy: true }); f.dropdownSnap('busy-immediate'); await f.dropdownFrames('busy');
          entry.resolve(); await Promise.resolve(); f.dropdownSnap('transport-ack');
          f.update({ ...entry.state, scan_busy: false, scan_revision: 21 + index, project_id: name,
            project_uid: selected.project_uid, project_cache_uid: `cache-${name}` });
          f.dropdownSnap('final-immediate'); await f.dropdownFrames('final');
        }, { index, name });
        const timeline = await page.evaluate(() => fixture.dropdownTimeline);
        checkDropdown(`dropdown-roundtrip-${index}-${compact}`, timeline, expectedPath, name);
        roundtrips.push({ name, timeline });
      }
      evidence.cases.push({ case: 'dropdown-dirty-selectedness-roundtrips', compact, roundtrips });
    }
    await page.evaluate(() => fixture.uncMount('superwings12', false));
    await page.selectOption('#widget [data-project-select]', '//192.168.200.19/v/projects/Ai_Ct_image/Dinoster5');
    await page.waitForFunction(() => fixture.writes.length > 0);
    const rollback = await page.evaluate(async () => {
      fixture.writes[0].reject(new Error('UNC selection transport failed'));
      await Promise.resolve(); await Promise.resolve();
      fixture.dropdownSnap('rollback-immediate'); await fixture.dropdownFrames('rollback');
      return fixture.dropdownTimeline;
    });
    checkDropdown('dropdown-transport-rollback', rollback, '//192.168.200.19/v/projects/Ai_Ct_image/superwings12', 'superwings12');
    evidence.cases.push({ case: 'dropdown-transport-rollback', timeline: rollback });
    const cleared = await page.evaluate(() => {
      fixture.update({ ...fixture.container.__hmbImageAssetLatestState, project_root: '', project_id: '',
        project_uid: '', project_cache_uid: '', scan_busy: false, scan_revision: 99 });
      return fixture.dropdownSnap('authoritative-empty-clear');
    });
    assert.equal(cleared.project_root, '');
    assert.equal(cleared.select_value, '', 'An authoritative cleared project must retain its placeholder.');
    evidence.cases.push({ case: 'dropdown-authoritative-empty-clear', view: cleared });

    // Generated catalogs represent the real native ACK/cache-completion
    // contract without archiving any user's media or project state. An optional
    // ignored native receipt allows the exact SDK payloads to be replayed too.
    const nativeTemporalPath = option('--native-temporal-report');
    const nativeRows = nativeTemporalPath
      ? JSON.parse(fs.readFileSync(nativeTemporalPath, 'utf8').replace(/^\uFEFF/, '')).cases
      : await page.evaluate(() => {
        const f = fixture, pixel = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j14sAAAAASUVORK5CYII=';
        let before = { ...f.base, catalog_root: '//192.168.200.19/v/projects/Ai_Ct_image', projects: f.uncProjects,
          project_root: '', project_id: '', project_uid: '', project_cache_uid: '', assets: [],
          scan_revision: 0, ui_edit_revision: 0, scan_busy: false };
        return ['Dinoster5', 'Katuri8', 'Dinoster5'].map((name, index) => {
          const selected = f.uncProjects.find((row) => row.name === name);
          const ack = { ...before, project_root: selected.path, project_id: '', project_uid: '', project_cache_uid: '',
            scan_busy: true, ui_edit_revision: index + 1, assets: [] };
          const final = { ...ack, scan_revision: ack.scan_revision + 1, scan_busy: false, project_id: name,
            project_uid: `verified-${name}`, project_cache_uid: `verified-cache-${name}`,
            assets: Array.from({ length: 12 }, (_, assetIndex) => ({ asset_library_id: `${name}-${assetIndex}`,
              source_uid: `project:${name}-${assetIndex}`, source_kind: 'project', registered: true,
              asset_id: `Hero${assetIndex}`, image_name: `Hero${assetIndex}`, path: `${selected.path}/Hero${assetIndex}.png`,
              relative_path: `Hero${assetIndex}.png`, thumbnail_url: pixel })) };
          const result = { label: ['first-selection', 'A-to-B', 'B-to-A'][index], before, ack, final };
          before = final;
          return result;
        });
      });
    assert.equal(nativeRows.length, 3, 'The native temporal fixture must cover first selection and both directions.');
    if (nativeTemporalPath) evidence.native_temporal_input = {
      path: nativeTemporalPath, sha256: sha(fs.readFileSync(nativeTemporalPath)),
      scope: 'Private generated SDK catalogs; delivery intentionally crossed final then old ACK in the isolated browser',
    };
    for (const native of nativeRows) {
      await page.evaluate((state) => {
        fixture.mount(state); fixture.dropdownTimeline = [];
        fixture.temporalRoot = fixture.container.querySelector('.hmb-image-assets');
        fixture.temporalSnap = (stage) => ({ ...fixture.dropdownSnap(stage),
          canonical_asset_count: fixture.container.__hmbImageAssetLatestState.assets.length,
          grid_card_count: fixture.container.querySelectorAll('.asset-card').length,
          mount_token: fixture.container.__hmbImageAssetMountToken,
          root_retained: fixture.temporalRoot === fixture.container.querySelector('.hmb-image-assets') });
      }, native.before);
      await page.selectOption('#widget [data-project-select]', native.final.project_root);
      const timeline = await page.evaluate(async (native) => {
        const f = fixture, views = [];
        for (const [stage, state] of [['worker-final', native.final], ['late-native-ack', native.ack], ['recovery-final', native.final]]) {
          f.update(state); views.push(f.temporalSnap(`${stage}-immediate`));
          for (let frame = 0; frame < 3; frame++) await new Promise((resolve) => requestAnimationFrame(() => {
            views.push(f.temporalSnap(`${stage}-raf-${frame}`)); resolve();
          }));
        }
        return views;
      }, native);
      const caseName = `cached-completion-before-old-ack-${native.label}`;
      const failedViews = timeline.filter((view) => view.canonical_asset_count !== native.final.assets.length
        || view.grid_card_count !== native.final.assets.length || !view.root_retained);
      if (failedViews.length) dropdownFailures.push({ case: caseName, failures: failedViews });
      if (!(native.final.scan_revision > native.ack.scan_revision)) dropdownFailures.push({
        case: `${caseName}-completion-clock`, failures: [{ ack_scan_revision: native.ack.scan_revision, final_scan_revision: native.final.scan_revision }],
      });
      checkDropdown(caseName, timeline, native.final.project_root, native.final.project_id);
      assert.equal(new Set(timeline.map((view) => view.mount_token)).size, 1, 'Late ACK must not replace the widget mount.');
      evidence.cases.push({ case: caseName, timeline, completion_clock_advanced: native.final.scan_revision > native.ack.scan_revision });
    }

    const prepaintConfigs = [
      { name: 'first-catalog-update-latest-callback', from: '', kind: 'catalog-update', expected: 'Dinoster5' },
      { name: 'first-empty-transient-catalog', from: '', kind: 'transient-empty', expected: 'Dinoster5' },
      { name: 'existing-project-update-and-rollback', from: 'superwings12', kind: 'catalog-update', expected: 'Dinoster5', rollback: true },
      { name: 'authoritative-target-removal', from: '', kind: 'target-removal', expected: '' },
      { name: 'authoritative-empty-catalog', from: '', kind: 'empty-authority', expected: '' },
      { name: 'authoritative-project-clear', from: 'superwings12', kind: 'clear', expected: '' },
      { name: 'newer-project-authority', from: '', kind: 'new-project', expected: 'Katuri8' },
      { name: 'runtime-owner-replacement', from: 'superwings12', kind: 'owner', expected: 'superwings12' },
      { name: 'authoritative-catalog-replacement', from: 'superwings12', kind: 'new-catalog', expected: 'NewProject' },
    ];
    for (const compact of [false, true]) {
      for (const config of prepaintConfigs) {
        await page.evaluate(({ config, compact }) => {
          const f = fixture; f.uncMount(config.from, compact);
          f.prepaintBase = JSON.parse(JSON.stringify(f.container.__hmbImageAssetLatestState));
          f.prepaintPublishedBeforeEcho = null;
          f.prepaintHandler = (event) => {
            if (!event.target.matches('#widget [data-project-select]')) return;
            f.dropdownSnap('change-before-canonical-echo');
            f.prepaintPublishedBeforeEcho = f.writes.some((row) => row.state.project_root === f.uncProjects[0].path);
            const old = JSON.parse(JSON.stringify(f.prepaintBase)); old.projects.reverse(); old.manifest_signature = 'latest-before-paint';
            if (config.kind === 'transient-empty') old.projects = [];
            if (config.kind === 'target-removal') { old.projects = old.projects.filter((row) => row.name !== 'Dinoster5'); old.scan_revision += 1; }
            if (config.kind === 'empty-authority') { old.projects = []; old.scan_revision += 1; }
            if (config.kind === 'clear') Object.assign(old, { project_root: '', project_id: '', project_uid: '', project_cache_uid: '', scan_revision: old.scan_revision + 1 });
            if (config.kind === 'new-project') Object.assign(old, { project_root: f.uncProjects[1].path, project_id: 'Katuri8', project_uid: 'new-owner-project', scan_revision: old.scan_revision + 1 });
            if (config.kind === 'owner') old.shot_routing = { ...old.shot_routing, publisher_instance_uuid: '10000000-0000-4000-8000-000000000001' };
            if (config.kind === 'new-catalog') Object.assign(old, { catalog_root: 'D:/DifferentCatalog',
              project_root: 'D:/DifferentCatalog/NewProject', project_id: 'NewProject', project_uid: 'different-project',
              projects: [{ path: 'D:/DifferentCatalog/NewProject', name: 'NewProject', project_id: 'NewProject' }],
              scan_revision: old.scan_revision + 1 });
            f.controller.update({ value: JSON.stringify(old), onChange: (value) => {
              const promise = f.onChange(value); f.writes.at(-1).callback_owner = 'latest'; return promise;
            } });
            f.dropdownSnap('canonical-echo-before-paint');
          };
          document.addEventListener('change', f.prepaintHandler);
        }, { config, compact });
        await page.selectOption('#widget [data-project-select]', '//192.168.200.19/v/projects/Ai_Ct_image/Dinoster5');
        const outcome = await page.evaluate(async () => {
          const f = fixture; await f.dropdownFrames('deferred-paint'); await new Promise((resolve) => setTimeout(resolve, 30));
          f.dropdownSnap('after-deferred-command'); document.removeEventListener('change', f.prepaintHandler);
          return { timeline: f.dropdownTimeline, emitted_before_first_paint: f.prepaintPublishedBeforeEcho,
            selection_writes: f.writes.filter((row) => row.state.project_root === f.uncProjects[0].path).map((row) => ({
              callback_owner: row.callback_owner, project_root: row.state.project_root, manifest_signature: row.state.manifest_signature,
              catalog_paths: row.state.projects.map((project) => project.path),
              project_id: row.state.project_id, project_uid: row.state.project_uid, project_cache_uid: row.state.project_cache_uid })),
            busy: f.container.__hmbImageAssetBusy, pending_action: Boolean(f.container.__hmbImageAssetPendingSlowAction) };
        });
        const caseName = `prepaint-${config.name}-${compact ? 'compact' : 'expanded'}`;
        evidence.active_case = { case: caseName, compact, config, ...outcome };
        assert.equal(outcome.emitted_before_first_paint, false, 'Project publication must remain deferred until after the first paint.');
        if (config.expected === 'Dinoster5') {
          if (outcome.selection_writes.length !== 1) dropdownFailures.push({ case: caseName, failures: [outcome] });
          checkDropdown(caseName, outcome.timeline, '//192.168.200.19/v/projects/Ai_Ct_image/Dinoster5', 'Dinoster5');
          if (outcome.selection_writes.length) {
            assert.equal(outcome.selection_writes[0].callback_owner, 'latest');
            assert.equal(outcome.selection_writes[0].manifest_signature, 'latest-before-paint', 'The deferred command must rebase onto the latest canonical metadata.');
            assert.ok(outcome.selection_writes[0].catalog_paths.some((value) => pathIdentity(value) === pathIdentity(outcome.selection_writes[0].project_root)),
              'A same-clock partial catalog echo cannot erase the verified target from the backend command.');
            assert.deepEqual([outcome.selection_writes[0].project_id, outcome.selection_writes[0].project_uid, outcome.selection_writes[0].project_cache_uid], ['', '', '']);
          }
          assert.equal(outcome.busy, true, 'An old non-busy prop cannot end the pending action.');
          if (config.rollback && outcome.selection_writes.length) {
            const restored = await page.evaluate(async () => {
              fixture.writes.find((row) => row.state.project_root === fixture.uncProjects[0].path).reject(new Error('deferred project rejected'));
              await Promise.resolve(); await Promise.resolve();
              return { view: fixture.snap(), manifest_signature: fixture.container.__hmbImageAssetLatestState.manifest_signature };
            });
            assert.equal(restored.view.select_label, config.from);
            assert.equal(restored.manifest_signature, 'latest-before-paint', 'Rollback cannot discard the canonical update received before publication.');
            assert.equal(restored.view.busy, false);
            outcome.rollback = restored;
          }
        } else {
          assert.equal(outcome.selection_writes.length, 0, 'New authority/owner or target deletion must cancel the unpublished command.');
          assert.equal(outcome.timeline.at(-1).select_label, config.expected || '프로젝트 선택');
          assert.equal(outcome.busy, false);
        }
        evidence.cases.push({ case: caseName, compact, config, ...outcome });
        delete evidence.active_case;
      }
    }

    await page.evaluate(() => {
      fixture.uncMount('', false);
      fixture.prepaintHandler = (event) => {
        if (event.target.matches('#widget [data-project-select]')) fixture.controller.cleanup();
      };
      document.addEventListener('change', fixture.prepaintHandler);
    });
    await page.selectOption('#widget [data-project-select]', '//192.168.200.19/v/projects/Ai_Ct_image/Dinoster5');
    const queuedCleanup = await page.evaluate(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50)); document.removeEventListener('change', fixture.prepaintHandler);
      return { writes: fixture.writes.length, dom_children: fixture.container.children.length,
        pending_action: Boolean(fixture.container.__hmbImageAssetPendingSlowAction) };
    });
    assert.deepEqual(queuedCleanup, { writes: 0, dom_children: 0, pending_action: false });
    evidence.cases.push({ case: 'prepaint-cleanup-cancels-unpublished-action', ...queuedCleanup });
    await page.evaluate(() => {
      fixture.uncMount('', false); fixture.retiringMountToken = fixture.container.__hmbImageAssetMountToken;
      fixture.prepaintHandler = (event) => {
        if (event.target.matches('#widget [data-project-select]')) fixture.uncMount('Katuri8', false);
      };
      document.addEventListener('change', fixture.prepaintHandler);
    });
    await page.selectOption('#widget [data-project-select]', '//192.168.200.19/v/projects/Ai_Ct_image/Dinoster5');
    const queuedReplacement = await page.evaluate(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50)); document.removeEventListener('change', fixture.prepaintHandler);
      return { writes: fixture.writes.length, select_label: fixture.snap().select_label,
        mount_replaced: fixture.retiringMountToken !== fixture.container.__hmbImageAssetMountToken,
        pending_action: Boolean(fixture.container.__hmbImageAssetPendingSlowAction) };
    });
    assert.deepEqual(queuedReplacement, { writes: 0, select_label: 'Katuri8', mount_replaced: true, pending_action: false });
    evidence.cases.push({ case: 'prepaint-replacement-cancels-retired-mount-action', ...queuedReplacement });
    evidence.dropdown_failures = dropdownFailures;
    assert.deepEqual(errors, []);
    evidence.page_errors = errors;
    evidence.source_sha256_after = sha(fs.readFileSync(sourcePath));
    assert.equal(evidence.source_sha256_after, evidence.source_sha256_before, 'Browser validation must not mutate runtime source.');
    evidence.result = dropdownFailures.length ? 'FAIL' : 'PASS';
    if (evidenceDir) fs.writeFileSync(path.join(evidenceDir, 'project-label-regression-receipt.json'), JSON.stringify(evidence, null, 2));
    assert.equal(dropdownFailures.length, 0,
      `Dropdown continuity failures: ${dropdownFailures.map((row) => row.case).join(', ')}. Full frame evidence is saved in the receipt.`);
    console.log(`ImageAsset project label Chrome: PASS (${evidence.cases.length} full mount cases; page.selectOption, dirty roundtrips, catalog morphs, expanded/compact, ACK, rollback, authoritative clear)`);
    await page.evaluate(() => fixture.controller.cleanup());
  } catch (error) {
    evidence.result = 'FAIL';
    evidence.failure_summary = String(error.message || error);
    evidence.page_errors = errors;
    evidence.source_sha256_after = sha(fs.readFileSync(sourcePath));
    if (evidenceDir) fs.writeFileSync(path.join(evidenceDir, 'project-label-regression-receipt.json'), JSON.stringify(evidence, null, 2));
    throw error;
  } finally {
    await browser.close();
  }
}
