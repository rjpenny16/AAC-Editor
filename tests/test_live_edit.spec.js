const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const path = require('path');

const BASE_URL = process.env.TDSNAP_WEB_URL || 'http://localhost:8765';
const CAPTURE_DIR = process.env.AAC_CAPTURE_UX_DIR;

async function capture(page, filename) {
  if (CAPTURE_DIR) await page.screenshot({ path: path.join(CAPTURE_DIR, filename), fullPage: true });
}

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function defaultStatus(overrides = {}) {
  return {
    ok: true,
    available: true,
    running: true,
    unlocked: true,
    page: 'Eating',
    grid: { cols: 3, rows: 2 },
    pages: ['Eating', 'Topics Menu Page', 'Games'],
    ...overrides,
  };
}

function defaultLayout(pageName = 'Eating', overrides = {}) {
  return {
    ok: true,
    page: pageName,
    grid: { cols: 3, rows: 2 },
    buttons: [],
    free_slots: [0, 1, 2, 3, 4, 5],
    fingerprint: pageName.toLowerCase().replaceAll(' ', '-') + '-v1',
    ...overrides,
  };
}

async function mockTD(page, options = {}) {
  const status = options.status || defaultStatus();
  const layout = options.layout;
  await page.route('**/api/tdsnap/status', (route) => {
    const value = typeof status === 'function' ? status(route) : status;
    return fulfillJson(route, value);
  });
  await page.route('**/api/tdsnap/page-layout*', async (route) => {
    const requested = new URL(route.request().url()).searchParams.get('page');
    const value = typeof layout === 'function'
      ? await layout(requested, route)
      : layout || defaultLayout(requested || status.page || 'Eating');
    if (value == null) return;
    return fulfillJson(route, value);
  });
}

/* Settings are backed by a real per-machine file, so tests mock the endpoint
   rather than hitting it — the same store persisting across page.goto calls
   in one test lets a test simulate "the next launch" without a real restart. */
async function mockSettings(page, initial = {}) {
  const store = {
    preferences: initial.preferences || {},
    draft: initial.draft || null,
    templates: initial.templates || [],
  };
  await page.route('**/api/settings', (route) => {
    const method = route.request().method();
    if (method === 'GET') return fulfillJson(route, { ok: true, ...store });
    if (method === 'PUT') {
      const body = route.request().postDataJSON() || {};
      store.preferences = body.preferences || {};
      store.draft = body.draft || null;
      // Mirrors the server: an absent key leaves saved templates alone, so the
      // draft autosave cannot wipe them.
      if ('templates' in body) store.templates = body.templates || [];
      return fulfillJson(route, { ok: true });
    }
    if (method === 'DELETE') {
      store.preferences = {};
      store.draft = null;
      store.templates = [];
      return fulfillJson(route, { ok: true });
    }
    return route.continue();
  });
  return store;
}

async function openEditor(page) {
  await page.goto(BASE_URL);
  await expect(page.locator('#step-load')).toBeVisible();
  await expect(page.locator('#wizard-progress-label')).toHaveText('Setup');
}

async function connect(page) {
  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#wizard-items')).toBeVisible();
  await expect(page.locator('#items-heading')).toBeFocused();
}

async function existingItems(page) {
  await connect(page);
  await expect(page.locator('#wizard-progress-label')).toHaveText('Add');
}

async function newItems(page, title = 'Snacks') {
  await connect(page);
  await page.locator('#create-page-btn').click();
  await expect(page.locator('#wizard-title')).toBeVisible();
  await page.locator('#title-input').fill(title);
  await page.locator('#wizard-title .wizard-next').click();
  await expect(page.locator('#wizard-destination')).toBeVisible();
  await page.locator('#wizard-destination .wizard-next').click();
  await expect(page.locator('#wizard-items')).toBeVisible();
}

async function blockingViolations(page) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations
    .filter((violation) => ['serious', 'critical'].includes(violation.impact))
    .map(({ id, impact, help, nodes }) => ({ id, impact, help, targets: nodes.map((n) => n.target) }));
}

// Settings are backed by a real file on the machine running the suite, and
// the webServer above is one long-lived process for the whole file — without
// this, one test's autosaved draft would leak into every test after it. Every
// test gets an empty, isolated mock by default; tests that exercise settings
// specifically call mockSettings(page, {...}) again to override it, and the
// most recently registered route wins.
test.beforeEach(async ({ page }) => {
  await mockSettings(page);
});

// Only the connect screen used to be scanned, which left the screens where the
// real work happens — and the modal with the destructive button — unchecked.
test.describe('accessibility past the first screen', () => {
  test('the word list and its chip editor are clean', async ({ page }) => {
    await mockTD(page);
    await existingItems(page);
    await page.locator('#word-input').fill('apple');
    await page.locator('#word-add-btn').click();
    expect(await blockingViolations(page)).toEqual([]);

    await page.locator('#chipbox .chip').first().click();
    await expect(page.locator('#chip-editor')).toBeVisible();
    expect(await blockingViolations(page)).toEqual([]);
  });

  test('the placement editor is clean', async ({ page }) => {
    await mockTD(page);
    await existingItems(page);
    await page.locator('#word-input').fill('apple');
    await page.locator('#word-add-btn').click();
    await page.locator('.more-options > summary').click();
    await page.locator('#layout-options-btn').click();
    await expect(page.locator('#wizard-layout')).toBeVisible();
    expect(await blockingViolations(page)).toEqual([]);
  });

  test('the review screen is clean', async ({ page }) => {
    await mockTD(page);
    await existingItems(page);
    await page.locator('#word-input').fill('apple');
    await page.locator('#word-add-btn').click();
    await page.locator('#build-btn').click();
    await expect(page.locator('#step-result')).toBeVisible();
    expect(await blockingViolations(page)).toEqual([]);
  });
});

test.describe('dark theme', () => {
  test.use({ colorScheme: 'dark' });

  test('has no contrast failures', async ({ page }) => {
    // Light sensitivity is common in this user population, therapy rooms are
    // dim, and TD Snap itself ships dark themes.
    await mockTD(page);
    await existingItems(page);
    await page.locator('#word-input').fill('apple');
    await page.locator('#word-add-btn').click();

    const results = await new AxeBuilder({ page }).withTags(['wcag2aa', 'wcag21aa']).analyze();
    const contrast = results.violations.filter((violation) => violation.id === 'color-contrast');
    expect(contrast.map((v) => v.nodes.map((n) => n.failureSummary))).toEqual([]);
  });
});

test('initial wizard has no serious or critical accessibility violations', async ({ page }) => {
  await openEditor(page);
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations
    .filter((violation) => ['serious', 'critical'].includes(violation.impact))
    .map(({ id, impact, help, nodes }) => ({
      id,
      impact,
      help,
      targets: nodes.map((node) => node.target),
    }));
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
});

test('native window hides the browser-only quit control', async ({ page }) => {
  await page.route('**/api/config', (route) => fulfillJson(route, {
    ok: true,
    token: 'native-test-token',
    native: true,
    elevated: false,
  }));
  await page.goto(BASE_URL);
  await expect(page.locator('#quit-btn')).toBeHidden();
});

test('Grid 3 uses the active-grid three-step flow and live styled rectangles', async ({ page }) => {
  let submitted = null;
  let mutationHeaders = null;
  await page.route('**/api/grid3/status', (route) => fulfillJson(route, {
    ok: true,
    available: true,
    installed: true,
    running: true,
    elevated: true,
    needs_elevation: false,
    unlocked: true,
    dirty: false,
    grid_set: 'Super Core 50 copy',
    page: 'Home',
    grid: { cols: 3, rows: 2 },
  }));
  await page.route('**/api/grid3/page-layout', (route) => fulfillJson(route, {
    ok: true,
    supported: true,
    grid_set: 'Super Core 50 copy',
    page: 'Home',
    grid: { cols: 3, rows: 2 },
    background: '#F0F0F0',
    preview_aspect: 1.8,
    fingerprint: 'grid3-home-v1',
    free_slots: [1, 5],
    buttons: [{ slot: 0, label: 'hello', existing: true }],
    cells: [
      { slot: 0, x: 0, y: 0, label: 'hello', safe_blank: false,
        style: { key: 'Core', background: '#FFFFFF', border: '#333333', foreground: '#111111' },
        rect: { left: 0, top: 0, width: .33, height: .5 } },
      { slot: 1, x: 1, y: 0, label: '', safe_blank: true,
        style: { key: 'Verb', background: '#FFF2CC', border: '#AA8800', foreground: '#111111' },
        rect: { left: .34, top: 0, width: .32, height: .5 } },
      { slot: 2, x: 2, y: 0, label: '', safe_blank: false,
        style: { key: 'Workspace', background: '#DDDDDD', border: '#555555', foreground: '#111111' },
        rect: { left: .67, top: 0, width: .33, height: 1 } },
      { slot: 5, x: 2, y: 1, label: '', safe_blank: true,
        style: { key: 'Other', background: '#DDEEFF', border: '#225588', foreground: '#111111' },
        rect: { left: .34, top: .51, width: .32, height: .49 } },
    ],
  }));
  await page.route('**/api/grid3/probe', (route) => fulfillJson(route, {
    ok: true,
    supported: true,
    checks: { edit_mode: 'pass', undo_without_save: 'pass' },
  }));
  await page.route('**/api/grid3/edit-plan', (route) => {
    submitted = route.request().postDataJSON();
    mutationHeaders = route.request().headers();
    return fulfillJson(route, {
      ok: true,
      page: 'Home',
      grid_set: 'Super Core 50 copy',
      buttons: 2,
      warnings: [],
      checks: {
        grid3_edit: 'pass', target_grid: 'pass', content: 'pass',
        positions: 'pass', style_preserved: 'pass', save_completed: 'pass',
      },
    });
  });

  await page.goto(BASE_URL);
  await page.locator('#provider-grid3').click();
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#wizard-items')).toBeVisible();
  await expect(page.locator('#wizard-progress-label')).toHaveText('Add');
  await expect(page.locator('#layout-options-btn')).toBeHidden();
  await expect(page.locator('#capacity')).toHaveText('2 spaces available');
  await page.locator('#word-input').fill('Help');
  await page.locator('#word-add-btn').click();
  await page.locator('#word-input').fill('More');
  await page.locator('#word-add-btn').click();
  await capture(page, 'after-grid3-add-words.png');
  await page.locator('#build-btn').click();
  await expect(page.locator('#result-heading')).toHaveText('Check positions before adding');
  await expect(page.locator('#review-action')).toHaveText('Add 2 buttons to Home');
  await expect(page.locator('#review-preview .cell.used')).toHaveCount(2);
  await expect(page.locator('#confirm-update-label')).toHaveText('Add 2 buttons to Home');
  await page.setViewportSize({ width: 390, height: 760 });
  await page.locator('#adjust-placement-btn').click();
  await expect(page.locator('#preview')).toHaveClass(/grid3-preview/);
  await expect(page.locator('#preview .cell.used')).toHaveCount(2);
  await expect(page.locator('#preview .cell.used').first()).toHaveCSS('background-color', 'rgb(255, 242, 204)');
  await expect(page.locator('#placement-order-wrap')).toBeVisible();
  const reflow = await page.evaluate(() => {
    const frame = document.querySelector('#wizard-placement .preview-frame');
    const preview = document.querySelector('#preview');
    return {
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      previewWidth: preview.getBoundingClientRect().width,
      frameWidth: frame.getBoundingClientRect().width,
    };
  });
  expect(reflow.documentWidth).toBeLessThanOrEqual(reflow.viewportWidth);
  expect(reflow.previewWidth).toBeLessThanOrEqual(reflow.frameWidth);
  await capture(page, 'after-grid3-placement-390.png');
  await page.getByRole('button', { name: 'Move later: Help' }).click();
  await page.locator('#placement-back-btn').click();
  await page.locator('#confirm-update-btn').click();

  await expect(page.locator('#result-heading')).toHaveText('Done — Grid 3 was updated');
  expect(submitted.fingerprint).toBe('grid3-home-v1');
  expect(submitted.items.map((item) => item.slot)).toEqual([5, 1]);
  expect(mutationHeaders['x-aac-editor']).toBe('grid3');
  expect(mutationHeaders['x-tdsnap-token']).toBeTruthy();
});

test('connect opens TD Snap when it is not already running', async ({ page }) => {
  let checks = 0;
  let launches = 0;
  let releaseFirstStatus;
  const firstStatusGate = new Promise((resolve) => { releaseFirstStatus = resolve; });
  await page.route('**/api/tdsnap/status', async (route) => {
    checks += 1;
    if (checks === 1) await firstStatusGate;
    return fulfillJson(route, checks === 1
      ? { ok: true, available: true, running: false, unlocked: true }
      : defaultStatus({ page: 'Topics Menu Page', pages: ['Topics Menu Page'] }));
  });
  await page.route('**/api/tdsnap/launch', (route) => {
    launches += 1;
    return fulfillJson(route, { ok: true, launched: true });
  });
  await page.route('**/api/tdsnap/page-layout*', (route) =>
    fulfillJson(route, defaultLayout('Topics Menu Page')));

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#app-activity')).toContainText('Checking for TD Snap');
  await expect(page.locator('#live-connect-btn')).toHaveAttribute('aria-busy', 'true');
  releaseFirstStatus();
  await expect(page.locator('#wizard-items')).toBeVisible();
  await expect(page.locator('#app-activity')).toBeHidden();
  await expect(page.locator('#live-connect-btn')).toHaveAttribute('aria-busy', 'false');
  expect(launches).toBe(1);
});

test('open-page path goes straight to Add and edits only after confirmation', async ({ page }) => {
  let submitted = null;
  let editCalls = 0;
  await mockTD(page, {
    status: defaultStatus({ pages: ['Eating', 'Places'] }),
    layout: defaultLayout('Eating', {
      buttons: [{ slot: 0, label: 'Apple' }],
      free_slots: [1, 2, 3, 4, 5],
      fingerprint: 'eating-v1',
    }),
  });
  await page.route('**/api/tdsnap/edit-plan', (route) => {
    editCalls += 1;
    submitted = route.request().postDataJSON();
    return fulfillJson(route, {
      ok: true,
      page: 'Eating',
      buttons: 2,
      warnings: [],
      checks: {
        td_snap_edit: 'pass',
        target_page: 'pass',
        content: 'pass',
        positions: 'pass',
      },
    });
  });

  await connect(page);
  await expect(page.locator('#wizard-progress-label')).toHaveText('Add');
  await expect(page.locator('#parent-select')).toHaveValue('Eating');
  await expect(page.locator('#current-page-label')).toHaveText('Adding to Eating');
  await expect(page.locator('#file-badge')).toHaveText('TD Snap · Change app');
  await expect(page.locator('#file-badge')).toHaveAttribute(
    'aria-label', 'Change app (currently TD Snap)',
  );
  await page.locator('#choose-page-btn').click();
  await expect(page.locator('#wizard-destination')).toBeVisible();
  await expect(page.locator('#parent-select')).toHaveValue('Eating');
  await page.locator('#wizard-destination .wizard-next').click();
  await expect(page.locator('#wizard-progress-label')).toHaveText('Add');
  await page.locator('#word-input').fill('Help');
  await page.locator('#word-add-btn').click();
  await page.locator('#word-input').fill('More');
  await page.locator('#word-input').press('Enter');
  await capture(page, 'after-add-words.png');
  await page.locator('#build-btn').click();

  await expect(page.locator('#wizard-progress-label')).toHaveText('Review');
  await expect(page.locator('#review-action')).toHaveText('Add 2 buttons to Eating');
  await expect(page.locator('#review-target')).toHaveText('Eating');
  await expect(page.locator('#review-items li')).toHaveCount(2);
  await expect(page.locator('#review-preview .cell.used')).toHaveCount(2);
  await expect(page.locator('#confirm-update-label')).toHaveText('Add 2 buttons to Eating');
  await capture(page, 'after-review-placement.png');
  expect(editCalls).toBe(0);

  await page.locator('#review-back-btn').click();
  await expect(page.locator('#chipbox .chip')).toHaveCount(2);
  await page.locator('#build-btn').click();
  await page.locator('#adjust-placement-btn').click();
  await expect(page.locator('#wizard-progress-label')).toHaveText('Review');
  const help = page.locator('#preview .cell.used').filter({ hasText: 'Help' });
  await help.press('ArrowRight');
  await page.locator('#placement-back-btn').click();
  await expect(page.locator('#review-placement')).toHaveText('The positions you chose');
  expect(editCalls).toBe(0);

  await page.locator('#confirm-update-btn').click();
  await expect(page.locator('#result-heading')).toHaveText('Done — TD Snap was updated');
  await capture(page, 'after-completion.png');
  expect(editCalls).toBe(1);
  expect(submitted).toMatchObject({
    operation: 'add_to_existing_page',
    page: 'Eating',
    fingerprint: 'eating-v1',
  });
  expect(submitted.items.map((item) => item.label)).toEqual(['Help', 'More']);
});

test('new-page secondary path validates the name and retains it', async ({ page }) => {
  let submitted = null;
  await mockTD(page, {
    status: defaultStatus({
      page: 'Topics Menu Page',
      grid: { cols: 5, rows: 5 },
      pages: ['Topics Menu Page', 'Eating', 'Games'],
    }),
    layout: defaultLayout('Topics Menu Page', {
      grid: { cols: 5, rows: 5 },
      free_slots: Array.from({ length: 25 }, (_, index) => index),
      fingerprint: 'topics-v1',
    }),
  });
  await page.route('**/api/tdsnap/page', (route) => {
    submitted = route.request().postDataJSON();
    return fulfillJson(route, {
      ok: true,
      page: 'Snacks',
      parent: 'Eating',
      buttons: 2,
      warnings: [],
      checks: {
        td_snap_edit: 'pass',
        navigation: 'pass',
        content: 'pass',
        symbols: 'pass',
      },
    });
  });

  await connect(page);
  await page.locator('#create-page-btn').click();
  await page.locator('#wizard-title .wizard-next').click();
  await expect(page.locator('#title-error')).toHaveText('Enter a name for the new page.');
  await expect(page.locator('#title-error')).toBeFocused();

  await page.locator('#title-input').fill('Snacks');
  await page.locator('#wizard-title .wizard-next').click();
  await expect(page.locator('#wizard-progress-label')).toHaveText('Setup');
  await expect(page.locator('#placement-title')).toContainText('Eating');
  await expect(page.locator('#placement-copy')).toContainText(
    'The new Snacks button will be added to Eating.',
  );
  await expect(page.locator('#parent-select')).toHaveValue('Eating');
  await page.locator('#wizard-destination .wizard-back').click();
  await expect(page.locator('#title-input')).toHaveValue('Snacks');
  await page.locator('#wizard-title .wizard-next').click();
  await page.locator('#wizard-destination .wizard-next').click();

  await page.locator('#word-input').fill('More please');
  await page.locator('#word-add-btn').click();
  await page.locator('#word-input').fill('No thanks');
  await page.locator('#word-add-btn').click();
  await page.locator('#build-btn').click();
  await expect(page.locator('#result-heading')).toHaveText('Check positions before adding');
  await expect(page.locator('#review-target')).toHaveText('Snacks, found from Eating');
  await expect(page.locator('#confirm-update-label')).toHaveText('Create Snacks with 2 buttons');
  expect(submitted).toBeNull();
  await page.locator('#confirm-update-btn').click();

  expect(submitted.parent).toBe('Eating');
  expect(submitted.title).toBe('Snacks');
  expect(submitted.operation).toBe('create_page');
  expect(submitted.items.map((item) => item.label)).toEqual(['More please', 'No thanks']);
});

test('new-page flow checks that the selected parent has room', async ({ page }) => {
  await mockTD(page, {
    status: defaultStatus({ pages: ['Eating', 'Full'] }),
    layout: (requested) => requested === 'Full'
      ? defaultLayout('Full', {
        buttons: [{ slot: 0, label: 'A' }, { slot: 1, label: 'B' }],
        free_slots: [],
      })
      : defaultLayout(requested || 'Eating'),
  });

  await connect(page);
  await page.locator('#create-page-btn').click();
  await page.locator('#title-input').fill('New Page');
  await page.locator('#wizard-title .wizard-next').click();
  await page.locator('#parent-select').selectOption('Full');
  await expect(page.locator('#parent-capacity')).toContainText('full');
  await page.locator('#wizard-destination .wizard-next').click();
  await expect(page.locator('#destination-error')).toContainText('full');
  await expect(page.locator('#wizard-destination')).toBeVisible();
});

test('new-page flow rejects a title that already exists', async ({ page }) => {
  await mockTD(page, {
    status: defaultStatus({ pages: ['Eating', 'Existing'] }),
  });
  await connect(page);
  await page.locator('#create-page-btn').click();
  await page.locator('#title-input').fill(' existing ');
  await page.locator('#wizard-title .wizard-next').click();
  await expect(page.locator('#title-error')).toContainText('already exists');
  await expect(page.locator('#wizard-title')).toBeVisible();
});

test('exported TD Snap file can create and save an edited copy', async ({ page }) => {
  let submitted = null;
  await page.route('**/api/pageset', (route) => fulfillJson(route, {
    ok: true,
    session_id: 'file-session',
    filename: 'sample.sps',
    schema_version: '4.13',
    grid: { cols: 3, rows: 2 },
    pages: [{ id: 1, title: 'Home' }],
    baseline_problems: [],
  }));
  await page.route('**/api/pageset/file-session/page/1/capacity', (route) =>
    fulfillJson(route, { ok: true, free_cells: 2 }));
  await page.route('**/api/pageset/file-session/page', async (route) => {
    submitted = route.request().postDataJSON();
    return fulfillJson(route, {
      ok: true,
      buttons: submitted.items.length,
      edits: 1,
      checks: {
        sqlite_integrity: 'pass', linkage_chains: 'pass', roundtrip_diff: 'pass',
      },
    });
  });
  await page.route('**/api/pageset/file-session/pages', (route) => fulfillJson(route, {
    ok: true, pages: [{ id: 1, title: 'Home' }, { id: 2, title: 'Snacks' }],
  }));

  await openEditor(page);
  await page.locator('#provider-file').click();
  await page.locator('#file-input').setInputFiles({
    name: 'sample.sps',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('synthetic pageset'),
  });
  // An exported file now asks the same first question as a live connection,
  // because it can add to an existing page as well as create one.
  await expect(page.locator('#wizard-operation')).toBeVisible();
  await page.locator('#operation-new').click();
  await page.locator('#wizard-operation .wizard-next').click();
  await expect(page.locator('#wizard-title')).toBeVisible();
  await page.locator('#title-input').fill('Snacks');
  await page.locator('#wizard-title .wizard-next').click();
  await expect(page.locator('#parent-capacity')).toContainText('2 empty spaces');
  await page.locator('#wizard-destination .wizard-next').click();
  await page.locator('#word-input').fill('Chips, Apple');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await page.locator('#confirm-update-btn').click();

  await expect(page.locator('#result-heading')).toHaveText('Done — TD Snap was updated');
  await expect(page.locator('#file-save-btn')).toBeVisible();
  await expect(page.locator('#file-save-btn')).toHaveAttribute(
    'href', '/api/pageset/file-session/download',
  );
  expect(submitted).toMatchObject({ title: 'Snacks', parent_page_id: 1 });
  expect(submitted.items.map((item) => item.label)).toEqual(['Chips', 'Apple']);
});

test('words are required on the words-and-phrases question', async ({ page }) => {
  await mockTD(page);
  await existingItems(page);
  await page.locator('#build-btn').click();
  await expect(page.locator('#items-error')).toHaveText(
    'Add at least one word or phrase before continuing.',
  );
  await expect(page.locator('#items-error')).toBeFocused();
  await expect(page.locator('#wizard-items')).toBeVisible();
});

test('locked Windows reports a plain-language connection error', async ({ page }) => {
  let locked = true;
  await page.route('**/api/tdsnap/status', (route) =>
    fulfillJson(route, defaultStatus({ unlocked: !locked })));
  await page.route('**/api/tdsnap/page-layout*', (route) =>
    fulfillJson(route, defaultLayout('Eating')));
  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#connection-error')).toBeVisible();
  await capture(page, 'after-connection-failure.png');
  await expect(page.locator('#connection-error')).toContainText(
    'AAC Editor couldn’t reach TD Snap. Nothing was changed.',
  );
  await expect(page.locator('#connection-retry')).toBeVisible();
  await expect(page.locator('#connection-help-btn')).toBeVisible();
  await page.locator('#connection-help-btn').click();
  await expect(page.locator('#connection-help-details')).toHaveAttribute('open', '');
  await expect(page.locator('#connection-help-details summary')).toBeFocused();
  locked = false;
  await page.locator('#connection-retry').click();
  await expect(page.locator('#wizard-items')).toBeVisible();
  await expect(page.locator('#step-load')).toBeHidden();
});

test('a request that never resolves exits the connection busy state', async ({ page }) => {
  test.setTimeout(20_000);
  await page.route('**/api/tdsnap/status', async () => {
    await new Promise(() => {});
  });
  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#connection-error')).toBeVisible({ timeout: 12_000 });
  await expect(page.locator('#connection-error')).toContainText(
    'AAC Editor couldn’t reach TD Snap. Nothing was changed.',
  );
  await expect(page.locator('#live-connect-btn')).toBeEnabled();
  await expect(page.locator('#live-connect-btn')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('body')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('#app-activity')).toBeHidden();
});

test('a partial create resumes on the created page without duplicate buttons', async ({ page }) => {
  let created = false;
  await mockTD(page, {
    status: () => defaultStatus({
      page: created ? 'World Cup Final' : 'Topics Menu Page',
      grid: { cols: 3, rows: 2 },
      pages: created ? ['Topics Menu Page', 'World Cup Final'] : ['Topics Menu Page'],
    }),
    layout: (requested) => defaultLayout(requested || 'World Cup Final', {
      buttons: requested === 'World Cup Final' ? [{ slot: 0, label: 'Roar' }] : [],
      free_slots: requested === 'World Cup Final' ? [1, 2, 3, 4, 5] : [0, 1, 2, 3, 4, 5],
      fingerprint: requested === 'World Cup Final' ? 'world-cup-v1' : 'topics-v1',
    }),
  });
  await page.route('**/api/tdsnap/page', (route) => {
    created = true;
    return fulfillJson(route, {
      ok: false,
      error: 'TD Snap stopped after creating the page.',
    }, 400);
  });

  await newItems(page, 'World Cup Final');
  await page.locator('#word-input').fill('Roar, Cheer');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await page.locator('#confirm-update-btn').click();

  await expect(page.locator('#wizard-items')).toBeVisible();
  await expect(page.locator('#operation-existing')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#parent-select')).toHaveValue('World Cup Final');
  await expect(page.locator('#chipbox .chip')).toHaveCount(1);
  await expect(page.locator('#chipbox .chip')).toContainText('Cheer');
  await expect(page.locator('#items-error')).toContainText('created the page');
  await expect(page.locator('#items-error')).toContainText('1 button is already there');
  await expect(page.locator('#items-error')).toContainText('1 button remains');
});

test('live monitoring follows an existing TD Snap page and keeps the full list', async ({ page }) => {
  let statusCalls = 0;
  await mockTD(page, {
    status: () => {
      statusCalls += 1;
      const current = statusCalls === 1 ? 'Eating' : 'Games';
      return defaultStatus({
        page: current,
        grid: { cols: 2, rows: 2 },
        pages: ['Eating', 'Games', 'Nested Page', 'Topics Menu Page'],
      });
    },
    layout: (requested) => {
      const current = requested || 'Games';
      return defaultLayout(current, {
        grid: { cols: 2, rows: 2 },
        buttons: [{ slot: 0, label: current === 'Games' ? 'Play' : 'Apple' }],
        free_slots: [1, 2, 3],
        fingerprint: current + '-v1',
      });
    },
  });

  await connect(page);
  await expect(page.locator('#parent-select')).toHaveValue('Games', { timeout: 4000 });
  await expect(page.locator('#preview-live-text')).toContainText('Games');
  await expect(page.locator('#preview .cell.existing')).toContainText('Play');
  await expect(page.locator('#parent-select option')).toHaveCount(4);
});

test('page suggestions are visible while typing', async ({ page }) => {
  await mockTD(page);
  await connect(page);
  await page.locator('#choose-page-btn').click();
  await page.locator('#parent-filter').fill('game');

  await expect(page.locator('#parent-filter')).toBeFocused();
  await expect(page.locator('#parent-select')).toHaveAttribute('size', '2');
  await expect(page.locator('#parent-select option')).toHaveText(['Eating', 'Games']);

  await page.locator('#parent-filter-clear').click();
  await expect(page.locator('#parent-select')).toHaveAttribute('size', '1');
});

test('a new topic page is not changed by live page monitoring', async ({ page }) => {
  let statusCalls = 0;
  await mockTD(page, {
    status: () => {
      statusCalls += 1;
      return defaultStatus({
        page: statusCalls > 1 ? 'Eating' : 'Topics Menu Page',
        grid: statusCalls > 1 ? { cols: 2, rows: 2 } : { cols: 10, rows: 5 },
        pages: ['Topics Menu Page', 'Eating', 'Games'],
      });
    },
    layout: defaultLayout('Topics Menu Page', {
      grid: { cols: 10, rows: 5 },
      free_slots: Array.from({ length: 50 }, (_, index) => index),
      fingerprint: 'topics-v1',
    }),
  });

  await newItems(page, 'Dinosaurs');
  await page.locator('.more-options > summary').click();
  await page.locator('#layout-options-btn').click();
  await page.locator('#style-topic').click();
  await page.locator('#layout-back-btn').click();
  await page.locator('#word-input').fill('Roar, Stomp, Chomp, Sleep, Run, Hide');
  await page.locator('#word-input').press('Enter');
  await expect(page.locator('#preview .cell.used')).toHaveCount(6);
  await page.waitForTimeout(1200);
  await expect(page.locator('#preview .cell.used')).toHaveCount(6);
  await expect(page.locator('#parent-select')).toHaveValue('Topics Menu Page');
});

test('AI suggestions use the chosen existing page and current buttons', async ({ page }) => {
  let request = null;
  await mockTD(page, {
    status: defaultStatus({
      page: 'Breakfast Foods',
      pages: ['Breakfast Foods', 'Topics Menu Page'],
    }),
    layout: defaultLayout('Breakfast Foods', {
      buttons: [{ slot: 0, label: 'Eggs' }, { slot: 1, label: 'Bacon' }],
      free_slots: [2, 3, 4, 5],
      fingerprint: 'breakfast-v1',
    }),
  });
  await page.route('**/api/ai/status*', (route) => fulfillJson(route, {
    ok: true,
    ollama: { reachable: true, models: ['llama3.2'] },
    local: {
      engine_available: false,
      downloaded: false,
      model: { name: 'Local', size: '1 GB', license: 'Apache-2.0' },
      download: { status: 'idle' },
    },
  }));
  await page.route('**/api/ai/words', (route) => {
    request = route.request().postDataJSON();
    return fulfillJson(route, { ok: true, words: ['Eggs', 'Waffles'], engine: 'ollama' });
  });

  await existingItems(page);
  await page.locator('.more-options > summary').click();
  await page.locator('#ai-suggest > summary').click();
  await expect(page.locator('#ai-go')).toBeEnabled();
  await page.locator('#ai-go').click();

  expect(request.category).toBe('Breakfast Foods');
  expect(request.existing).toEqual(['Eggs', 'Bacon']);
  await expect(page.locator('#chipbox .chip')).toHaveCount(1);
  await expect(page.locator('#chipbox .chip')).toContainText('Waffles');
});

test('AI topic phrases keep meaning-matched colors and rows', async ({ page }) => {
  let request = null;
  await mockTD(page, {
    status: defaultStatus({
      page: 'Topics Menu Page',
      grid: { cols: 5, rows: 5 },
      pages: ['Topics Menu Page'],
    }),
    layout: defaultLayout('Topics Menu Page', {
      grid: { cols: 5, rows: 5 },
      free_slots: Array.from({ length: 25 }, (_, index) => index),
      fingerprint: 'topics-v1',
    }),
  });
  await page.route('**/api/ai/status*', (route) => fulfillJson(route, {
    ok: true,
    ollama: { reachable: true, models: ['llama3.2'] },
    local: {
      engine_available: false,
      downloaded: false,
      model: { name: 'Local', size: '1 GB', license: 'Apache-2.0' },
      download: { status: 'idle' },
    },
  }));
  await page.route('**/api/ai/words', (route) => {
    request = route.request().postDataJSON();
    return fulfillJson(route, {
      ok: true,
      engine: 'ollama',
      words: [
        { label: 'Who is your favorite?', function: 'comment' },
        { label: 'The story has magic', function: 'question' },
        { label: 'I love this story', function: 'personal' },
        { label: 'I do not like spiders', function: 'positive' },
        { label: 'I read it with Mom', function: 'comment' },
      ],
    });
  });

  await newItems(page, 'Harry Potter');
  await page.locator('.more-options > summary').click();
  await page.locator('#layout-options-btn').click();
  await page.locator('#style-topic').click();
  await page.locator('#layout-back-btn').click();
  await page.locator('#ai-suggest > summary').click();
  await expect(page.locator('#ai-go')).toBeEnabled();
  await page.locator('#ai-go').click();

  expect(request.kind).toBe('phrases');
  const expected = [
    ['Who is your favorite?', 'rgb(30, 136, 229)', '0'],
    ['The story has magic', 'rgb(245, 124, 0)', '5'],
    ['I love this story', 'rgb(67, 160, 71)', '10'],
    ['I do not like spiders', 'rgb(229, 57, 53)', '15'],
    ['I read it with Mom', 'rgb(142, 36, 170)', '20'],
  ];
  for (const [label, color, slot] of expected) {
    const cell = page.locator('#preview .cell.used').filter({ hasText: label });
    await expect(cell).toHaveCSS('border-color', color);
    await expect(cell).toHaveAttribute('data-slot', slot);
  }
});

test('another edit refreshes the existing layout before a second submission', async ({ page }) => {
  let layoutCalls = 0;
  const submissions = [];
  await mockTD(page, {
    status: defaultStatus({ page: 'Eating', pages: ['Eating'] }),
    layout: () => {
      layoutCalls += 1;
      return defaultLayout('Eating', {
        buttons: [{ slot: 0, label: layoutCalls > 1 ? 'Apple' : 'Old Apple' }],
        free_slots: [1, 2, 3, 4, 5],
        fingerprint: layoutCalls > 1 ? 'eating-v2' : 'eating-v1',
      });
    },
  });
  await page.route('**/api/tdsnap/edit-plan', (route) => {
    submissions.push(route.request().postDataJSON());
    return fulfillJson(route, {
      ok: true,
      buttons: 1,
      checks: { td_snap_edit: 'pass', content: 'pass', positions: 'pass' },
      warnings: [],
    });
  });

  await existingItems(page);
  await page.locator('#word-input').fill('Pizza');
  await page.locator('#word-add-btn').click();
  await page.locator('#build-btn').click();
  await page.locator('#confirm-update-btn').click();
  await page.locator('#another-btn').click();
  await expect(page.locator('#wizard-items')).toBeVisible();
  await page.locator('#word-input').fill('Pasta');
  await page.locator('#word-add-btn').click();
  await page.locator('#build-btn').click();
  await page.locator('#confirm-update-btn').click();

  expect(submissions).toHaveLength(2);
  expect(submissions[0].fingerprint).toBe('eating-v1');
  expect(submissions[1].fingerprint).toBe('eating-v2');
});

test('existing labels are de-duplicated and page capacity is enforced', async ({ page }) => {
  await mockTD(page, {
    status: defaultStatus({ grid: { cols: 2, rows: 1 }, pages: ['Eating'] }),
    layout: defaultLayout('Eating', {
      grid: { cols: 2, rows: 1 },
      buttons: [{ slot: 0, label: 'Apple' }],
      free_slots: [1],
      fingerprint: 'eating-v1',
    }),
  });
  await existingItems(page);
  await page.locator('#word-input').fill('apple, Banana, Cherry');
  await page.locator('#word-input').press('Enter');
  await expect(page.locator('#chipbox .chip')).toHaveCount(1);
  await expect(page.locator('#chipbox .chip-body')).toContainText('Banana');
  await expect(page.locator('#chip-note')).toContainText(
    'apple is already on Eating, so it wasn’t added.',
  );
  await expect(page.locator('#chip-note')).toContainText('Eating is full.');
  await expect(page.locator('#chip-note')).toContainText('Cherry');
  await expect(page.locator('#word-input')).toBeDisabled();
  await expect(page.locator('#capacity')).toHaveText('1 added · 0 spaces left');
});

test('duplicate feedback names every skipped button and preserves spelling', async ({ page }) => {
  await mockTD(page, {
    status: defaultStatus({ pages: ['Eating'] }),
    layout: defaultLayout('Eating', {
      buttons: [{ slot: 0, label: 'Apple' }, { slot: 1, label: 'More' }],
      free_slots: [2, 3, 4, 5],
    }),
  });
  await existingItems(page);
  await page.locator('#word-input').fill('aPpLe, MORE, Banana');
  await page.locator('#word-input').press('Enter');
  await expect(page.locator('#chip-note li')).toHaveText(['aPpLe', 'MORE']);
  await expect(page.locator('#chip-note')).toContainText(
    'These buttons are already on Eating, so they weren’t added:',
  );
});

test('a full page uses human capacity language and blocks adding', async ({ page }) => {
  await mockTD(page, {
    status: defaultStatus({ grid: { cols: 1, rows: 1 }, pages: ['Eating'] }),
    layout: defaultLayout('Eating', {
      grid: { cols: 1, rows: 1 },
      buttons: [{ slot: 0, label: 'Apple' }],
      free_slots: [],
    }),
  });
  await existingItems(page);
  await expect(page.locator('#capacity')).toHaveText('Page is full');
  await expect(page.locator('#parent-capacity')).toContainText(
    '“Eating” is full. Choose another page',
  );
  await expect(page.locator('#word-input')).toBeDisabled();
  await expect(page.locator('#word-add-btn')).toBeDisabled();
});

test('button editor validates labels and preserves spoken text and color', async ({ page }) => {
  await mockTD(page);
  await existingItems(page);
  await page.locator('#word-input').fill('Hello, Goodbye');
  await page.locator('#word-input').press('Enter');
  await page.locator('#chipbox .chip-body').filter({ hasText: 'Hello' }).click();
  await page.locator('#edit-label').fill('Goodbye');
  await page.locator('#edit-save').click();
  await expect(page.locator('#chip-editor')).toBeVisible();
  await expect(page.locator('#edit-label')).toHaveJSProperty(
    'validationMessage',
    'Each button needs a unique label.',
  );
  await page.locator('#edit-label').fill('Greeting');
  await page.locator('#edit-message').fill('Hello, it is good to see you');
  await page.locator('#edit-fn-row [data-fn="personal"]').click();
  await page.locator('#edit-save').click();
  await expect(page.locator('#chip-editor')).toBeHidden();
  const greeting = page.locator('#chipbox .chip-body').filter({ hasText: 'Greeting' });
  await expect(greeting).toHaveAttribute('aria-label', /Personal.*speaks/);
  await page.locator('#build-btn').click();
  await expect(page.locator('#review-items')).toContainText('Speaks: Hello, it is good to see you');
});

test('radio groups, headings, and placement work with a keyboard', async ({ page }) => {
  await mockTD(page, {
    status: defaultStatus({ page: 'Topics Menu Page', pages: ['Topics Menu Page'] }),
    layout: defaultLayout('Topics Menu Page'),
  });
  await connect(page);
  await page.locator('#create-page-btn').focus();
  await page.locator('#create-page-btn').press('Enter');
  await expect(page.locator('#title-heading')).toBeFocused();
  await page.locator('#title-input').fill('Keyboard Page');
  await page.locator('#wizard-title .wizard-next').click();
  await page.locator('#wizard-destination .wizard-next').click();
  await page.locator('.more-options > summary').click();
  await page.locator('#layout-options-btn').click();
  await page.locator('#style-words').focus();
  await page.locator('#style-words').press('ArrowRight');
  await expect(page.locator('#style-topic')).toHaveAttribute('aria-checked', 'true');
  await page.locator('#layout-back-btn').click();
  await page.locator('#word-input').fill('How are you?, Great');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await page.locator('#adjust-placement-btn').click();
  const first = page.locator('#preview .cell.used').filter({ hasText: 'How are you?' });
  await first.press('ArrowRight');
  await expect(page.locator('#preview .cell.used').filter({ hasText: 'How are you?' }))
    .toHaveAttribute('aria-label', /column 2/);
});

test('a page-layout error is visible and a later selection recovers', async ({ page }) => {
  let placesAttempts = 0;
  let releaseFirstPlaces;
  const firstPlacesGate = new Promise((resolve) => { releaseFirstPlaces = resolve; });
  await mockTD(page, {
    status: defaultStatus({ pages: ['Eating', 'Places'] }),
    layout: async (requested, route) => {
      if (requested === 'Places' && ++placesAttempts === 1) {
        await firstPlacesGate;
        return route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ ok: false, error: 'TD Snap changed pages during inspection.' }),
        });
      }
      return defaultLayout(requested || 'Eating');
    },
  });

  await connect(page);
  await page.locator('#choose-page-btn').click();
  await page.locator('#parent-select').selectOption('Places');
  await expect(page.locator('#wizard-placement .preview-frame')).toHaveAttribute('aria-busy', 'true');
  releaseFirstPlaces();
  await expect(page.locator('#build-error')).toContainText(
    'Couldn’t load the selected page.',
  );
  await expect(page.locator('#parent-capacity')).toContainText('could not be loaded');
  await page.locator('#parent-select').selectOption('Eating');
  await page.locator('#parent-select').selectOption('Places');
  await expect(page.locator('#build-error')).toBeHidden();
  await expect(page.locator('#parent-capacity')).toContainText(
    '6 empty spaces AAC Editor can update safely',
  );
});

test('verification warnings appear only after explicit confirmation', async ({ page }) => {
  let releaseEdit;
  const editGate = new Promise((resolve) => { releaseEdit = resolve; });
  await mockTD(page);
  await page.route('**/api/tdsnap/edit-plan', async (route) => {
    await editGate;
    return fulfillJson(route, {
      ok: true,
      buttons: 1,
      checks: { td_snap_edit: 'pass', content: 'pass', symbols: 'partial' },
      warnings: ['TD Snap could not find a symbol for 1 button.'],
    });
  });

  await existingItems(page);
  await page.locator('#word-input').fill('Unusualword');
  await page.locator('#word-add-btn').click();
  await page.locator('#build-btn').click();
  await expect(page.locator('#app-activity')).toBeHidden();
  await page.locator('#confirm-update-btn').click();
  await expect(page.locator('#app-activity')).toContainText('Updating TD Snap and checking');
  await expect(page.locator('#confirm-update-btn')).toHaveAttribute('aria-busy', 'true');
  releaseEdit();
  await expect(page.locator('#checks li.warning')).toContainText('Matching symbols');
  await expect(page.locator('#result-warnings')).toContainText('could not find a symbol');
  await expect(page.locator('#result-heading')).toBeFocused();
});

test('a confirmed edit can run past the API deadline', async ({ page }) => {
  let editStarted;
  let finishEdit;
  const started = new Promise((resolve) => { editStarted = resolve; });
  const finish = new Promise((resolve) => { finishEdit = resolve; });
  await page.clock.install();
  await mockTD(page);
  await page.route('**/api/tdsnap/edit-plan', async (route) => {
    editStarted();
    await finish;
    return fulfillJson(route, { ok: true, buttons: 1, checks: {}, warnings: [] });
  });

  await existingItems(page);
  await page.locator('#word-input').fill('Help');
  await page.locator('#word-add-btn').click();
  await page.locator('#build-btn').click();
  await page.locator('#confirm-update-btn').click();
  await started;
  await page.clock.fastForward(10_001);
  finishEdit();

  await expect(page.locator('#result-heading')).toHaveText('Done \u2014 TD Snap was updated');
});

for (const viewport of [
  { name: '1100 by 800', width: 1100, height: 800, compact: false },
  { name: '760 by 560', width: 760, height: 560, compact: false },
  { name: '200 percent equivalent reflow', width: 550, height: 400, compact: true },
]) {
  test('layout remains readable at ' + viewport.name, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockTD(page);
    await connect(page);
    const layout = await page.evaluate(() => {
      const headingElement = document.querySelector('#items-heading');
      const heading = headingElement.getBoundingClientRect();
      const topElement = document.elementFromPoint(heading.left + 4, heading.top + 4);
      return {
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        headingTop: heading.top,
        headingVisible: topElement === headingElement || headingElement.contains(topElement),
      };
    });
    expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
    expect(layout.headingTop).toBeGreaterThanOrEqual(0);
    expect(layout.headingVisible).toBe(true);
    await expect(page.locator('#items-heading')).toBeFocused();
    if (!viewport.compact) {
      await page.locator('#word-input').fill('Help');
      await page.locator('#word-add-btn').click();
      await page.locator('#build-btn').click();
      const review = await page.evaluate(() => ({
        headingTop: document.querySelector('#result-heading').getBoundingClientRect().top,
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
      }));
      expect(review.headingTop).toBeGreaterThanOrEqual(0);
      expect(review.documentWidth).toBeLessThanOrEqual(review.viewportWidth);
      await expect(page.locator('#result-heading')).toBeFocused();
    }
  });
}

test('leaving with planned buttons asks first', async ({ page }) => {
  await mockTD(page);
  await existingItems(page);
  await page.locator('#word-input').fill('apple');
  await page.locator('#word-add-btn').click();
  await expect(page.locator('.chip')).toHaveCount(1);

  let asked = false;
  page.on('dialog', (dialog) => {
    asked = dialog.type() === 'beforeunload';
    return dialog.dismiss();
  });
  await page.close({ runBeforeUnload: true });
  await expect.poll(() => asked).toBe(true);
});

test('leaving with nothing planned does not ask', async ({ page }) => {
  await mockTD(page);
  await existingItems(page);

  let asked = false;
  page.on('dialog', (dialog) => {
    asked = true;
    return dialog.dismiss();
  });
  await page.close({ runBeforeUnload: true });
  await new Promise((resolve) => setTimeout(resolve, 500));
  expect(asked).toBe(false);
});

async function applyOneEdit(page, word = 'apple') {
  await page.route('**/api/tdsnap/edit-plan', (route) => fulfillJson(route, {
    ok: true, added: 1, checks: [{ name: 'TD Snap saved the change', ok: true }],
  }));
  await existingItems(page);
  await page.locator('#word-input').fill(word);
  await page.locator('#word-add-btn').click();
  await page.locator('#build-btn').click();
  await page.locator('#confirm-update-btn').click();
  await expect(page.locator('#success-state')).toBeVisible();
}

async function closeAndReportPrompt(page) {
  let asked = false;
  page.on('dialog', (dialog) => {
    if (dialog.type() === 'beforeunload') asked = true;
    return dialog.dismiss();
  });
  await page.close({ runBeforeUnload: true });
  await new Promise((resolve) => setTimeout(resolve, 500));
  return asked;
}

test('leaving after a successful edit does not ask', async ({ page }) => {
  // The words stay in state after a successful edit; they are in the page set
  // by then, so leaving is safe and must not prompt.
  await mockTD(page);
  await applyOneEdit(page);
  expect(await closeAndReportPrompt(page)).toBe(false);
});

test('composing again after a successful edit asks', async ({ page }) => {
  await mockTD(page);
  await applyOneEdit(page);

  await page.locator('#another-btn').click();
  await expect(page.locator('#wizard-items')).toBeVisible();
  await page.locator('#word-input').fill('banana');
  await page.locator('#word-add-btn').click();

  expect(await closeAndReportPrompt(page)).toBe(true);
});

test('an unexpected failure is surfaced instead of failing silently', async ({ page }) => {
  await mockTD(page);
  await openEditor(page);
  await expect(page.locator('#app-error')).toBeHidden();

  await page.evaluate(() => {
    // An unhandled rejection is the shape most of the app's async work takes.
    Promise.reject(new Error('simulated failure'));
  });

  await expect(page.locator('#app-error')).toBeVisible();
  await expect(page.locator('#app-error-text')).toHaveText('simulated failure');
  await page.locator('#app-error-dismiss').click();
  await expect(page.locator('#app-error')).toBeHidden();
});

test('the support report is shown before it is copied, and carries no page content', async ({ page }) => {
  await mockTD(page);
  await page.route('**/api/diagnostics', (route) => fulfillJson(route, {
    ok: true,
    report: {},
    text: 'AAC Editor support report\n\n[app]\n  version: 2.2.0\n',
  }));
  await openEditor(page);

  await page.locator('#support-report-btn').click();
  await expect(page.locator('#support-dialog')).toBeVisible();
  const report = await page.locator('#support-report-text').textContent();
  expect(report).toContain('AAC Editor support report');
  // 'Eating' is the mocked open page; the report must not name it.
  expect(report).not.toContain('Eating');
});

test('recent errors travel with the support report', async ({ page }) => {
  await mockTD(page);
  await page.route('**/api/diagnostics', (route) => fulfillJson(route, {
    ok: true,
    report: {},
    text: 'AAC Editor support report\n',
  }));
  await openEditor(page);
  await page.evaluate(() => {
    Promise.reject(new Error('simulated failure'));
  });
  await expect(page.locator('#app-error')).toBeVisible();

  await page.locator('#app-error-report').click();
  await expect(page.locator('#support-report-text')).toContainText('recent app errors');
  await expect(page.locator('#support-report-text')).toContainText('simulated failure');
});

test('support dialog has no serious or critical accessibility violations', async ({ page }) => {
  await mockTD(page);
  await page.route('**/api/diagnostics', (route) => fulfillJson(route, {
    ok: true, report: {}, text: 'AAC Editor support report\n',
  }));
  await openEditor(page);
  await page.locator('#support-report-btn').click();
  await expect(page.locator('#support-dialog')).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations
    .filter((violation) => ['serious', 'critical'].includes(violation.impact));
  expect(blocking).toEqual([]);
});

test.describe('never lose work: settings, drafts, and undo', () => {
  const draft = {
    provider: 'tdsnap',
    operation: 'existing',
    page_style: 'words',
    active_fn: '',
    target_page: 'Eating',
    title: '',
    items: [
      { label: 'Apple', message: null, fn: '', slot: 0, symbol: true, symbol_query: 'fruit' },
      { label: 'Banana', message: null, fn: '', slot: 1, symbol: false, symbol_query: null },
    ],
    saved_at: 1700000000,
  };

  test('the recovery banner offers an unfinished page, and resuming restores its buttons', async ({ page }) => {
    await mockSettings(page, { draft });
    await mockTD(page);
    await openEditor(page);

    const banner = page.locator('#draft-banner');
    await expect(banner).toBeVisible();
    await expect(page.locator('#draft-banner-text')).toContainText('Eating');

    await page.locator('#draft-resume-btn').click();
    await expect(banner).toBeHidden();

    await page.locator('#live-connect-btn').click();
    await expect(page.locator('#wizard-items')).toBeVisible();
    await expect(page.locator('#chipbox .chip')).toHaveCount(2);
    await expect(page.locator('#chipbox .chip-body').filter({ hasText: 'Apple' })).toBeVisible();
    await expect(page.locator('#chipbox .chip-body').filter({ hasText: 'Banana' })).toBeVisible();
    // Each button's symbol choice is part of the work, so it comes back too.
    await expect(
      page.locator('#chipbox .chip-body').filter({ hasText: 'Apple' }),
    ).toHaveAttribute('title', 'Symbol: “fruit”');
    await expect(
      page.locator('#chipbox .chip-body').filter({ hasText: 'Banana' }),
    ).toHaveAttribute('title', 'No symbol');
  });

  test('discarding the recovery banner clears the stored draft and starts empty', async ({ page }) => {
    const store = await mockSettings(page, { draft });
    await mockTD(page);
    await openEditor(page);

    await expect(page.locator('#draft-banner')).toBeVisible();
    await page.locator('#draft-discard-btn').click();
    await expect(page.locator('#draft-banner')).toBeHidden();
    await expect.poll(() => store.draft).toBeNull();

    await page.locator('#live-connect-btn').click();
    await expect(page.locator('#wizard-items')).toBeVisible();
    await expect(page.locator('#chipbox .chip')).toHaveCount(0);
  });

  test('the recovery banner has no serious or critical accessibility violations', async ({ page }) => {
    await mockSettings(page, { draft });
    await mockTD(page);
    await openEditor(page);
    await expect(page.locator('#draft-banner')).toBeVisible();
    expect(await blockingViolations(page)).toEqual([]);
  });

  test('the settings panel lists what is saved and Clear removes it, including a draft', async ({ page }) => {
    await mockSettings(page, {
      preferences: { provider: 'grid3', ollama_host: 'http://localhost:11434' },
      draft,
    });
    await mockTD(page);
    await openEditor(page);
    await page.locator('#draft-discard-btn').click(); // out of the way for this test

    await page.locator('#settings-panel-btn').click();
    const dialog = page.locator('#settings-panel');
    await expect(dialog).toBeVisible();
    await expect(page.locator('#settings-panel-list')).toContainText('grid3');
    await expect(page.locator('#settings-panel-list')).toContainText('localhost:11434');
    expect(await blockingViolations(page)).toEqual([]);

    await page.locator('#settings-clear-btn').click();
    await expect(page.locator('#settings-panel-status')).toContainText('Cleared');
    await expect(page.locator('#settings-panel-list')).toContainText('Nothing saved yet');
  });

  test('the last chosen AAC app is remembered, and falls back once nothing is stored', async ({ page }) => {
    const store = await mockSettings(page, { preferences: { provider: 'grid3' } });
    await mockTD(page);
    await page.goto(BASE_URL); // no ?provider= query string
    await expect(page.locator('#provider-grid3')).toHaveClass(/selected/);

    // Nothing stored (e.g. after Clear all saved data) falls back to the default.
    store.preferences = {};
    store.draft = null;
    await page.goto(BASE_URL);
    await expect(page.locator('#provider-tdsnap')).toHaveClass(/selected/);
  });

  test('removing a chip can be undone', async ({ page }) => {
    await mockTD(page);
    await existingItems(page);
    await page.locator('#word-input').fill('Apple, Banana');
    await page.locator('#word-input').press('Enter');
    await expect(page.locator('#chipbox .chip')).toHaveCount(2);
    await expect(page.locator('#undo-remove-btn')).toBeHidden();

    await page.getByRole('button', { name: 'Remove Apple' }).click();
    await expect(page.locator('#chipbox .chip')).toHaveCount(1);
    await expect(page.locator('#undo-remove-btn')).toBeVisible();

    await page.locator('#undo-remove-btn').click();
    await expect(page.locator('#chipbox .chip')).toHaveCount(2);
    await expect(page.locator('#chipbox .chip-body').filter({ hasText: 'Apple' })).toBeVisible();
    await expect(page.locator('#undo-remove-btn')).toBeHidden();
  });

  test('undo is scoped to the current session and does not resurrect a stale removal', async ({ page }) => {
    await mockTD(page);
    await existingItems(page);
    await page.locator('#word-input').fill('Apple');
    await page.locator('#word-input').press('Enter');
    await page.getByRole('button', { name: 'Remove Apple' }).click();
    await expect(page.locator('#undo-remove-btn')).toBeVisible();

    await page.locator('#file-badge').click(); // also calls resetConnection, and is reachable from any step
    await expect(page.locator('#step-load')).toBeVisible();
    await page.locator('#live-connect-btn').click();
    await expect(page.locator('#wizard-items')).toBeVisible();
    await expect(page.locator('#undo-remove-btn')).toBeHidden();
  });
});


/* Changing and removing what is already on the page.
 *
 * The safety rules matter more here than anywhere else in the suite: an
 * addition can be undone by deleting a chip, while a change or a removal
 * reaches into vocabulary somebody already relies on. These tests pin that
 * nothing is written before the review names it, that a button AAC Editor
 * must not touch says why, and that the request carries only the fields that
 * actually moved.
 */
test.describe('changing and removing existing buttons', () => {
  const EDITABLE_PAGE = {
    buttons: [
      {
        slot: 0, label: 'aple', message: 'I want an aple', function: null,
        symbol: true, editable: true, locked_reason: null,
      },
      {
        slot: 1, label: 'pear', message: null, function: null,
        symbol: true, editable: true, locked_reason: null,
      },
      {
        slot: 2, label: 'Games', message: null, function: null, symbol: true,
        editable: false,
        locked_reason: 'This button opens another page, so AAC Editor leaves it alone.',
      },
    ],
    free_slots: [3, 4, 5],
    content_readable: true,
    fingerprint: 'eating-v1',
  };

  async function editablePage(page, overrides = {}) {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating', { ...EDITABLE_PAGE, ...overrides }),
    });
  }

  async function openExisting(page, label) {
    await page.locator('#edit-existing-btn').click();
    await expect(page.locator('#wizard-placement')).toBeVisible();
    await page.locator('#preview .cell.existing').filter({ hasText: label }).click();
    await expect(page.locator('#chip-editor')).toBeVisible();
  }

  test('a locked button says why, and cannot be selected', async ({ page }) => {
    await editablePage(page);
    await connect(page);
    await page.locator('#edit-existing-btn').click();

    const locked = page.locator('#preview .cell.existing').filter({ hasText: 'Games' });
    await expect(locked).toHaveAttribute(
      'title', 'This button opens another page, so AAC Editor leaves it alone.',
    );
    await expect(locked).toHaveAttribute('aria-label', /existing and locked\. This button opens another page/);
    await expect(locked).not.toHaveAttribute('role', 'button');
    await locked.click();
    await expect(page.locator('#chip-editor')).toBeHidden();
  });

  test('the way in is hidden when the page set content cannot be read', async ({ page }) => {
    await editablePage(page, {
      content_readable: false,
      buttons: EDITABLE_PAGE.buttons.map((button) => ({
        ...button,
        editable: false,
        locked_reason: 'AAC Editor couldn’t read what this button holds today.',
      })),
    });
    await connect(page);

    await expect(page.locator('#edit-existing-btn')).toBeHidden();
  });

  test('a change and a removal are named in review and sent as one edit', async ({ page }) => {
    let submitted = null;
    let editCalls = 0;
    await editablePage(page);
    await page.route('**/api/tdsnap/edit-plan', (route) => {
      editCalls += 1;
      submitted = route.request().postDataJSON();
      return fulfillJson(route, {
        ok: true,
        page: 'Eating',
        buttons: 1,
        changed: 1,
        removed: 1,
        warnings: [],
        checks: {
          td_snap_edit: 'pass', target_page: 'pass', content: 'pass',
          positions: 'pass', changed_content: 'pass', removed_buttons: 'pass',
          untouched_buttons: 'pass',
        },
      });
    });

    await connect(page);
    await openExisting(page, 'aple');
    await expect(page.locator('#chip-editor-title')).toHaveText('Change this button');
    await expect(page.locator('#chip-editor-note')).toContainText('On the page now: “aple”');
    // The change operation never rewrites a topic-page row, so the dialog
    // does not offer one for a button that already exists.
    await expect(page.locator('#edit-fn-field')).toBeHidden();
    await expect(page.locator('#edit-label')).toHaveValue('aple');
    await expect(page.locator('#edit-message')).toHaveValue('I want an aple');
    await page.locator('#edit-label').fill('apple');
    await page.locator('#edit-save').click();
    await expect(page.locator('#preview .cell.marked-changed')).toHaveCount(1);

    await page.locator('#preview .cell.existing').filter({ hasText: 'pear' }).click();
    await page.locator('#edit-remove').click();
    await expect(page.locator('#preview .cell.marked-removed')).toHaveCount(1);

    await page.locator('#placement-back-btn').click();
    await expect(page.locator('#wizard-items')).toBeVisible();
    await expect(page.locator('#edit-existing-summary')).toHaveText(
      'Pending: change 1 and remove 1 button on eating.',
    );
    await page.locator('#word-input').fill('banana');
    await page.locator('#word-add-btn').click();
    await page.locator('#build-btn').click();

    await expect(page.locator('#review-action')).toHaveText(
      'Add 1, change 1 and remove 1 button on Eating',
    );
    await expect(page.locator('#confirm-update-label')).toHaveText(
      'Add 1, change 1 and remove 1 button on Eating',
    );
    await expect(page.locator('#review-changes li')).toHaveText([
      'aple“aple” becomes “apple”',
    ]);
    await expect(page.locator('#review-removals li')).toHaveText(['pear']);
    expect(editCalls).toBe(0);

    await page.locator('#confirm-update-btn').click();
    await expect(page.locator('#result-heading')).toHaveText('Done — TD Snap was updated');
    expect(editCalls).toBe(1);
    expect(submitted).toMatchObject({
      operation: 'edit_page',
      page: 'Eating',
      fingerprint: 'eating-v1',
      changes: [{ slot: 0, label: 'apple' }],
      removals: [1],
    });
    expect(submitted.items.map((item) => item.label)).toEqual(['banana']);
    await expect(page.locator('#result-sub')).toHaveText(
      '“Eating” was updated: 1 added, 1 changed, 1 removed. Nothing else on the page changed.',
    );
    await expect(page.locator('#checks li')).toContainText([
      'TD Snap saved the change',
      'The chosen page was updated',
      'Every requested speaking button is present',
      'Every new button is in the reviewed space',
      'Every changed button says what you asked for',
      'Every removed button is gone',
      'Nothing else on the page changed',
    ]);
  });

  test('a pending change can be taken back, leaving nothing to confirm', async ({ page }) => {
    await editablePage(page);
    await connect(page);
    await openExisting(page, 'aple');
    await page.locator('#edit-remove').click();
    await expect(page.locator('#preview .cell.marked-removed')).toHaveCount(1);

    await page.locator('#preview .cell.existing').filter({ hasText: 'aple' }).click();
    await expect(page.locator('#edit-revert')).toBeVisible();
    await page.locator('#edit-revert').click();
    await expect(page.locator('#preview .cell.marked-removed')).toHaveCount(0);

    await page.locator('#placement-back-btn').click();
    await expect(page.locator('#edit-existing-summary')).toBeHidden();
    await page.locator('#build-btn').click();
    await expect(page.locator('#items-error')).toHaveText(
      'Add at least one word or phrase before continuing.',
    );
  });

  test('a removal alone is enough to review and confirm', async ({ page }) => {
    let submitted = null;
    await editablePage(page);
    await page.route('**/api/tdsnap/edit-plan', (route) => {
      submitted = route.request().postDataJSON();
      return fulfillJson(route, {
        ok: true, page: 'Eating', buttons: 0, changed: 0, removed: 1,
        warnings: [], checks: { td_snap_edit: 'pass', removed_buttons: 'pass' },
      });
    });

    await connect(page);
    await openExisting(page, 'pear');
    await page.locator('#edit-remove').click();
    await page.locator('#placement-back-btn').click();
    await page.locator('#build-btn').click();

    await expect(page.locator('#review-action')).toHaveText('Remove 1 button on Eating');
    await expect(page.locator('#review-items-wrap')).toBeHidden();
    await expect(page.locator('#review-changes-wrap')).toBeHidden();
    await page.locator('#confirm-update-btn').click();
    await expect(page.locator('#result-heading')).toHaveText('Done — TD Snap was updated');
    expect(submitted).toMatchObject({ operation: 'edit_page', items: [], removals: [1] });
  });

  test('renaming onto a label already on the page is refused before review', async ({ page }) => {
    await editablePage(page);
    await connect(page);
    await openExisting(page, 'aple');
    await page.locator('#edit-label').fill('pear');
    await page.locator('#edit-save').click();

    await expect(page.locator('#chip-editor')).toBeVisible();
    await expect(page.locator('#preview .cell.marked-changed')).toHaveCount(0);
  });

  test('the editor works with a keyboard alone', async ({ page }) => {
    await editablePage(page);
    await connect(page);
    await page.locator('#edit-existing-btn').click();
    const target = page.locator('#preview .cell.existing').filter({ hasText: 'aple' });
    await target.focus();
    await target.press('Enter');

    await expect(page.locator('#chip-editor')).toBeVisible();
    await page.locator('#edit-label').fill('apple');
    await page.locator('#edit-save').click();
    await expect(page.locator('#preview .cell.marked-changed')).toHaveCount(1);
  });

  test('leaving with a pending removal asks first', async ({ page }) => {
    await editablePage(page);
    await connect(page);
    await openExisting(page, 'pear');
    await page.locator('#edit-remove').click();
    await page.locator('#placement-back-btn').click();

    // A pending removal is never autosaved, so the leave prompt is the only
    // thing between the user and losing it.
    const prompted = await page.evaluate(() => {
      const event = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    });
    expect(prompted).toBe(true);
  });

  test('the change editor has no serious or critical accessibility violations', async ({ page }) => {
    await editablePage(page);
    await connect(page);
    await page.locator('#edit-existing-btn').click();
    expect(await blockingViolations(page)).toEqual([]);

    await page.locator('#preview .cell.existing').filter({ hasText: 'aple' }).click();
    await expect(page.locator('#chip-editor')).toBeVisible();
    expect(await blockingViolations(page)).toEqual([]);
    await page.locator('#edit-save').click();

    await page.locator('#preview .cell.existing').filter({ hasText: 'pear' }).click();
    await page.locator('#edit-remove').click();
    await page.locator('#placement-back-btn').click();
    await page.locator('#build-btn').click();
    await expect(page.locator('#review-removals li')).toHaveCount(1);
    expect(await blockingViolations(page)).toEqual([]);
  });
});

/* Moving what is already on the page, and undoing an edit that has landed.
 *
 * Both reach into vocabulary somebody relies on, so the same rules apply as to
 * changing and removing: nothing is written before the review names it, a
 * locked button says why, and the request carries cells rather than guesses.
 * The undo tests also pin the two things it cannot reach — one edit back, and
 * not past a TD Snap sync — being said before it runs, not after.
 */
test.describe('moving buttons and undoing an applied edit', () => {
  const MOVABLE_PAGE = {
    buttons: [
      {
        slot: 0, label: 'aple', message: 'I want an aple', function: null,
        symbol: true, editable: true, locked_reason: null,
      },
      {
        slot: 1, label: 'pear', message: null, function: null,
        symbol: true, editable: true, locked_reason: null,
      },
      {
        slot: 2, label: 'Games', message: null, function: null, symbol: true,
        editable: false,
        locked_reason: 'This button opens another page, so AAC Editor leaves it alone.',
      },
    ],
    free_slots: [3, 4, 5],
    content_readable: true,
    fingerprint: 'eating-v1',
  };

  const APPLIED = {
    page: 'Eating',
    grid: { cols: 3, rows: 2 },
    restores: {
      adds: [{ label: 'old', message: 'the old one' }],
      changes: [{
        label: 'aple', message: 'I want an aple',
        from: { label: 'apple', message: 'I want an apple' },
      }],
      removals: [{ label: 'banana', message: null }],
      moves: [{ label: 'pear', slot: 4, to: 1 }],
    },
    warnings: ['“old” is re-created with a fresh TD Snap symbol search, which may not find the symbol it had.'],
  };

  async function movablePage(page, overrides = {}) {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating', { ...MOVABLE_PAGE, ...overrides }),
    });
  }

  /* What the server would say it is holding, and what an undo would report. */
  async function mockUndo(page, { available = null, report = null } = {}) {
    const calls = { undo: 0, forgotten: 0, body: null };
    await page.route('**/api/tdsnap/last-edit', (route) => {
      if (route.request().method() === 'DELETE') {
        calls.forgotten += 1;
        return fulfillJson(route, { ok: true });
      }
      return fulfillJson(route, { ok: true, undo: available });
    });
    await page.route('**/api/tdsnap/undo', (route) => {
      calls.undo += 1;
      calls.body = route.request().postDataJSON();
      return fulfillJson(route, {
        ok: true,
        page: 'Eating',
        buttons: 1, changed: 1, removed: 0, moved: 1,
        undone: true,
        undo: null,
        warnings: [],
        checks: {
          td_snap_edit: 'pass', target_page: 'pass', content: 'pass',
          positions: 'pass', changed_content: 'pass', moved_buttons: 'pass',
          untouched_buttons: 'pass', undone: 'pass',
        },
        ...(report || {}),
      });
    });
    return calls;
  }

  test('a button is dragged to an empty cell and named in review', async ({ page }) => {
    let submitted = null;
    await movablePage(page);
    await page.route('**/api/tdsnap/edit-plan', (route) => {
      submitted = route.request().postDataJSON();
      return fulfillJson(route, {
        ok: true, page: 'Eating', buttons: 0, changed: 0, removed: 0, moved: 1,
        warnings: [], undo: null,
        checks: { td_snap_edit: 'pass', moved_buttons: 'pass', untouched_buttons: 'pass' },
      });
    });
    await connect(page);
    await page.locator('#edit-existing-btn').click();

    const apple = page.locator('#preview .cell.existing').filter({ hasText: 'aple' });
    await apple.focus();
    await apple.press('ArrowDown');

    // The button is drawn where it is going, and the cell it left is empty.
    const moved = page.locator('#preview [data-slot="3"]');
    await expect(moved).toHaveClass(/marked-moved/);
    await expect(moved).toHaveText(/aple/);
    await expect(moved).toHaveAttribute('aria-label', /Moved here from row 1, column 1/);
    await expect(page.locator('#preview [data-slot="0"]')).toHaveText('');

    await page.locator('#placement-back-btn').click();
    await expect(page.locator('#edit-existing-summary')).toHaveText(
      'Pending: move 1 button on eating.',
    );
    await page.locator('#build-btn').click();

    await expect(page.locator('#review-action')).toHaveText('Move 1 button on Eating');
    await expect(page.locator('#review-moves li')).toHaveText([
      'aplerow 1, column 1 → row 2, column 1',
    ]);

    await page.locator('#confirm-update-btn').click();
    await expect(page.locator('#result-heading')).toHaveText('Done — TD Snap was updated');
    expect(submitted).toMatchObject({
      operation: 'edit_page',
      page: 'Eating',
      fingerprint: 'eating-v1',
      moves: [{ slot: 0, to: 3 }],
      changes: [],
      removals: [],
    });
    await expect(page.locator('#checks li')).toContainText([
      'Every moved button is in its new cell',
    ]);
  });

  test('dropping one button on another sends both halves of the swap', async ({ page }) => {
    let submitted = null;
    await movablePage(page);
    await page.route('**/api/tdsnap/edit-plan', (route) => {
      submitted = route.request().postDataJSON();
      return fulfillJson(route, {
        ok: true, page: 'Eating', buttons: 0, changed: 0, removed: 0, moved: 2,
        warnings: [], undo: null, checks: { td_snap_edit: 'pass', moved_buttons: 'pass' },
      });
    });
    await connect(page);
    await page.locator('#edit-existing-btn').click();

    // Arrow keys are the keyboard equivalent of dropping one onto the other.
    const apple = page.locator('#preview .cell.existing').filter({ hasText: 'aple' });
    await apple.focus();
    await apple.press('ArrowRight');

    await expect(page.locator('#preview [data-slot="1"]')).toHaveText(/aple/);
    await expect(page.locator('#preview [data-slot="0"]')).toHaveText(/pear/);

    await page.locator('#placement-back-btn').click();
    await page.locator('#build-btn').click();
    await expect(page.locator('#review-action')).toHaveText('Move 2 buttons on Eating');
    await page.locator('#confirm-update-btn').click();

    expect(submitted.moves).toEqual([{ slot: 0, to: 1 }, { slot: 1, to: 0 }]);
  });

  test('a locked button is never moved and never landed on', async ({ page }) => {
    await movablePage(page);
    await connect(page);
    await page.locator('#edit-existing-btn').click();

    const locked = page.locator('#preview .cell.existing').filter({ hasText: 'Games' });
    await expect(locked).not.toHaveAttribute('draggable', 'true');

    // "pear" sits next to the locked button; moving right must do nothing.
    const pear = page.locator('#preview .cell.existing').filter({ hasText: 'pear' });
    await pear.focus();
    await pear.press('ArrowRight');
    await expect(page.locator('#preview [data-slot="1"]')).toHaveText(/pear/);
    await expect(page.locator('#preview [data-slot="2"]')).toHaveText(/Games/);
    await expect(page.locator('#preview .cell.marked-moved')).toHaveCount(0);
  });

  test('a cell a move frees becomes space for a new button', async ({ page }) => {
    await movablePage(page, { free_slots: [3] });
    await connect(page);
    // One free cell to start with: three existing buttons on a six-cell grid,
    // and the page reports only cell 3 as safe to write to.
    await expect(page.locator('#capacity')).toHaveText('1 space available');

    await page.locator('#edit-existing-btn').click();
    const apple = page.locator('#preview .cell.existing').filter({ hasText: 'aple' });
    await apple.focus();
    await apple.press('ArrowDown');
    await page.locator('#placement-back-btn').click();

    // Cell 0 is now free and cell 3 is taken, so the count is unchanged — but
    // the space that is offered has moved with the button.
    await expect(page.locator('#capacity')).toHaveText('1 space available');
    await page.locator('#word-input').fill('banana');
    await page.locator('#word-add-btn').click();
    await expect(page.locator('#preview [data-slot="0"]')).toHaveText(/banana/);
  });

  test('a symbol can be skipped or given its own search words', async ({ page }) => {
    let submitted = null;
    await movablePage(page);
    await page.route('**/api/tdsnap/edit-plan', (route) => {
      submitted = route.request().postDataJSON();
      return fulfillJson(route, {
        ok: true, page: 'Eating', buttons: 2, changed: 0, removed: 0, moved: 0,
        undo: null,
        warnings: ['TD Snap found no symbol for "more please". It was added without one — add one in TD Snap, or try different symbol search words.'],
        checks: { td_snap_edit: 'pass', symbols: 'partial' },
      });
    });
    await connect(page);
    await page.locator('#word-input').fill('more please, quiet');
    await page.locator('#word-input').press('Enter');

    await page.locator('.chip-body').filter({ hasText: 'more please' }).click();
    await expect(page.locator('#edit-symbol-field')).toBeVisible();
    await page.locator('#edit-symbol-query').fill('more');
    await page.locator('#edit-save').click();

    await page.locator('.chip-body').filter({ hasText: 'quiet' }).click();
    await page.locator('#edit-symbol').uncheck();
    // The search words are meaningless once no symbol is wanted, so they go.
    await expect(page.locator('#edit-symbol-query-row')).toBeHidden();
    await page.locator('#edit-save').click();

    await expect(
      page.locator('.chip-body').filter({ hasText: 'quiet' }),
    ).toHaveAttribute('title', 'No symbol');
    await page.locator('#build-btn').click();
    await expect(page.locator('#review-items li')).toHaveText([
      'more pleaseSymbol search: more',
      'quietNo symbol',
    ]);

    await page.locator('#confirm-update-btn').click();
    expect(submitted.items.map(
      ({ label, symbol, symbol_query: query }) => ({ label, symbol, query }),
    )).toEqual([
      { label: 'more please', symbol: true, query: 'more' },
      { label: 'quiet', symbol: false, query: null },
    ]);
    // The warning names the button, not a count.
    await expect(page.locator('#result-warnings')).toContainText('"more please"');
  });

  test('an applied edit is offered back, reviewed, and replayed in reverse', async ({ page }) => {
    await movablePage(page);
    const calls = await mockUndo(page, { available: APPLIED });
    await connect(page);

    // Offered on the word list, where somebody who carried on would notice.
    await expect(page.locator('#undo-last-btn')).toBeVisible();
    await page.locator('#undo-last-btn').click();

    await expect(page.locator('#result-heading')).toHaveText(
      'Check what undoing will put back',
    );
    await expect(page.locator('#review-action')).toHaveText(
      'Add 1, change 1, move 1 and remove 1 button on Eating',
    );
    await expect(page.locator('#review-items-wrap h3')).toHaveText('Buttons to put back');
    await expect(page.locator('#review-items li')).toHaveText(['oldSpeaks: the old one']);
    await expect(page.locator('#review-changes li')).toHaveText([
      'apple“apple” becomes “aple” · speaks “I want an aple”',
    ]);
    await expect(page.locator('#review-moves li')).toHaveText([
      'pearrow 2, column 2 → row 1, column 2',
    ]);
    await expect(page.locator('#review-removals li')).toHaveText(['banana']);
    // What it cannot reach is stated before it runs.
    await expect(page.locator('#review-undo-note')).toContainText(
      'cannot reach back past a sync in TD Snap',
    );
    await expect(page.locator('#review-undo-note')).toContainText(
      'fresh TD Snap symbol search',
    );
    // An undo has no placement to adjust.
    await expect(page.locator('#adjust-placement-btn')).toBeHidden();
    expect(calls.undo).toBe(0);

    await page.locator('#confirm-update-btn').click();
    await expect(page.locator('#result-heading')).toHaveText(
      'Done — the last change was undone in TD Snap',
    );
    expect(calls.undo).toBe(1);
    await expect(page.locator('#result-sub')).toContainText(
      'There is nothing left to undo from this session.',
    );
    await expect(page.locator('#checks li')).toContainText([
      'The previous change was put back',
    ]);
    // Single level: once spent, the control goes.
    await expect(page.locator('#undo-edit-btn')).toBeHidden();
  });

  test('nothing is offered to undo until an edit has been applied', async ({ page }) => {
    await movablePage(page);
    await mockUndo(page, { available: null });
    await connect(page);

    await expect(page.locator('#undo-last-btn')).toBeHidden();
    await page.locator('#word-input').fill('banana');
    await page.locator('#word-add-btn').click();
    await expect(page.locator('#undo-last-btn')).toBeHidden();
  });

  test('a refused undo says the page was left alone', async ({ page }) => {
    await movablePage(page);
    await mockUndo(page, { available: APPLIED });
    await page.route('**/api/tdsnap/undo', (route) => fulfillJson(route, {
      ok: false,
      error: 'The target page changed after preview. Refresh the layout and review the edit again.',
    }, 400));
    await connect(page);
    await page.locator('#undo-last-btn').click();
    await page.locator('#confirm-update-btn').click();

    await expect(page.locator('#review-error')).toContainText(
      'TD Snap couldn’t undo the last change.',
    );
    await expect(page.locator('#review-error')).toContainText(
      'the page is as it was before this undo',
    );
  });

  test('starting over stops offering an undo for a page set that may change', async ({ page }) => {
    await movablePage(page);
    const calls = await mockUndo(page, { available: APPLIED });
    await connect(page);
    await expect(page.locator('#undo-last-btn')).toBeVisible();

    await page.locator('#choose-page-btn').click();
    await page.locator('#reset-btn').click();

    await expect(page.locator('#step-load')).toBeVisible();
    expect(calls.forgotten).toBe(1);
  });

  test('the undo review has no serious or critical accessibility violations', async ({ page }) => {
    await movablePage(page);
    await mockUndo(page, { available: APPLIED });
    await connect(page);
    await page.locator('#undo-last-btn').click();
    await expect(page.locator('#review-undo-note')).toBeVisible();

    expect(await blockingViolations(page)).toEqual([]);
  });
});


/* Adding to a page that already exists in an exported file.
 *
 * The third provider could only ever create a page, which meant the most
 * ordinary request — three more words on a page somebody already uses — was
 * possible on Windows and nowhere else. These pin that it now walks the same
 * two routes as a live connection, and that the review still names the page.
 */
test.describe('exported file adds to an existing page', () => {
  const SESSION = {
    ok: true,
    session_id: 'file-session',
    filename: 'sample.sps',
    schema_version: '4.13',
    grid: { cols: 3, rows: 2 },
    pages: [{ id: 1, title: 'Home' }, { id: 2, title: 'Eating' }],
    baseline_problems: [],
  };

  const LAYOUT = {
    ok: true,
    page: 'Home',
    grid: { cols: 3, rows: 2 },
    buttons: [{
      slot: 0, label: 'apple', message: null, function: null, symbol: false,
      editable: false,
      locked_reason: 'AAC Editor only adds buttons in exported files.',
    }],
    free_slots: [1, 2, 3, 4, 5],
    content_readable: false,
    fingerprint: 'file-home-v1',
  };

  async function openFile(page, routes = {}) {
    await page.route('**/api/pageset', (route) => fulfillJson(route, SESSION));
    await page.route('**/api/pageset/file-session/pages', (route) =>
      fulfillJson(route, { ok: true, pages: SESSION.pages }));
    await page.route('**/api/pageset/file-session/page/*/layout', (route) =>
      fulfillJson(route, LAYOUT));
    for (const [pattern, handler] of Object.entries(routes)) {
      await page.route(pattern, handler);
    }
    await openEditor(page);
    await page.locator('#provider-file').click();
    await page.locator('#file-input').setInputFiles({
      name: 'sample.sps',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('synthetic pageset'),
    });
    await expect(page.locator('#wizard-operation')).toBeVisible();
  }

  test('buttons are added to a chosen page and the review names it', async ({ page }) => {
    let submitted = null;
    await openFile(page, {
      '**/api/pageset/file-session/page/1/buttons': (route) => {
        submitted = route.request().postDataJSON();
        return fulfillJson(route, {
          ok: true, buttons: submitted.items.length, edits: 1,
          checks: {
            sqlite_integrity: 'pass', linkage_chains: 'pass',
            roundtrip_diff: 'pass', target_page: 'pass', positions: 'pass',
          },
        });
      },
    });

    // "Add buttons to an existing page" leads, as it does for a live connection.
    await expect(page.locator('#operation-existing')).toHaveAttribute('aria-checked', 'true');
    await page.locator('#wizard-operation .wizard-next').click();
    await expect(page.locator('#parent-capacity')).toContainText('5 empty spaces');
    await page.locator('#wizard-destination .wizard-next').click();

    // Existing buttons are shown and locked, and say so.
    await expect(page.locator('#preview .cell.existing')).toHaveText(/apple/);
    await expect(page.locator('#preview .cell.existing')).toHaveAttribute(
      'title', 'AAC Editor only adds buttons in exported files.',
    );
    await expect(page.locator('#edit-existing-btn')).toBeHidden();

    await page.locator('#word-input').fill('Chips, Juice');
    await page.locator('#word-input').press('Enter');
    await page.locator('#build-btn').click();
    await expect(page.locator('#review-action')).toHaveText('Add 2 buttons to Home');
    await expect(page.locator('#review-target')).toHaveText('Home');

    await page.locator('#confirm-update-btn').click();
    await expect(page.locator('#result-heading')).toHaveText('Done — TD Snap was updated');
    await expect(page.locator('#file-save-btn')).toBeVisible();
    expect(submitted.fingerprint).toBe('file-home-v1');
    expect(submitted.items.map((item) => item.slot)).toEqual([1, 2]);
    expect(submitted.items.map((item) => item.label)).toEqual(['Chips', 'Juice']);
    // No page is created on this path, so no title travels with it.
    expect(submitted.title).toBeUndefined();
  });

  test('a stale review is refused and says how to recover', async ({ page }) => {
    await openFile(page, {
      '**/api/pageset/file-session/page/1/buttons': (route) => fulfillJson(route, {
        ok: false,
        error: 'This page changed after the preview. Reload the page and review the edit again.',
      }, 400),
    });
    await page.locator('#wizard-operation .wizard-next').click();
    await page.locator('#wizard-destination .wizard-next').click();
    await page.locator('#word-input').fill('Chips');
    await page.locator('#word-input').press('Enter');
    await page.locator('#build-btn').click();
    await page.locator('#confirm-update-btn').click();

    await expect(page.locator('#review-error')).toContainText(
      'This page changed after the preview.',
    );
  });
});

test('real TD Snap edit is explicit opt-in', async ({ page }) => {
  test.skip(
    process.env.TDSNAP_LIVE_E2E !== '1',
    'set TDSNAP_LIVE_E2E=1 to add a real Playwright Test page to the open TD Snap set',
  );
  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await page.locator('#create-page-btn').click();
  await page.locator('#title-input').fill('Playwright Test');
  await page.locator('#wizard-title .wizard-next').click();
  await page.locator('#wizard-destination .wizard-next').click();
  await page.locator('#word-input').fill('hello');
  await page.locator('#word-add-btn').click();
  await page.locator('#build-btn').click();
  await page.locator('#confirm-update-btn').click();
  await expect(page.locator('#result-heading')).toHaveText(
    'Done — TD Snap was updated',
    { timeout: 30_000 },
  );
});


/* Importing a word list.
 *
 * The chip box already took a comma-separated paste; this is the shape the
 * work actually arrives in — a column of labels beside a column of sentences,
 * out of a spreadsheet. These pin the two things that make it safe to use: a
 * comma inside a phrase stays inside the phrase, and everything that will not
 * fit is named on screen before a single button is added.
 */
test.describe('importing a word list', () => {
  async function openImport(page) {
    await existingItems(page);
    await page.locator('.more-options > summary').click();
    await page.locator('#import-list-btn').click();
    await expect(page.locator('#import-dialog')).toBeVisible();
  }

  test('a pasted spreadsheet column maps itself and keeps phrases intact', async ({ page }) => {
    await mockTD(page);
    await openImport(page);

    await page.locator('#import-text').fill(
      'Label\tWhat it says\tFunction\n'
      + 'more\tI want more, please\tQuestion\n'
      + 'all done\tI am all done\tPositive\n'
      + 'help\t\t'
    );

    // The header is recognised and the columns are mapped without being asked.
    await expect(page.locator('#import-has-header')).toBeChecked();
    await expect(page.locator('#import-column-0')).toHaveValue('label');
    await expect(page.locator('#import-column-1')).toHaveValue('message');
    await expect(page.locator('#import-column-2')).toHaveValue('fn');
    await expect(page.locator('#import-summary')).toContainText('3 buttons ready to add');
    // The preview shows the rows as the mapping reads them.
    await expect(page.locator('#import-preview tbody tr').first())
      .toContainText('I want more, please');

    await page.locator('#import-add-btn').click();
    await expect(page.locator('#import-dialog')).toBeHidden();

    await expect(page.locator('#chipbox .chip')).toHaveCount(3);
    // The comma is punctuation inside the phrase, not a second button.
    await expect(page.locator('.chip-body').filter({ hasText: 'more' }).first())
      .toHaveAttribute('title', 'Speaks: “I want more, please”');
  });

  test('a single column of words needs no mapping at all', async ({ page }) => {
    await mockTD(page);
    await openImport(page);

    await page.locator('#import-text').fill('apple\npear\nplum');

    await expect(page.locator('#import-has-header')).not.toBeChecked();
    await expect(page.locator('#import-summary')).toContainText('3 buttons ready to add');
    await page.locator('#import-add-btn').click();
    await expect(page.locator('#chipbox .chip')).toHaveCount(3);
  });

  test('what will not fit is named before anything is added', async ({ page }) => {
    // Two free cells, and one of the imported words is already on the page.
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating', {
        buttons: [{
          slot: 0, label: 'apple', message: null, function: null, symbol: true,
          editable: false, locked_reason: 'Existing TD Snap button',
        }],
        free_slots: [1, 2],
      }),
    });
    await openImport(page);

    await page.locator('#import-text').fill('apple\npear\nplum\ncherry\nmango');

    const summary = page.locator('#import-summary');
    await expect(summary).toContainText('2 buttons ready to add');
    await expect(summary).toContainText('Already on Eating');
    await expect(summary).toContainText('apple');
    await expect(summary).toContainText('does not have room for 2 of these');
    await expect(summary).toContainText('cherry');
    await expect(page.locator('#import-add-btn')).toHaveText('Add 2 buttons');

    await page.locator('#import-add-btn').click();
    await expect(page.locator('#chipbox .chip')).toHaveCount(2);
    await expect(page.locator('#capacity')).toHaveText('2 added · 0 spaces left');
  });

  test('a row that cannot become a button says which row and why', async ({ page }) => {
    await mockTD(page);
    await openImport(page);

    await page.locator('#import-text').fill(
      'Label,Message\n'
      + 'more,I want more\n'
      + ',orphan message\n'
      + 'more,repeated label\n'
    );

    const summary = page.locator('#import-summary');
    await expect(summary).toContainText('1 button ready to add');
    // A row with no label is still identified by what it does hold, so the
    // user can find it in their file.
    await expect(summary).toContainText('Row 3, “orphan message” — no label');
    await expect(summary).toContainText('Row 4, “more” — repeated in this list');
  });

  test('an unrecognised header is visible in the preview and correctable', async ({ page }) => {
    await mockTD(page);
    await openImport(page);

    await page.locator('#import-text').fill('col1\tcol2\napple\tI want an apple');

    // Nothing in the header is recognisable, so the first row is treated as
    // vocabulary — and the preview shows exactly that, rather than hiding it.
    await expect(page.locator('#import-has-header')).not.toBeChecked();
    await expect(page.locator('#import-summary')).toContainText('2 buttons ready to add');
    await expect(page.locator('#import-preview tbody')).toContainText('col1');

    // One checkbox fixes it, and the second column can then be mapped.
    await page.locator('#import-has-header').check();
    await page.locator('#import-column-1').selectOption('message');
    await expect(page.locator('#import-summary')).toContainText('1 button ready to add');

    await page.locator('#import-add-btn').click();
    await expect(page.locator('#chipbox .chip')).toHaveCount(1);
    await expect(page.locator('.chip-body').filter({ hasText: 'apple' }))
      .toHaveAttribute('title', 'Speaks: “I want an apple”');
  });

  test('an import waits until a label column is chosen', async ({ page }) => {
    await mockTD(page);
    await openImport(page);

    await page.locator('#import-text').fill('col1\tcol2\napple\tI want an apple');
    await page.locator('#import-column-0').selectOption('');

    await expect(page.locator('#import-summary'))
      .toContainText('Choose which column holds the button label');
    await expect(page.locator('#import-add-btn')).toBeDisabled();
  });

  test('the import dialog has no serious or critical accessibility violations', async ({ page }) => {
    await mockTD(page);
    await openImport(page);
    await page.locator('#import-text').fill('Label\tMessage\napple\tI want an apple');
    await expect(page.locator('#import-mapping')).toBeVisible();

    expect(await blockingViolations(page)).toEqual([]);
  });
});


/* Page-set-wide duplicate detection.
 *
 * The blocking per-page check is unchanged: a word already on *this* page is
 * still skipped. This is the other half — the same word on some *other* page
 * is worth knowing about and must never be blocked, because two pages
 * deliberately carrying "more" is a normal thing for a page set to do.
 */
test.describe('duplicates elsewhere in the page set', () => {
  async function withVocabulary(page, labels) {
    await page.route('**/api/tdsnap/vocabulary', (route) =>
      fulfillJson(route, { ok: true, available: true, labels }));
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
  }

  test('a word already on another page is noted, and still added', async ({ page }) => {
    await withVocabulary(page, { more: ['Core Words', 'Feelings'] });
    await existingItems(page);

    await page.locator('#word-input').fill('more');
    await page.locator('#word-add-btn').click();

    const note = page.locator('#chip-note');
    await expect(note).toContainText('Already elsewhere in this page set');
    await expect(note).toContainText('“more” on Core Words, Feelings');
    await expect(note).toContainText('nothing is skipped');
    // Advisory means advisory: the button is on the list and reviewable.
    await expect(page.locator('#chipbox .chip')).toHaveCount(1);
    await page.locator('#build-btn').click();
    await expect(page.locator('#review-action')).toContainText('Add 1 button');
  });

  test('the page being edited is not named twice', async ({ page }) => {
    // "apple" is on Eating, which is the page being edited, and on Snacks.
    await withVocabulary(page, { apple: ['Eating', 'Snacks'] });
    await existingItems(page);

    await page.locator('#word-input').fill('apple');
    await page.locator('#word-add-btn').click();

    const note = page.locator('#chip-note');
    await expect(note).toContainText('“apple” on Snacks');
    await expect(note).not.toContainText('Eating');
  });

  test('a word that exists nowhere else says nothing at all', async ({ page }) => {
    await withVocabulary(page, { more: ['Core Words'] });
    await existingItems(page);

    await page.locator('#word-input').fill('kayak');
    await page.locator('#word-add-btn').click();

    await expect(page.locator('#chip-note')).toHaveText('');
  });

  test('an unreadable page set simply says nothing', async ({ page }) => {
    await page.route('**/api/tdsnap/vocabulary', (route) =>
      fulfillJson(route, { ok: true, available: false, labels: {} }));
    await mockTD(page);
    await existingItems(page);

    await page.locator('#word-input').fill('more');
    await page.locator('#word-add-btn').click();

    await expect(page.locator('#chip-note')).toHaveText('');
    await expect(page.locator('#chipbox .chip')).toHaveCount(1);
  });

  test('an import names what already exists elsewhere', async ({ page }) => {
    await withVocabulary(page, { more: ['Core Words'], help: ['Core Words'] });
    await existingItems(page);
    await page.locator('.more-options > summary').click();
    await page.locator('#import-list-btn').click();

    await page.locator('#import-text').fill('more\nhelp\nkayak');

    const summary = page.locator('#import-summary');
    await expect(summary).toContainText('3 buttons ready to add');
    await expect(summary).toContainText('Already elsewhere in this page set');
    await expect(summary).toContainText('“more” on Core Words');
    await expect(summary).toContainText('“help” on Core Words');
  });
});


/* Reusable topic templates.
 *
 * The caseload case: an SLP builds a good Swimming page once and wants it for
 * the next client, and the next. These pin the parts that make that reuse
 * safe — a template carries vocabulary and nothing tied to one page set, it
 * survives the draft autosave that runs between saving and reusing it, and
 * applying it to a page that cannot hold it all says so rather than dropping
 * words quietly.
 */
test.describe('reusable topic templates', () => {
  // More options may already be open from an earlier step in the same test;
  // clicking the summary again would close it.
  async function openTemplates(page) {
    const options = page.locator('.more-options');
    if (!(await options.evaluate((node) => node.open))) {
      await options.locator('> summary').click();
    }
    await page.locator('#templates-btn').click();
    await expect(page.locator('#templates-dialog')).toBeVisible();
  }

  test('a topic page saved once is added to a different page set', async ({ page }) => {
    const store = await mockSettings(page);
    await mockTD(page, {
      status: defaultStatus({ pages: ['Topics Menu Page'], grid: { cols: 4, rows: 3 } }),
      layout: defaultLayout('Topics Menu Page', {
        grid: { cols: 4, rows: 3 },
        free_slots: Array.from({ length: 12 }, (_, index) => index),
        fingerprint: 'topics-v1',
      }),
    });

    await newItems(page, 'Swimming');
    await page.locator('.more-options > summary').click();
    await page.locator('#layout-options-btn').click();
    await page.locator('#style-topic').click();
    await page.locator('#layout-back-btn').click();
    await page.locator('#word-input').fill('Splash, Jump in, Too cold');
    await page.locator('#word-input').press('Enter');
    await expect(page.locator('#chipbox .chip')).toHaveCount(3);

    await openTemplates(page);
    await page.locator('#template-name').fill('Swimming');
    await page.locator('#template-save-btn').click();
    await expect(page.locator('#template-save-hint')).toContainText('Saved “Swimming”');
    await expect(page.locator('#template-list li')).toContainText('3 buttons');
    await expect(page.locator('#template-list li')).toContainText('topic-page rows');

    // What was stored is vocabulary, not this page set: no page id, no
    // fingerprint, no title.
    expect(store.templates).toHaveLength(1);
    const saved = JSON.stringify(store.templates[0]);
    expect(saved).not.toContain('topics-v1');
    expect(saved).not.toContain('Topics Menu Page');
    expect(store.templates[0].page_style).toBe('topic');
    expect(store.templates[0].items.map((item) => item.label))
      .toEqual(['Splash', 'Jump in', 'Too cold']);

    // The next launch, against a different page set, reuses it.
    await page.locator('#templates-dialog button[value="close"]').click();
    await mockTD(page, {
      status: defaultStatus({ pages: ['Activities'], grid: { cols: 4, rows: 3 } }),
      layout: defaultLayout('Activities', {
        grid: { cols: 4, rows: 3 },
        free_slots: Array.from({ length: 12 }, (_, index) => index),
        fingerprint: 'activities-v1',
      }),
    });
    await newItems(page, 'Pool');
    await openTemplates(page);
    await page.locator('#template-list button[aria-label="Use template Swimming"]').click();

    await expect(page.locator('#template-summary')).toContainText('Added 3 buttons from “Swimming”');
    await page.locator('#templates-dialog button[value="close"]').click();
    await expect(page.locator('#chipbox .chip')).toHaveCount(3);
    // The saved page style came with it, so the topic-page rows are back.
    await expect(page.locator('#style-topic')).toHaveAttribute('aria-checked', 'true');
  });

  test('the autosaved draft does not wipe a saved template', async ({ page }) => {
    const store = await mockSettings(page);
    await mockTD(page);

    await existingItems(page);
    await page.locator('#word-input').fill('apple');
    await page.locator('#word-input').press('Enter');
    await openTemplates(page);
    await page.locator('#template-name').fill('Snacks');
    await page.locator('#template-save-btn').click();
    await expect(page.locator('#template-save-hint')).toContainText('Saved “Snacks”');
    await page.locator('#templates-dialog button[value="close"]').click();

    // The draft autosave writes preferences and draft every few seconds and
    // says nothing about templates; the template must still be there after.
    await page.locator('#word-input').fill('pear');
    await page.locator('#word-input').press('Enter');
    await expect.poll(() => store.draft && store.draft.items.length).toBe(2);
    expect(store.templates.map((template) => template.name)).toEqual(['Snacks']);

    await openTemplates(page);
    await expect(page.locator('#template-list li')).toContainText('Snacks');
  });

  test('a template too big for the page names what would not fit', async ({ page }) => {
    await mockSettings(page, {
      templates: [{
        name: 'Swimming',
        page_style: 'words',
        saved_at: 1700000000,
        items: [
          { label: 'Splash', message: null, fn: '', slot: 0, symbol: true, symbol_query: null },
          { label: 'Jump in', message: null, fn: '', slot: 1, symbol: true, symbol_query: null },
          { label: 'Too cold', message: null, fn: '', slot: 2, symbol: true, symbol_query: null },
          { label: 'apple', message: null, fn: '', slot: 3, symbol: true, symbol_query: null },
        ],
      }],
    });
    // One free cell besides the two the template will fill, and "apple" is
    // already on the page.
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating', {
        buttons: [{
          slot: 0, label: 'apple', message: null, function: null, symbol: true,
          editable: false, locked_reason: 'Existing TD Snap button',
        }],
        free_slots: [1, 2],
      }),
    });

    await existingItems(page);
    await openTemplates(page);
    await page.locator('#template-list button[aria-label="Use template Swimming"]').click();

    const summary = page.locator('#template-summary');
    await expect(summary).toContainText('Added 2 buttons from “Swimming”');
    await expect(summary).toContainText('Already on Eating');
    await expect(summary).toContainText('apple');
    await expect(summary).toContainText('Eating does not have room for');
    await expect(summary).toContainText('Too cold');

    await page.locator('#templates-dialog button[value="close"]').click();
    await expect(page.locator('#chipbox .chip')).toHaveCount(2);
    await expect(page.locator('#capacity')).toHaveText('2 added · 0 spaces left');
  });

  test('a template saved on a bigger grid keeps its words and re-slots them', async ({ page }) => {
    await mockSettings(page, {
      templates: [{
        name: 'Swimming',
        page_style: 'words',
        saved_at: 1700000000,
        // Cells from an 8x5 page; none of these exist on a 3x2 one.
        items: [
          { label: 'Splash', message: 'Big splash', fn: '', slot: 31, symbol: true, symbol_query: null },
          { label: 'Jump in', message: null, fn: '', slot: 37, symbol: false, symbol_query: null },
        ],
      }],
    });
    await mockTD(page);

    await existingItems(page);
    await openTemplates(page);
    await page.locator('#template-list button[aria-label="Use template Swimming"]').click();
    await expect(page.locator('#template-summary')).toContainText('Added 2 buttons');
    await page.locator('#templates-dialog button[value="close"]').click();

    await expect(page.locator('#chipbox .chip')).toHaveCount(2);
    await expect(page.locator('#preview .cell.used')).toHaveCount(2);
    // The message and the "no symbol" choice travelled with the words.
    await expect(page.locator('.chip-body').filter({ hasText: 'Splash' }))
      .toHaveAttribute('title', 'Speaks: “Big splash”');
  });

  test('deleting a template removes it for the next launch too', async ({ page }) => {
    const store = await mockSettings(page, {
      templates: [
        { name: 'Swimming', page_style: 'words', saved_at: 1, items: [{ label: 'Splash', message: null, fn: '', slot: null, symbol: true, symbol_query: null }] },
        { name: 'Zoo', page_style: 'words', saved_at: 2, items: [{ label: 'Lion', message: null, fn: '', slot: null, symbol: true, symbol_query: null }] },
      ],
    });
    await mockTD(page);

    await existingItems(page);
    await openTemplates(page);
    // Sorted by name, so Swimming is first and Zoo second.
    await expect(page.locator('#template-list li strong')).toHaveText(['Swimming', 'Zoo']);

    await page.locator('#template-list button[aria-label="Delete template Swimming"]').click();
    await expect(page.locator('#template-list li strong')).toHaveText(['Zoo']);
    await expect(page.locator('#template-save-hint')).toContainText('Deleted “Swimming”');
    expect(store.templates.map((template) => template.name)).toEqual(['Zoo']);
  });

  test('the settings panel names the templates Clear all would throw away', async ({ page }) => {
    await mockSettings(page, {
      templates: [
        { name: 'Zoo', page_style: 'words', saved_at: 2, items: [{ label: 'Lion', message: null, fn: '', slot: null, symbol: true, symbol_query: null }] },
        { name: 'Swimming', page_style: 'words', saved_at: 1, items: [{ label: 'Splash', message: null, fn: '', slot: null, symbol: true, symbol_query: null }] },
      ],
    });
    await mockTD(page);
    await openEditor(page);

    await page.locator('#settings-panel-btn').click();
    await expect(page.locator('#settings-panel')).toBeVisible();
    // Named, and never "Nothing saved yet" while they are on disk.
    await expect(page.locator('#settings-panel-list')).toContainText('Saved templates');
    await expect(page.locator('#settings-panel-list')).toContainText('Swimming, Zoo');

    await page.locator('#settings-clear-btn').click();
    await expect(page.locator('#settings-panel-list')).toContainText('Nothing saved yet');
  });

  test('saving without a name says so instead of saving', async ({ page }) => {
    const store = await mockSettings(page);
    await mockTD(page);

    await existingItems(page);
    await page.locator('#word-input').fill('apple');
    await page.locator('#word-input').press('Enter');
    await openTemplates(page);
    await page.locator('#template-save-btn').click();

    await expect(page.locator('#template-save-hint'))
      .toContainText('Give the template a name');
    await expect(page.locator('#template-name')).toBeFocused();
    expect(store.templates).toEqual([]);
  });

  test('the templates dialog has no serious or critical accessibility violations', async ({ page }) => {
    await mockSettings(page, {
      templates: [{
        name: 'Swimming', page_style: 'words', saved_at: 1,
        items: [{ label: 'Splash', message: null, fn: '', slot: null, symbol: true, symbol_query: null }],
      }],
    });
    await mockTD(page);

    await existingItems(page);
    await openTemplates(page);
    await expect(page.locator('#template-list li')).toContainText('Swimming');

    expect(await blockingViolations(page)).toEqual([]);
  });
});


/* Multi-page batch.
 *
 * A caseload session is rarely one page. What these pin is that queueing does
 * not weaken any of the guarantees a single page has: each queued page carries
 * the payload its own review froze, the batch is reviewed as one list before
 * anything is written, and every queued page is reported on afterwards —
 * including the ones never attempted, which is the failure mode a batch is
 * uniquely able to hide.
 */
test.describe('queueing several pages and applying them together', () => {
  function threePages() {
    return {
      status: defaultStatus({ pages: ['Eating', 'Games', 'Swimming'] }),
      layout: (requested) => defaultLayout(requested || 'Eating'),
    };
  }

  async function composeFor(page, pageName, word) {
    await page.locator('#wizard-items .wizard-back').click();
    await expect(page.locator('#wizard-destination')).toBeVisible();
    await page.locator('#parent-select').selectOption(pageName);
    await page.locator('#wizard-destination .wizard-next').click();
    await expect(page.locator('#wizard-items')).toBeVisible();
    await page.locator('#word-input').fill(word);
    await page.locator('#word-input').press('Enter');
    await page.locator('#build-btn').click();
    await expect(page.locator('#step-result')).toBeVisible();
  }

  async function queueFor(page, pageName, word) {
    await composeFor(page, pageName, word);
    await page.locator('#queue-add-btn').click();
    await expect(page.locator('#wizard-items')).toBeVisible();
  }

  test('two queued pages are applied in order and each is reported', async ({ page }) => {
    let submitted = null;
    await mockTD(page, threePages());
    await page.route('**/api/tdsnap/batch', (route) => {
      submitted = route.request().postDataJSON();
      return fulfillJson(route, {
        ok: true,
        applied: 2,
        undo_page: 'Games',
        undo: null,
        results: [
          { page: 'Eating', status: 'applied',
            report: { page: 'Eating', buttons: 1, changed: 0, removed: 0, moved: 0,
                      checks: { td_snap_edit: 'pass', content: 'pass', positions: 'pass' },
                      warnings: [] } },
          { page: 'Games', status: 'applied',
            report: { page: 'Games', buttons: 1, changed: 0, removed: 0, moved: 0,
                      checks: { td_snap_edit: 'pass', content: 'pass', positions: 'pass' },
                      warnings: [] } },
        ],
      });
    });

    await existingItems(page);
    await queueFor(page, 'Eating', 'apple');
    // The queue is visible while the next page is composed, and the chip box
    // was cleared rather than carrying the first page's words along.
    await expect(page.locator('#queue-banner')).toBeVisible();
    await expect(page.locator('#queue-list li')).toHaveCount(1);
    await expect(page.locator('#chipbox .chip')).toHaveCount(0);

    await queueFor(page, 'Games', 'chess');
    await expect(page.locator('#queue-list li')).toHaveCount(2);

    await page.locator('#queue-review-btn').click();
    await expect(page.locator('#step-result')).toBeVisible();
    await expect(page.locator('#result-eyebrow')).toHaveText('Review');
    await expect(page.locator('#review-action')).toContainText('Apply 2 queued pages');
    await expect(page.locator('#review-queue li')).toHaveCount(2);
    await expect(page.locator('#review-queue li').first()).toContainText('Eating');
    // Undo is single-level; the review says so rather than leaving it to be
    // discovered after two pages have been written.
    await expect(page.locator('#review-undo-note')).toContainText('Undo reaches back one page only');

    await page.locator('#confirm-update-btn').click();
    await expect(page.locator('#success-state')).toBeVisible();

    // Each queued page went over as its own entry, in the order queued, with
    // the fingerprint its own review was checked against.
    expect(submitted.entries.map((entry) => entry.page)).toEqual(['Eating', 'Games']);
    expect(submitted.entries[0].items.map((item) => item.label)).toEqual(['apple']);
    expect(submitted.entries[0].fingerprint).toBe('eating-v1');
    expect(submitted.entries[1].fingerprint).toBe('games-v1');

    await expect(page.locator('#result-heading')).toContainText('2 pages were updated');
    await expect(page.locator('#batch-outcome li')).toHaveCount(2);
    await expect(page.locator('#batch-outcome li').first()).toContainText('Applied');
    // The queue is spent, not silently still holding the pages just written.
    await expect(page.locator('#queue-banner')).toBeHidden();
  });

  test('a page that could not be applied is named, and so is the one never tried', async ({ page }) => {
    await mockTD(page, threePages());
    await page.route('**/api/tdsnap/batch', (route) => fulfillJson(route, {
      ok: true,
      applied: 1,
      undo_page: 'Eating',
      undo: null,
      results: [
        { page: 'Eating', status: 'applied',
          report: { page: 'Eating', buttons: 1, changed: 0, removed: 0, moved: 0,
                    checks: { td_snap_edit: 'pass', content: 'pass', symbols: 'partial' },
                    warnings: ['TD Snap found no symbol for “apple”.'] } },
        { page: 'Games', status: 'failed',
          error: 'TD Snap did not verify it. The original page was restored.' },
        { page: 'Swimming', status: 'skipped' },
      ],
    }));

    await existingItems(page);
    await queueFor(page, 'Eating', 'apple');
    await queueFor(page, 'Games', 'chess');
    await queueFor(page, 'Swimming', 'splash');
    await page.locator('#queue-review-btn').click();
    await page.locator('#confirm-update-btn').click();
    await expect(page.locator('#success-state')).toBeVisible();

    await expect(page.locator('#result-eyebrow')).toHaveText('Partly complete');
    await expect(page.locator('#result-heading')).toContainText('1 of 3 pages were applied');
    const outcome = page.locator('#batch-outcome li');
    await expect(outcome).toHaveCount(3);
    await expect(outcome.nth(1)).toContainText('put back the way it was');
    await expect(outcome.nth(1)).toContainText('The original page was restored');
    // The page nobody touched says so, rather than being left off the list.
    await expect(outcome.nth(2)).toContainText('Swimming');
    await expect(outcome.nth(2)).toContainText('Not attempted');
    // A warning stays attached to the page that raised it.
    await expect(page.locator('#result-warnings')).toContainText('Eating: TD Snap found no symbol');
    // One page's partial check is not hidden behind the other page's pass.
    await expect(page.locator('#checks li.warning')).toContainText('needs review');
  });

  test('a page already in the queue cannot be queued twice, and says why', async ({ page }) => {
    await mockTD(page, threePages());

    await existingItems(page);
    await queueFor(page, 'Eating', 'apple');
    await composeFor(page, 'Eating', 'pear');

    await expect(page.locator('#queue-add-btn')).toBeHidden();
    await expect(page.locator('#queue-add-note'))
      .toContainText('“Eating” is already in the queue');
    // Applying this one page on its own is still available.
    await expect(page.locator('#confirm-update-btn')).toBeVisible();
  });

  test('a queued page can be taken back out', async ({ page }) => {
    await mockTD(page, threePages());

    await existingItems(page);
    await queueFor(page, 'Eating', 'apple');
    await queueFor(page, 'Games', 'chess');
    await expect(page.locator('#queue-list li')).toHaveCount(2);

    await page.locator('#queue-list button[aria-label="Remove Eating from the queue"]').click();
    await expect(page.locator('#queue-list li')).toHaveCount(1);
    await expect(page.locator('#queue-list li')).toContainText('Games');
    await expect(page.locator('#queue-review-btn')).toHaveText('Review and apply 1 page');
  });

  test('work left in the chip box is named as not being in the batch', async ({ page }) => {
    await mockTD(page, threePages());

    await existingItems(page);
    await queueFor(page, 'Eating', 'apple');
    // Compose something for another page but do not queue it.
    await page.locator('#wizard-items .wizard-back').click();
    await page.locator('#parent-select').selectOption('Games');
    await page.locator('#wizard-destination .wizard-next').click();
    await page.locator('#word-input').fill('chess');
    await page.locator('#word-input').press('Enter');

    await page.locator('#queue-review-btn').click();
    await expect(page.locator('#review-undo-note'))
      .toContainText('Not in this batch, and not applied by it');
    await expect(page.locator('#review-undo-note')).toContainText('Games');
  });

  test('the queue is not offered where a batch cannot be applied', async ({ page }) => {
    // Creating a new page is not an edit to an existing one, so there is
    // nothing to batch — the button must not promise otherwise.
    await mockTD(page, threePages());

    await newItems(page, 'Dinosaurs');
    await page.locator('#word-input').fill('Roar');
    await page.locator('#word-input').press('Enter');
    await page.locator('#build-btn').click();
    await expect(page.locator('#step-result')).toBeVisible();
    await expect(page.locator('#queue-add-btn')).toBeHidden();
    await expect(page.locator('#queue-add-note')).toBeHidden();
  });

  test('quitting with pages queued warns that they would be lost', async ({ page }) => {
    // The queue is held only in this tab and deliberately not autosaved: every
    // entry carries a live fingerprint that would be stale on the next launch.
    // So losing it has to be hard, which is what this guards.
    await mockTD(page, threePages());
    await existingItems(page);
    await queueFor(page, 'Eating', 'apple');

    let asked = "";
    page.on('dialog', (dialog) => {
      asked = dialog.message();
      return dialog.dismiss();
    });
    await page.locator('#quit-btn').click();
    await expect.poll(() => asked).toContain('1 page queued but not yet applied');
    // Dismissed, so the app is still running and the queue is still there.
    await expect(page.locator('#queue-list li')).toHaveCount(1);
  });

  test('the batch review has no serious or critical accessibility violations', async ({ page }) => {
    await mockTD(page, threePages());

    await existingItems(page);
    await queueFor(page, 'Eating', 'apple');
    await queueFor(page, 'Games', 'chess');
    await page.locator('#queue-review-btn').click();
    await expect(page.locator('#review-queue li')).toHaveCount(2);

    expect(await blockingViolations(page)).toEqual([]);
  });
});

/* Steering the AI, and the model behind it (ROADMAP Phase 6).
 *
 * Suggestions used to be one shot, N items, take it or leave it. What these
 * pin is that every steer is visible and that none of it leaves the machine:
 * a rejected suggestion comes back as "not this", a kept one can ask for more
 * of its kind, style samples describe how the page set already writes a
 * button, and the Wikipedia lookup — the only outbound request the app makes —
 * is named, refusable, and never carries any of it.
 */
test.describe('steerable AI suggestions', () => {
  const READY_STATUS = {
    ok: true,
    ollama: { reachable: true, models: ['llama3.2'] },
    local: {
      engine_available: false,
      downloaded: false,
      selected: 'small',
      memory_bytes: 8 * 1024 ** 3,
      memory_measured: true,
      choices: [],
      model: { key: 'small', name: 'Local', size: '1 GB', license: 'Apache-2.0' },
      download: { status: 'idle' },
    },
  };

  /* Answer every AI request, recording what was asked. `replies` is consumed
     one generation at a time so a test can say what the second round returns. */
  async function mockAi(page, replies, { status = READY_STATUS } = {}) {
    const asked = [];
    const queue = [...replies];
    await page.route('**/api/ai/status*', (route) => fulfillJson(route, status));
    await page.route('**/api/ai/words', (route) => {
      asked.push(route.request().postDataJSON());
      const reply = queue.length > 1 ? queue.shift() : queue[0];
      return fulfillJson(route, { ok: true, engine: 'ollama', ...reply });
    });
    return asked;
  }

  async function openPanel(page) {
    await page.locator('.more-options > summary').click();
    await page.locator('#ai-suggest > summary').click();
    await expect(page.locator('#ai-go')).toBeEnabled();
  }

  async function suggestInto(page, title = 'Snacks') {
    await newItems(page, title);
    await openPanel(page);
    await page.locator('#ai-go').click();
  }

  test('a rejected suggestion is not offered again', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    const asked = await mockAi(page, [{ words: ['Kale', 'Chips'] }]);

    await suggestInto(page);
    await expect(page.locator('#chipbox .chip')).toHaveCount(2);
    // Nothing was rejected yet, so the first ask carried no negative
    // constraints at all.
    expect(asked[0].avoid).toEqual([]);

    await page.locator('#chipbox .chip', { hasText: 'Kale' })
      .getByRole('button', { name: 'Remove Kale' }).click();
    await page.locator('#ai-go').click();

    expect(asked[1].avoid).toEqual(['Kale']);
    // The page's own words are a different kind of "don't repeat" and stay
    // where they were.
    expect(asked[1].existing).toContain('Chips');
  });

  test('a word the user typed is never treated as a rejected suggestion', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    const asked = await mockAi(page, [{ words: ['Chips'] }]);

    await newItems(page, 'Snacks');
    await page.locator('#word-input').fill('Pretzel');
    await page.locator('#word-add-btn').click();
    await page.locator('#chipbox .chip', { hasText: 'Pretzel' })
      .getByRole('button', { name: 'Remove Pretzel' }).click();
    await openPanel(page);
    await page.locator('#ai-go').click();

    expect(asked[0].avoid).toEqual([]);
  });

  test('one suggestion is swapped for another, in place', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    const asked = await mockAi(page, [
      { words: ['Kale', 'Chips'] },
      { words: ['Chips', 'Popcorn'] },
    ]);

    await suggestInto(page);
    const kale = page.locator('#chipbox .chip', { hasText: 'Kale' });
    await kale.getByRole('button', { name: /^Edit Kale/ }).click();
    await expect(page.locator('#edit-ai-field')).toBeVisible();
    await page.locator('#edit-ai-regenerate').click();

    // Replaced where it sat, and the one it replaced counts as rejected.
    await expect(page.locator('#chipbox .chip')).toHaveCount(2);
    await expect(page.locator('#chipbox')).toContainText('Popcorn');
    await expect(page.locator('#chipbox')).not.toContainText('Kale');
    // The word being replaced is a "not this" for the regenerate request
    // itself, and a remembered one for every request after it.
    expect(asked[1].avoid).toEqual(['Kale']);
    await page.locator('#ai-go').click();
    expect(asked[2].avoid).toEqual(['Kale']);
    // ... and it is undoable like any other removal.
    await page.locator('#undo-remove-btn').click();
    await expect(page.locator('#chipbox')).toContainText('Kale');
  });

  test('"more like this" asks for more of one kind', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    const asked = await mockAi(page, [
      { words: ['Chips'] },
      { words: ['Pretzels', 'Popcorn'] },
    ]);

    await suggestInto(page);
    await page.locator('#chipbox .chip', { hasText: 'Chips' })
      .getByRole('button', { name: /^Edit Chips/ }).click();
    await page.locator('#edit-ai-more').click();

    expect(asked[1].like).toEqual(['Chips']);
    await expect(page.locator('#chipbox .chip')).toHaveCount(3);
    await expect(page.locator('#ai-status')).toContainText('more like “Chips”');
  });

  test('the per-item controls belong to suggestions, not to typed words', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    await mockAi(page, [{ words: ['Chips'] }]);

    await newItems(page, 'Snacks');
    await page.locator('#word-input').fill('Pretzel');
    await page.locator('#word-add-btn').click();
    await page.locator('#chipbox .chip', { hasText: 'Pretzel' })
      .getByRole('button', { name: /^Edit Pretzel/ }).click();
    await expect(page.locator('#edit-ai-field')).toBeHidden();
    await page.locator('#chip-editor button[value="cancel"]').click();

    // A suggestion the user renames becomes their word, and stops offering to
    // regenerate something they already decided on.
    await openPanel(page);
    await page.locator('#ai-go').click();
    await page.locator('#chipbox .chip', { hasText: 'Chips' })
      .getByRole('button', { name: /^Edit Chips/ }).click();
    await expect(page.locator('#edit-ai-field')).toBeVisible();
    await page.locator('#edit-label').fill('Crisps');
    await page.locator('#edit-save').click();
    await page.locator('#chipbox .chip', { hasText: 'Crisps' })
      .getByRole('button', { name: /^Edit Crisps/ }).click();
    await expect(page.locator('#edit-ai-field')).toBeHidden();
  });

  test('suggestions are asked to match how the page set already writes', async ({ page }) => {
    await page.route('**/api/tdsnap/vocabulary', (route) => fulfillJson(route, {
      ok: true,
      available: true,
      labels: { 'i want more': ['Core Words'] },
      samples: ['I want more', 'All done'],
    }));
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating', {
        buttons: [{ slot: 0, label: 'Eggs' }],
        free_slots: [1, 2, 3, 4, 5],
      }),
    });
    const asked = await mockAi(page, [{ words: ['Chips'] }]);

    await existingItems(page);
    await openPanel(page);
    await page.locator('#ai-go').click();

    // The page being edited leads, then the rest of the page set.
    expect(asked[0].style).toEqual(['Eggs', 'I want more', 'All done']);

    // Turning it off means the prompt says nothing about style at all.
    await page.locator('#ai-style').uncheck();
    await page.locator('#ai-go').click();
    expect(asked[1].style).toEqual([]);
  });

  test('the reference article is named, and can be refused', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    const asked = await mockAi(page, [{
      words: ['Quicksilver'],
      grounding: {
        used: true,
        title: 'Mercury (element)',
        url: 'https://en.wikipedia.org/wiki/Mercury_(element)',
        alternatives: ['Mercury (planet)'],
      },
    }]);

    await newItems(page, 'Mercury');
    await openPanel(page);
    await page.locator('#ai-grounding').check();
    await page.locator('#ai-go').click();

    const source = page.locator('#ai-grounding-source');
    await expect(source).toBeVisible();
    await expect(page.locator('#ai-grounding-link')).toHaveText('Mercury (element)');
    await expect(page.locator('#ai-grounding-link'))
      .toHaveAttribute('href', 'https://en.wikipedia.org/wiki/Mercury_(element)');

    await page.locator('#ai-grounding-pick').selectOption('Mercury (planet)');
    await expect(page.locator('#ai-grounding-note'))
      .toContainText('Suggest again to use “Mercury (planet)”');
    // Refusing arms the next request rather than silently throwing away
    // suggestions the user may already have edited.
    await expect(page.locator('#chipbox .chip')).toHaveCount(1);

    await page.locator('#ai-go').click();
    expect(asked[1].grounding_title).toBe('Mercury (planet)');
    expect(asked[1].grounding_exclude).toEqual(['Mercury (element)']);
  });

  test('refusing every article turns the lookup off rather than guessing', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    const asked = await mockAi(page, [{
      words: ['Quicksilver'],
      grounding: {
        used: true, title: 'Mercury (element)',
        url: 'https://en.wikipedia.org/wiki/Mercury_(element)', alternatives: [],
      },
    }]);

    await newItems(page, 'Mercury');
    await openPanel(page);
    await page.locator('#ai-grounding').check();
    await page.locator('#ai-go').click();
    await page.locator('#ai-grounding-pick').selectOption('none');

    await expect(page.locator('#ai-grounding')).not.toBeChecked();
    await page.locator('#ai-go').click();
    expect(asked[1].grounding).toBe(false);
  });

  test('nothing the user composed is offered to the reference lookup', async ({ page }) => {
    /* The browser cannot see what the server sends to Wikipedia, so what this
       pins is the half it owns: the request that carries style samples and
       rejections carries only the page title as the thing to look up. The
       server side is pinned in tests/test_ai.py. */
    await page.route('**/api/tdsnap/vocabulary', (route) => fulfillJson(route, {
      ok: true, available: true, labels: {}, samples: ['I want more'],
    }));
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    const asked = await mockAi(page, [{ words: ['Kale'] }]);

    await newItems(page, 'Snacks');
    await openPanel(page);
    await page.locator('#ai-grounding').check();
    await page.locator('#ai-go').click();
    await page.locator('#chipbox .chip', { hasText: 'Kale' })
      .getByRole('button', { name: 'Remove Kale' }).click();
    await page.locator('#ai-go').click();

    const request = asked[1];
    expect(request.category).toBe('Snacks');
    expect(request.grounding).toBe(true);
    expect(request.avoid).toEqual(['Kale']);
    expect(request.style).toContain('I want more');
    // The only article-shaped fields are article titles this app was told
    // about, never the user's own words.
    expect(request.grounding_title).toBeNull();
    expect(request.grounding_exclude).toEqual([]);
  });

  test('a bigger model is offered only where the machine was measured to hold it', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    await mockAi(page, [{ words: ['Chips'] }], {
      status: {
        ok: true,
        ollama: { reachable: false, models: [] },
        local: {
          engine_available: true,
          downloaded: false,
          selected: 'small',
          memory_bytes: 8 * 1024 ** 3,
          memory_measured: true,
          download: { status: 'idle' },
          model: { key: 'small', name: 'Small', size: '1 GB', license: 'Apache-2.0' },
          choices: [
            {
              key: 'small', name: 'Small', license: 'Apache-2.0', size: '1 GB',
              summary: 'Runs on a clinic laptop.', downloaded: false,
              supported: true, reason: '',
            },
            {
              key: 'large', name: 'Large', license: 'Apache-2.0', size: '4.7 GB',
              summary: 'Better on niche topics.', downloaded: false,
              supported: false,
              reason: 'This computer has about 8 GB of memory; Large needs about 16 GB.',
            },
          ],
        },
      },
    });

    await newItems(page, 'Snacks');
    await page.locator('.more-options > summary').click();
    await page.locator('#ai-suggest > summary').click();

    const row = page.locator('#ai-model-choice-row');
    await expect(row).toBeVisible();
    // Present but unpickable, with the measured reason said out loud rather
    // than the option quietly missing.
    await expect(page.locator('#ai-model-choice option[value="large"]')).toBeDisabled();
    await expect(page.locator('#ai-model-choice')).toHaveValue('small');
    await expect(page.locator('#ai-model-choice-note')).toContainText('needs about 16 GB');
  });

  test('a single built-in model shows no picker at all', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    await mockAi(page, [{ words: ['Chips'] }], {
      status: {
        ok: true,
        ollama: { reachable: false, models: [] },
        local: {
          engine_available: true, downloaded: false, selected: 'small',
          memory_bytes: 0, memory_measured: false,
          download: { status: 'idle' },
          model: { key: 'small', name: 'Small', size: '1 GB', license: 'Apache-2.0' },
          choices: [{
            key: 'small', name: 'Small', license: 'Apache-2.0', size: '1 GB',
            summary: 'Runs on a clinic laptop.', downloaded: false,
            supported: true, reason: '',
          }],
        },
      },
    });

    await newItems(page, 'Snacks');
    await page.locator('.more-options > summary').click();
    await page.locator('#ai-suggest > summary').click();
    await expect(page.locator('#ai-model-choice-row')).toBeHidden();
  });

  test('the steering controls have no serious or critical accessibility violations', async ({ page }) => {
    await mockTD(page, {
      status: defaultStatus({ pages: ['Eating'] }),
      layout: defaultLayout('Eating'),
    });
    await mockAi(page, [{
      words: ['Kale'],
      grounding: {
        used: true, title: 'Snack', url: 'https://en.wikipedia.org/wiki/Snack',
        alternatives: ['Snack food'],
      },
    }]);

    await newItems(page, 'Snacks');
    await openPanel(page);
    await page.locator('#ai-grounding').check();
    await page.locator('#ai-go').click();
    await page.locator('#chipbox .chip', { hasText: 'Kale' })
      .getByRole('button', { name: /^Edit Kale/ }).click();
    await expect(page.locator('#edit-ai-field')).toBeVisible();

    expect(await blockingViolations(page)).toEqual([]);
  });
});
