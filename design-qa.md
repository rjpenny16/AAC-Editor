# AAC Editor — Canvas First design QA

final result: passed

## Comparison target and evidence

Selected option: **3 — Canvas First**. Implemented in the existing Flask frontend.

- Source visual truth: `C:/Users/rjpen/.codex/generated_images/01a0f956-b755-73a0-8a28-7a46530cbadf/exec-e289c631-1f53-42bc-9ed2-f3adb6c9e8aa.png`
- Implementation URL: `http://127.0.0.1:8765/` (isolated preview settings and synthetic exported file).
- Evidence directory: `C:/Users/rjpen/.codex/visualizations/2026/10/01/01a0f956-b755-73a0-8a28-7a46530cbadf/aac-design/`
- Implementation screenshot: evidence directory + `implementation-final.jpg`.
- Full-view comparison: `comparison-final.jpg`, source left and implementation right in the same image.
- Focused comparisons: `comparison-editing-final.jpg` and `comparison-states-final.jpg`, source above implementation. Reviewed controls, labels, badges, and selected state at readable scale.
- CSS viewport: **1487 × 1058**, light theme, measured device pixel ratio approximately **1**.
- Source pixels: **1487 × 1058**. Implementation screenshot pixels: **1472 × 1048**, reflecting the in-app capture surface. Normalized the screenshot to the source dimensions using Lanczos resampling for comparisons (approximately 1% scale correction). Browser scrollbar/capture differences are excluded from findings.
- Matched state: Home Page, 4 × 3 grid; original hello and Food locked; pending more, help, finished; more selected; empty input; standard layout; AI collapsed.

## Findings and comparison history

No actionable P0/P1/P2 findings remain in the final comparison.

1. **First comparison — blocked** (`comparison-v1.jpg`, `implementation-v1.jpg`).
   - [P2] Layout choices inherited two columns instead of the intended stacked rows. Explicitly changed the workspace radio group to one column.
   - [P2] Duplicate visible preview guidance and pending heading added vertical clutter. Kept their accessible text and removed the duplicate visible copy.
   - [P2] Locked-cell fill and preview text weight drifted from the reference. Added a dedicated locked-surface token and increased speaking-label size/weight.
2. **Second comparison — blocked** (`comparison-v2.jpg`, `comparison-editing-v2.jpg`).
   - [P2] AI disclosure partly overlapped the fixed footer at the target viewport. Reduced editing-strip spacing and retained the layout explanation as an accessible description, freeing the required space.
   - [P2] Narrow selected cells overlapped the New badge, and finished wrapped unnecessarily. On narrow screens the check replaces the badge for the selected cell; reduced horizontal cell padding without reducing label size.
   - [P2] Narrow CSS forced a hidden, empty placement-order section to display. Restricted the responsive override to sections without the hidden attribute.
   - Disabled Add could inherit its blue hover fill. Excluded aria-disabled controls from enabled hover rules.
3. **Final comparison — passed** (`comparison-final.jpg` and both focused final comparisons).
   - Verified stacked layout rows, distinct editing groups, large canvas, readable locked/new states, a selected check, visible AI disclosure, and persistent primary action.
   - Responsive post-fix evidence: `implementation-mobile-final.jpg` at 390 × 844; `implementation-short-final.jpg` at 550 × 400; `implementation-default-final.jpg` at 1280 × 720. No document-width overflow; Check changes remains visible. Preview grids may scroll horizontally where needed. Taller editing content scrolls vertically above the persistent footer.

## Required fidelity surfaces

- **Fonts/typography:** retained the app's Segoe UI Variable Text/Segoe UI/system stack. Navy headings and bold speaking labels preserve the reference hierarchy. Controls and helper text remain readable; long cell labels can wrap. Generated source fonts are inferred visually, not an exact font specification.
- **Spacing/layout:** full-width preview above a shallow, divided three-column strip; compact progress in the header and a fixed footer. Narrow screens stack editing sections. Small spacing differences are acceptable for the existing tool and topic-row content.
- **Colors/tokens:** pale slate background, white canvas, navy text, blue main action and selected state. Measured contrast ratios: light primary 5.54:1, helper 5.62:1, disabled Add 4.66:1, locked label 13.28:1; dark primary 7.51:1, helper 6.98:1, disabled 5.44:1. These are selected token-pair checks, not an exhaustive accessibility certification.
- **Image quality/assets:** retained the existing AAC Editor logo; used packaged official Bootstrap Icons 1.13.1 for check, circle, lock, and disclosure indicators, with their license. No generated screenshot is used as the interface. Existing Grid 3 cell styling remains data-driven.
- **Copy/content:** matched Build your page, word entry, pending summary, page layout, tools, and Check changes. Kept the exported-copy identity and existing product instructions. Disabled Add uses readable slate text rather than the source's white-on-gray treatment. Layout guidance remains available through aria-describedby rather than cramped inline text.

## Interaction and regression verification

- Added a single word with Add; added a comma-separated batch; verified one entry per word.
- Removed and restored a word with Ctrl+Z from the relocated input.
- Selected a preview button and moved it down/up with arrow keys; selected state followed the button.
- Switched to topic rows, entered a question, removed it, and returned to standard buttons.
- Filled all ten safe spaces; input and Add disabled with a clear full-page explanation.
- Opened Check changes and verified the three planned words; returned without applying changes.
- Opened and closed Templates and the AI disclosure.
- Browser warning/error log check: empty.
- JavaScript/CSS lint: passed. Unit tests: **58 passed**. Python web tests: **74 passed, 1 skipped**. Whitespace diff check: passed.

## Test gaps and accepted differences

The full browser regression suite, physical AAC integrations, native WebView rendering, screen-reader operation, and live dark-theme rendering were not exercised in this preview. Dark token contrast was checked numerically. The mock specifies one standard-button state; existing topic rows, expanded tools, live editing, and Grid 3 preserve their functional content and may require vertical scrolling.

Progress connector lines and a few badge sizes differ slightly from the generated concept (P3 polish). The actual controls preserve the intended hierarchy and remain usable. No outstanding fix is required for acceptance.

## Implementation checklist

- [x] Preserve existing frontend and review-before-apply behavior.
- [x] Separate word entry, pending buttons, and layout/tools.
- [x] Make primary, selected, locked, and disabled states recognizable.
- [x] Compare source and rendered implementation together, including focused regions.
- [x] Fix actionable findings and capture post-fix evidence.
- [x] Restore the default browser viewport and leave the local preview available.
