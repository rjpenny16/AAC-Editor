/* Open Board Format boards, as the server reads them, turned into word-list
 * items. Pure: no DOM, no state, so node --test pins it.
 *
 * The server does the reading (tdsnap/obf.py) and hands back the canonical
 * model: boards of cells, each {row, col, label, message, border, link}. This
 * is the half that decides what one board becomes on the page already open —
 * speaking buttons, in their own cells where the page is big enough — and what
 * it does not: a button that opens another board has nowhere to point on a
 * single page, so it is named rather than turned into something it was not.
 */

/* The function whose clinical colour a border is, or "" for any other colour. */
function functionForBorder(border, functions) {
  if (!border) return "";
  const wanted = String(border).toUpperCase();
  const match = Object.entries(functions)
    .find(([, fn]) => String(fn.color).toUpperCase() === wanted);
  return match ? match[0] : "";
}

/* One board's speaking buttons as candidate items, in reading order.
   `preferredSlot` is the board's own cell when the whole board fits the page
   grid, so a board laid out with care keeps that layout; otherwise null, and
   the caller places it in the first open space. */
function boardWords(board, { cols, rows, functions = {} }) {
  const fits = board.rows <= rows && board.columns <= cols;
  const items = [];
  const links = [];
  [...board.cells]
    .sort((left, right) => left.row - right.row || left.col - right.col)
    .forEach((cell) => {
      if (cell.link) {
        links.push(cell.label);
        return;
      }
      items.push({
        label: cell.label,
        message: cell.message || null,
        fn: functionForBorder(cell.border, functions),
        symbolQuery: "",
        preferredSlot: fits ? cell.row * cols + cell.col : null,
      });
    });
  return { items, links, fits };
}

/* Give each accepted item a cell: its preferred one where that is open and not
   already promised, then the first open space for everyone else. Two passes, so
   an item without a preference can never take the cell another item's board put
   it in. `firstOpen(fn, taken)` answers the fallback. */
function assignSlots(items, { open, taken = [], firstOpen }) {
  const openSet = new Set(open);
  const used = new Set(taken);
  const slots = items.map((item) => {
    const slot = item.preferredSlot;
    if (Number.isInteger(slot) && openSet.has(slot) && !used.has(slot)) {
      used.add(slot);
      return slot;
    }
    return null;
  });
  return slots.map((slot, index) => {
    if (slot !== null) return slot;
    const chosen = firstOpen(items[index].fn, used);
    if (chosen !== null && chosen !== undefined) used.add(chosen);
    return chosen ?? null;
  });
}

/* "“more” on Snacks — opens a web link", or "Snacks — has no layout". */
function describeSkipped(entry) {
  return entry.label
    ? `“${entry.label}” on ${entry.board} — ${entry.reason}`
    : `${entry.board} — ${entry.reason}`;
}

/* One line per page a board-set import will create, for the review list. */
function describePlannedPage(page) {
  const links = page.cells.filter((cell) => cell.link).length;
  const words = page.cells.length - links;
  const parts = [
    `${words} speaking button${words === 1 ? "" : "s"}`,
    links ? `${links} link${links === 1 ? "" : "s"} to other imported pages` : "",
    page.renamed ? `renamed from “${page.name}”, which is already taken` : "",
    page.rearranged
      ? `was a ${page.source_grid.cols} by ${page.source_grid.rows} board, so its buttons are in reading order`
      : "",
  ];
  return parts.filter(Boolean).join(" · ");
}

export { assignSlots, boardWords, describePlannedPage, describeSkipped, functionForBorder };
