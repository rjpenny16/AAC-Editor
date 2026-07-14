const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.TDSNAP_WEB_URL || 'http://localhost:8765';

async function openEditor(page) {
  await page.goto(BASE_URL);
  await expect(page.locator('#step-load')).toBeVisible();
}

test('connect opens TD Snap when it is not already running', async ({ page }) => {
  let checks = 0;
  let launches = 0;
  let releaseFirstStatus;
  const firstStatusGate = new Promise((resolve) => { releaseFirstStatus = resolve; });
  await page.route('**/api/tdsnap/status', async (route) => {
    checks += 1;
    if (checks === 1) await firstStatusGate;
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(checks === 1
        ? { ok: true, available: true, running: false, unlocked: true }
        : {
            ok: true, available: true, running: true, unlocked: true,
            page: 'Topics Menu Page', grid: { cols: 5, rows: 5 },
            pages: ['Topics Menu Page'],
          }),
    });
  });
  await page.route('**/api/tdsnap/launch', (route) => {
    launches += 1;
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ ok: true, launched: true }),
    });
  });
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Topics Menu Page', grid: { cols: 5, rows: 5 }, buttons: [],
      free_slots: Array.from({ length: 25 }, (_, index) => index), fingerprint: 'v1',
    }),
  }));

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#app-activity')).toBeVisible();
  await expect(page.locator('#app-activity')).toContainText('Checking for TD Snap');
  await expect(page.locator('#live-connect-btn')).toHaveAttribute('aria-busy', 'true');
  releaseFirstStatus();
  await expect(page.locator('#step-build')).toBeVisible();
  await expect(page.locator('#app-activity')).toBeHidden();
  await expect(page.locator('#live-connect-btn')).toHaveAttribute('aria-busy', 'false');
  expect(launches).toBe(1);
});

test('onboarding is keyboard-ready, ephemeral, and tailors the editor', async ({ page }) => {
  await page.goto(BASE_URL);
  await page.locator('#settings-btn').click();
  await expect(page.locator('#step-welcome')).toBeVisible();
  await expect(page.locator('#step-load')).toBeHidden();
  await expect(page.locator('.workflow-rail')).toBeHidden();
  await expect(page.locator('#welcome-heading')).toBeFocused();
  await expect(page.locator('.welcome-question:visible')).toHaveCount(1);
  await expect(page.locator('.welcome-question:visible [role="radio"]')).toHaveCount(2);
  await expect(page.locator('#welcome-heading')).toHaveText('How would you like to begin?');

  await page.locator('#profile-aac-guided').hover();
  await expect(page.locator('#profile-aac-guided .welcome-choice-context')).toHaveCSS('opacity', '1');

  await page.locator('#profile-aac-guided').focus();
  await page.locator('#profile-aac-guided').press('ArrowRight');
  await expect(page.locator('#profile-aac-standard')).toHaveAttribute('aria-checked', 'true');
  await page.locator('#welcome-start').click();
  await expect(page.locator('#welcome-heading')).toHaveText('Would you like local AI suggestions?');
  await expect(page.locator('.welcome-question:visible [role="radio"]')).toHaveCount(2);
  await page.locator('#profile-ai-assist').click();
  await page.locator('#welcome-start').click();
  await expect(page.locator('#welcome-heading')).toHaveText('How familiar is this workspace?');
  await page.locator('#profile-layout-familiar').click();
  await page.locator('#welcome-start').click();

  await expect(page.locator('#step-load')).toBeVisible();
  await expect(page.locator('body')).toHaveClass(/layout-familiar/);
  await expect(page.locator('.workflow-item em').first()).toBeHidden();
  await expect(page.locator('#operation-existing')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#style-words')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#ai-suggest')).not.toHaveAttribute('hidden', '');
  await expect(page.locator('.ai-advanced')).not.toHaveAttribute('open', '');
  await expect(page.locator('.ai-settings')).toBeHidden();
  await expect(page.locator('#workflow-tour')).toBeHidden();

  await page.reload();
  await expect(page.locator('#step-load')).toBeVisible();
  await page.locator('#settings-btn').click();
  await expect(page.locator('#step-welcome')).toBeVisible();
  await page.locator('#welcome-start').click();
  await page.locator('#welcome-start').click();
  await page.locator('#welcome-start').click();
  await expect(page.locator('#operation-existing')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#style-words')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('.buttons-hint')).toHaveText('Add one word per button.');
  await expect(page.locator('#preview-legend')).toHaveAttribute('hidden', '');
  await expect(page.locator('#placement-advice')).not.toHaveAttribute('hidden', '');
  await expect(page.locator('#ai-suggest')).toBeHidden();
  await expect(page.locator('#workflow-tour')).toBeVisible();
  await expect(page.locator('.workflow-item[data-step="1"]')).toHaveClass(/tour-current/);
  await page.locator('#workflow-tour-next').click();
  await expect(page.locator('#workflow-tour-title')).toHaveText('Build');
  await expect(page.locator('.workflow-item[data-step="2"]')).toHaveClass(/tour-current/);
  await page.locator('#workflow-tour-next').click();
  await expect(page.locator('#workflow-tour-title')).toHaveText('Review');
  await page.keyboard.press('Escape');
  await expect(page.locator('#workflow-tour')).toBeHidden();
  await expect(page.locator('#live-connect-btn')).toBeFocused();

  await page.reload();
  await page.locator('#settings-btn').click();
  await page.locator('#welcome-skip').click();
  await expect(page.locator('#step-load')).toBeVisible();
  await expect(page.locator('#ai-suggest')).not.toHaveAttribute('hidden', '');
  await expect(page.locator('.ai-advanced')).not.toHaveAttribute('open', '');
  await expect(page.locator('.workflow-item em').first()).toBeHidden();
  await expect(page.locator('#operation-hint')).not.toHaveAttribute('hidden', '');
  await expect(page.locator('#style-hint')).not.toHaveAttribute('hidden', '');
  await expect(page.locator('#workflow-tour')).toBeHidden();
});

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

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#step-build')).toBeVisible();

  await page.locator('#style-topic').click();
  await expect(page.locator('#operation-new')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#title-input')).toBeFocused();

  await page.locator('#build-btn').click();
  await expect(page.locator('#build-error')).toContainText('Give the new page a title.');

  await page.locator('#title-input').fill('Snacks');
  await expect(page.locator('#build-error')).toBeHidden();
  await expect(page.locator('#placement-title')).toContainText('Eating');
  await expect(page.locator('#parent-select')).toHaveValue('Eating');
  await expect(page.locator('#use-placement')).toBeHidden();

  await page.locator('#word-input').fill('More please');
  await page.locator('#word-input').press('Enter');
  await page.locator('#word-input').fill('No thanks');
  await page.locator('#word-input').press('Enter');

  const first = page.locator('#preview .cell.used').filter({ hasText: 'More please' });
  const target = page.locator('#preview .cell[data-slot="20"]');
  await first.dragTo(target);
  await expect(target).toContainText('More please');
  await expect(target).toHaveCSS('border-color', 'rgb(67, 160, 71)');
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
  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await page.locator('#operation-new').click();
  await page.locator('#parent-filter').fill('Eating');
  await expect(page.locator('#parent-select option')).toHaveCount(1);
  await page.locator('#title-input').fill('Games');
  await expect(page.locator('#parent-capacity')).toContainText('Eating');
  await page.locator('#parent-filter-clear').click();
  await expect(page.locator('#parent-select option')).toHaveCount(3);
  await expect(page.locator('#parent-filter')).toHaveValue('');
});

test('live preview follows TD Snap page changes and keeps the full page list', async ({ page }) => {
  let statusCalls = 0;
  await page.route('**/api/tdsnap/status', (route) => {
    statusCalls += 1;
    const current = statusCalls === 1 ? 'Eating' : 'Games';
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, available: true, running: true, unlocked: true,
        page: current, grid: { cols: 2, rows: 2 },
        pages: ['Eating', 'Games', 'Nested Page', 'Topics Menu Page'],
      }),
    });
  });
  await page.route('**/api/tdsnap/page-layout*', (route) => {
    const requested = new URL(route.request().url()).searchParams.get('page');
    const current = requested || 'Games';
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, page: current, grid: { cols: 2, rows: 2 },
        buttons: [{ slot: 0, label: current === 'Games' ? 'Play' : 'Apple' }],
        free_slots: [1, 2, 3], fingerprint: `${current}-v1`,
      }),
    });
  });

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#preview-live-text')).toContainText('Games');
  await expect(page.locator('#parent-select')).toHaveValue('Games');
  await expect(page.locator('#preview .cell.existing')).toContainText('Play');
  await expect(page.locator('#parent-select option')).toHaveCount(4);
});

test('a new topic page is not corrupted by the live monitor following another page', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  let statusCalls = 0;
  await page.route('**/api/tdsnap/status', (route) => {
    statusCalls += 1;
    // After connecting, TD Snap's live page moves to a smaller 2x2 page.
    const small = statusCalls > 1;
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, available: true, running: true, unlocked: true,
        page: small ? 'Eating' : 'Topics Menu Page',
        grid: small ? { cols: 2, rows: 2 } : { cols: 10, rows: 5 },
        pages: ['Topics Menu Page', 'Eating', 'Games'],
      }),
    });
  });
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Topics Menu Page', grid: { cols: 10, rows: 5 }, buttons: [],
      free_slots: Array.from({ length: 50 }, (_, index) => index), fingerprint: 'topics-v1',
    }),
  }));

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#step-build')).toBeVisible();
  await page.locator('#style-topic').click();
  await page.locator('#title-input').fill('Dinosaurs');
  await page.locator('#parent-select').selectOption('Topics Menu Page');
  await page.locator('#word-input').fill('Roar, Stomp, Chomp, Sleep, Run, Hide');
  await page.locator('#word-input').press('Enter');
  await expect(page.locator('#preview .cell.used')).toHaveCount(6);

  // Let the 750ms live monitor fire against the now-2x2 live page.
  await page.waitForTimeout(2000);

  // The new-page design must be intact: all six words, parent unchanged.
  await expect(page.locator('#preview .cell.used')).toHaveCount(6);
  await expect(page.locator('#parent-select')).toHaveValue('Topics Menu Page');
  expect(errors).toEqual([]);
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

  await openEditor(page);
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

test('AI suggestions use the selected existing page and its current buttons', async ({ page }) => {
  let request = null;
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Breakfast Foods', grid: { cols: 3, rows: 2 },
      pages: ['Breakfast Foods', 'Topics Menu Page'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Breakfast Foods', grid: { cols: 3, rows: 2 },
      buttons: [{ slot: 0, label: 'Eggs' }, { slot: 1, label: 'Bacon' }],
      free_slots: [2, 3, 4, 5], fingerprint: 'breakfast-v1',
    }),
  }));
  await page.route('**/api/ai/status*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true,
      ollama: { reachable: true, models: ['llama3.2'] },
      local: {
        engine_available: false, downloaded: false,
        model: { name: 'Local', size: '1 GB', license: 'Apache-2.0' },
        download: { status: 'idle' },
      },
    }),
  }));
  await page.route('**/api/ai/words', async (route) => {
    request = route.request().postDataJSON();
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ ok: true, words: ['Eggs', 'Waffles'], engine: 'ollama' }),
    });
  });

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await page.locator('#ai-suggest > summary').click();
  await expect(page.locator('#ai-go')).toBeEnabled();
  await page.locator('#ai-go').click();

  expect(request.category).toBe('Breakfast Foods');
  expect(request.existing).toEqual(['Eggs', 'Bacon']);
  await expect(page.locator('#chipbox .chip')).toHaveCount(1);
  await expect(page.locator('#chipbox .chip')).toContainText('Waffles');
});

test('AI topic phrases use meaning-matched colors and rows', async ({ page }) => {
  let request = null;
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Topics Menu Page', grid: { cols: 5, rows: 5 }, pages: ['Topics Menu Page'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, page: 'Topics Menu Page', grid: { cols: 5, rows: 5 }, buttons: [],
      free_slots: Array.from({ length: 25 }, (_, index) => index), fingerprint: 'topics-v1',
    }),
  }));
  await page.route('**/api/ai/status*', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, ollama: { reachable: true, models: ['llama3.2'] },
      local: {
        engine_available: false, downloaded: false,
        model: { name: 'Local', size: '1 GB', license: 'Apache-2.0' },
        download: { status: 'idle' },
      },
    }),
  }));
  await page.route('**/api/ai/words', async (route) => {
    request = route.request().postDataJSON();
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ ok: true, engine: 'ollama', words: [
        { label: 'Who is your favorite?', function: 'comment' },
        { label: 'The story has magic', function: 'question' },
        { label: 'I love this story', function: 'personal' },
        { label: 'I do not like spiders', function: 'positive' },
        { label: 'I read it with Mom', function: 'comment' },
      ] }),
    });
  });

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await page.locator('#style-topic').click();
  await page.locator('#title-input').fill('Harry Potter');
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

  await openEditor(page);
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

  await openEditor(page);
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

  await openEditor(page);
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

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await page.locator('#operation-existing').press('ArrowRight');
  await expect(page.locator('#operation-new')).toHaveAttribute('aria-checked', 'true');
  await expect(page.locator('#title-field')).toBeVisible();
  await page.locator('#style-words').press('ArrowRight');
  await expect(page.locator('#style-topic')).toHaveAttribute('aria-checked', 'true');
  await page.locator('#word-input').fill('How are you?, Great');
  await page.locator('#word-input').press('Enter');
  const first = page.locator('#preview .cell.used').filter({ hasText: 'How are you?' });
  await first.press('ArrowRight');
  await expect(page.locator('#preview .cell.used').filter({ hasText: 'How are you?' }))
    .toHaveAttribute('aria-label', /column 2/);
});

test('layout errors are visible and a later page selection can recover', async ({ page }) => {
  let placesAttempts = 0;
  let releaseFirstPlaces;
  const firstPlacesGate = new Promise((resolve) => { releaseFirstPlaces = resolve; });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/tdsnap/status', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ok: true, available: true, running: true, unlocked: true,
      page: 'Eating', grid: { cols: 3, rows: 2 }, pages: ['Eating', 'Places'],
    }),
  }));
  await page.route('**/api/tdsnap/page-layout*', async (route) => {
    const requested = new URL(route.request().url()).searchParams.get('page');
    if (requested === 'Places' && ++placesAttempts === 1) {
      await firstPlacesGate;
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

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await page.locator('#parent-select').selectOption('Places');
  await expect(page.locator('#preview-loading')).toBeVisible();
  await expect(page.locator('#preview-loading')).toContainText('Loading “Places”');
  await expect(page.locator('.preview-workspace')).toHaveAttribute('aria-busy', 'true');
  releaseFirstPlaces();
  await expect(page.locator('#build-error')).toContainText("Couldn’t load the selected TD Snap page.");
  await expect(page.locator('#preview-loading')).toBeHidden();
  await expect(page.locator('#parent-capacity')).toContainText('could not be loaded');
  await page.locator('#parent-select').selectOption('Eating');
  await page.locator('#parent-select').selectOption('Places');
  await expect(page.locator('#build-error')).toBeHidden();
  await expect(page.locator('#parent-capacity')).toContainText('6 empty cells');
  expect(errors).toEqual([]);
});

test('partial automation checks are presented as review notes', async ({ page }) => {
  let releaseEdit;
  const editGate = new Promise((resolve) => { releaseEdit = resolve; });
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
  await page.route('**/api/tdsnap/edit-plan', async (route) => {
    await editGate;
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ok: true, buttons: 1,
        checks: { td_snap_edit: 'pass', content: 'pass', symbols: 'partial' },
        warnings: ['TD Snap could not find a symbol for 1 button.'],
      }),
    });
  });

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await page.locator('#word-input').fill('Unusualword');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await expect(page.locator('#app-activity')).toContainText('Updating TD Snap and verifying the edit');
  await expect(page.locator('#build-btn')).toHaveAttribute('aria-busy', 'true');
  releaseEdit();
  await expect(page.locator('#checks li.warning')).toContainText('Matching symbols');
  await expect(page.locator('#app-activity')).toBeHidden();
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

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#step-build')).toBeVisible();
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

  await openEditor(page);
  await page.locator('#live-connect-btn').click();
  await expect(page.locator('#step-build')).toBeVisible({ timeout: 10_000 });
  await page.locator('#operation-new').click();
  await page.locator('#title-input').fill('Playwright Test');
  await page.locator('#word-input').fill('hello');
  await page.locator('#word-input').press('Enter');
  await page.locator('#build-btn').click();
  await expect(page.locator('#step-result')).toBeVisible({ timeout: 30_000 });
});
