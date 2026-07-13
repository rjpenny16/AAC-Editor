const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.TDSNAP_WEB_URL || 'http://localhost:8765';

test('live editor recommends placement, reorders topic rows, and sends a live-only edit', async ({ page }) => {
  let submitted = null;
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true,
      available: true,
      running: true,
      unlocked: true,
      page: 'Topics Menu Page',
      grid: { cols: 10, rows: 5 },
      pages: ['Topics Menu Page', 'Eating', 'Games', 'About Me', 'Classroom'],
    }),
  }));
  await page.route('**/api/tdsnap/page', async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        page: 'Snacks',
        parent: 'Eating',
        buttons: 2,
        checks: {
          td_snap_edit: 'pass',
          navigation: 'pass',
          content: 'pass',
          symbols: 'pass',
          topic_format: 'pass',
        },
        warnings: [],
      }),
    });
  });
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Topics Menu Page', grid: { cols: 10, rows: 5 },
      buttons: [], free_slots: Array.from({ length: 50 }, (_, index) => index),
      fingerprint: 'topics-v1',
    }),
  }));

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#step-build')).toBeVisible();

  await page.locator('#operation-new').click();

  await page.locator('#build-btn').click();
  await expect(page.locator('#build-error')).toContainText('Give the new page a title.');

  await page.locator('#title-input').fill('Snacks');
  await expect(page.locator('#build-error')).toBeHidden();
  await expect(page.locator('#placement-title')).toContainText('Eating');
  await expect(page.locator('#parent-select')).toHaveValue('Eating');
  await expect(page.locator('#use-placement')).toBeHidden();

  await page.locator('#style-topic').click();
  await page.locator('#word-input').fill('More please');
  await page.locator('#word-input').press('Enter');
  await page.locator('#word-input').fill('No thanks');
  await page.locator('#word-input').press('Enter');

  const first = page.locator('#preview .cell.used').filter({ hasText: 'More please' });
  const target = page.locator('#preview .cell[data-slot="20"]');
  await first.dragTo(target);
  await expect(target).toContainText('More please');
  await page.locator('#build-btn').click();

  await expect(page.locator('#step-result')).toBeVisible();
  await expect(page.locator('#result-heading')).toContainText('TD Snap updated');
  await expect(page.locator('#checks li')).toHaveCount(5);
  await expect(page.locator('#live-result-note')).toBeVisible();
  expect(submitted.parent).toBe('Eating');
  expect(submitted.items.find((item) => item.label === 'More please')).toMatchObject({
    slot: 20,
    symbol: true,
    border_color: '#43A047',
  });
});

test('detected page filter can always be cleared', async ({ page }) => {
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      ok: true,
      available: true,
      running: true,
      unlocked: true,
      page: 'Topics Menu Page',
      grid: { cols: 10, rows: 5 },
      pages: ['Topics Menu Page', 'Eating', 'Games'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ ok: true, page: 'Topics Menu Page', grid: { cols: 10, rows: 5 }, buttons: [], free_slots: [], fingerprint: 'v1' }),
  }));
  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await page.locator('#parent-filter').fill('Eating');
  await expect(page.locator('#parent-select option')).toHaveCount(1);
  await page.locator('#parent-filter-clear').click();
  await expect(page.locator('#parent-select option')).toHaveCount(3);
  await expect(page.locator('#parent-filter')).toHaveValue('');
});

test('adds words to exact empty cells on an existing page without creating a page', async ({ page }) => {
  let submitted = null;
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Eating', grid: { cols: 3, rows: 2 }, pages: ['Eating', 'Places'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Eating', grid: { cols: 3, rows: 2 },
      buttons: [{ slot: 0, label: 'Apple' }, { slot: 2, label: 'Drink' }],
      free_slots: [1, 3, 4, 5], fingerprint: 'eating-v1',
    }),
  }));
  await page.route('**/api/tdsnap/edit-plan', async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, page: 'Eating', buttons: 2, warnings: [],
        checks: { td_snap_edit: 'pass', target_page: 'pass', content: 'pass', positions: 'pass' },
      }),
    });
  });

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#operation-existing')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#preview .cell.existing')).toHaveCount(2);
  await page.locator('#word-input').fill('Pizza, Pasta');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();

  await expect(page.locator('#step-result')).toBeVisible();
  expect(submitted.operation).toBe('add_to_existing_page');
  expect(submitted.page).toBe('Eating');
  expect(submitted.fingerprint).toBe('eating-v1');
  expect(submitted.items.map((item) => item.slot)).toEqual([1, 3]);
});

test('repeat edit refreshes occupied cells and fingerprint before another submission', async ({ page }) => {
  const layouts = [];
  const submissions = [];
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Eating', grid: { cols: 3, rows: 2 }, pages: ['Eating', 'Places'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => {
    const requested = new URL(route.request().url()).searchParams.get('page');
    layouts.push(requested);
    const places = requested === 'Places';
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, page: requested, grid: { cols: 3, rows: 2 },
        buttons: [{ slot: places ? 2 : 0, label: places ? 'School' : 'Apple' }],
        free_slots: places ? [0, 1, 3, 4, 5] : [1, 2, 3, 4, 5],
        fingerprint: places ? 'places-v1' : 'eating-v2',
      }),
    });
  });
  await page.route('**/api/tdsnap/edit-plan', async (route) => {
    submissions.push(route.request().postDataJSON());
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, buttons: 1, checks: {
          td_snap_edit: 'pass', target_page: 'pass', content: 'pass', positions: 'pass',
        }, warnings: [],
      }),
    });
  });

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await page.locator('#word-input').fill('Pizza');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await expect(page.locator('#step-result')).toBeVisible();

  await page.locator('#another-btn').click();
  await expect(page.locator('#step-build')).toBeVisible();
  await expect(page.locator('#preview .cell.existing')).toHaveText('Apple');
  await page.locator('#parent-select').selectOption('Places');
  await expect(page.locator('#preview .cell.existing')).toHaveText('School');
  await page.locator('#word-input').fill('Park');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await expect(page.locator('#step-result')).toBeVisible();

  await page.locator('#another-btn').click();
  await expect(page.locator('#parent-select')).toHaveValue('Places');
  await expect(page.locator('#preview .cell.existing')).toHaveText('School');

  expect(layouts).toEqual(['Eating', 'Eating', 'Places', 'Places']);
  expect(submissions).toHaveLength(2);
  expect(submissions[1]).toMatchObject({ page: 'Places', fingerprint: 'places-v1' });
});

test('existing labels are de-duplicated case-insensitively and capacity is enforced', async ({ page }) => {
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Eating', grid: { cols: 2, rows: 1 }, pages: ['Eating'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Eating', grid: { cols: 2, rows: 1 },
      buttons: [{ slot: 0, label: 'Apple' }], free_slots: [1], fingerprint: 'eating-v1',
    }),
  }));

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await page.locator('#word-input').fill('apple, Banana, Cherry');
  await page.locator('#word-input').press('Enter');

  await expect(page.locator('#chipbox .chip')).toHaveCount(1);
  await expect(page.locator('#chipbox .chip-body')).toContainText('Banana');
  await expect(page.locator('#chip-note')).toContainText('1 duplicate skipped');
  await expect(page.locator('#chip-note')).toContainText("1 word didn't fit");
  await expect(page.locator('#word-input')).toBeDisabled();
  await expect(page.locator('#capacity')).toHaveText('1 of 1 cells');
});

test('button editor validates labels and preserves spoken phrase and color', async ({ page }) => {
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Eating', grid: { cols: 3, rows: 2 }, pages: ['Eating'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Eating', grid: { cols: 3, rows: 2 },
      buttons: [], free_slots: [0, 1, 2, 3, 4, 5], fingerprint: 'eating-v1',
    }),
  }));

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await page.locator('#word-input').fill('Hello, Goodbye');
  await page.locator('#word-input').press('Enter');
  await page.locator('#chipbox .chip-body').filter({ hasText: 'Hello' }).click();
  await page.locator('#edit-label').fill('Goodbye');
  await page.locator('#edit-save').click();
  await expect(page.locator('#chip-editor')).toBeVisible();
  await expect(page.locator('#edit-label')).toHaveJSProperty('validationMessage', 'Each button needs a unique label.');

  await page.locator('#edit-label').fill('Greeting');
  await page.locator('#edit-message').fill('Hello, it is good to see you');
  await page.locator('#edit-fn-row [data-fn="personal"]').click();
  await page.locator('#edit-save').click();
  await expect(page.locator('#chip-editor')).toBeHidden();
  const greeting = page.locator('#chipbox .chip-body').filter({ hasText: 'Greeting' });
  await expect(greeting).toHaveAttribute('aria-label', /Personal.*speaks/);
  await expect(page.locator('#preview .cell.used').filter({ hasText: 'Greeting' })).toHaveClass(/coded/);
});

test('radio groups and preview support keyboard-only operation', async ({ page }) => {
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Topics Menu Page', grid: { cols: 3, rows: 2 }, pages: ['Topics Menu Page'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Topics Menu Page', grid: { cols: 3, rows: 2 }, buttons: [],
      free_slots: [0, 1, 2, 3, 4, 5], fingerprint: 'topics-v1',
    }),
  }));

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await page.locator('#operation-existing').focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#operation-new')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#title-field')).toBeVisible();
  await page.locator('#style-words').focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#style-topic')).toHaveAttribute('aria-checked', 'true');
  await page.locator('#word-input').fill('How are you?, Great');
  await page.locator('#word-input').press('Enter');
  const first = page.locator('#preview .cell.used').filter({ hasText: 'How are you?' });
  await first.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#preview .cell.used').filter({ hasText: 'How are you?' }))
    .toHaveAttribute('aria-label', /column 2/);
});

test('layout errors are visible and a later page selection can recover', async ({ page }) => {
  let placesAttempts = 0;
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Eating', grid: { cols: 3, rows: 2 }, pages: ['Eating', 'Places'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => {
    const requested = new URL(route.request().url()).searchParams.get('page');
    if (requested === 'Places' && ++placesAttempts === 1) {
      return route.fulfill({
        status: 400, contentType: 'application/json',
        body: JSON.stringify({ ok: false, error: 'TD Snap changed pages during inspection.' }),
      });
    }
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, page: requested, grid: { cols: 3, rows: 2 }, buttons: [],
        free_slots: [0, 1, 2, 3, 4, 5], fingerprint: `${requested}-v1`,
      }),
    });
  });

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await page.locator('#parent-select').selectOption('Places');
  await expect(page.locator('#build-error')).toContainText("Couldn’t load the selected TD Snap page.");
  await expect(page.locator('#parent-capacity')).toContainText('could not be loaded');
  await page.locator('#parent-select').selectOption('Eating');
  await page.locator('#parent-select').selectOption('Places');
  await expect(page.locator('#build-error')).toBeHidden();
  await expect(page.locator('#parent-capacity')).toContainText('6 empty cells');
  expect(errors).toEqual([]);
});

test('partial automation checks are presented as review notes', async ({ page }) => {
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Eating', grid: { cols: 2, rows: 2 }, pages: ['Eating'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Eating', grid: { cols: 2, rows: 2 }, buttons: [],
      free_slots: [0, 1, 2, 3], fingerprint: 'eating-v1',
    }),
  }));
  await page.route('**/api/tdsnap/edit-plan', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, buttons: 1,
      checks: { td_snap_edit: 'pass', content: 'pass', symbols: 'partial' },
      warnings: ['TD Snap could not find a symbol for 1 button.'],
    }),
  }));

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await page.locator('#word-input').fill('Unusualword');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await expect(page.locator('#checks li.warning')).toContainText('Matching symbols');
  await expect(page.locator('#checks li.warning')).toContainText('needs review');
  await expect(page.locator('#result-warnings')).toContainText('could not find a symbol');
  await expect(page.locator('#result-heading')).toBeFocused();
});

test('mobile layout stays inside the viewport while the grid scrolls locally', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Topics Menu Page', grid: { cols: 10, rows: 5 }, pages: ['Topics Menu Page'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Topics Menu Page', grid: { cols: 10, rows: 5 }, buttons: [],
      free_slots: Array.from({ length: 50 }, (_, index) => index), fingerprint: 'topics-v1',
    }),
  }));

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  const sizes = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    previewClient: document.querySelector('#preview').clientWidth,
    previewScroll: document.querySelector('#preview').scrollWidth,
  }));
  expect(sizes.document).toBeLessThanOrEqual(sizes.viewport);
  expect(sizes.previewScroll).toBeGreaterThan(sizes.previewClient);
  const buildWidth = await page.locator('#build-btn').evaluate((el) => el.getBoundingClientRect().width);
  expect(buildWidth).toBeGreaterThan(300);
});

test('real TD Snap edit is explicit opt-in', async ({ page }) => {
  test.skip(
    process.env.TDSNAP_LIVE_E2E !== '1',
    'set TDSNAP_LIVE_E2E=1 to add a real Playwright Test page to the open TD Snap set',
  );

  await page.goto(BASE_URL);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#step-build')).toBeVisible({ timeout: 10_000 });
  await page.locator('#operation-new').click();
  await page.locator('#title-input').fill('Playwright Test');
  await page.locator('#word-input').fill('hello');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await expect(page.locator('#step-result')).toBeVisible({ timeout: 30_000 });
});
