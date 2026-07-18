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
    'Couldn’t load the selected TD Snap page.',
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
