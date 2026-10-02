# AI vocabulary investigation

The useful change for this editor is a more capable local instruction model
combined with reference retrieval that preserves actual lists and names.
Prompt wording alone did not resolve the small model's category mistakes.

A later [three-model comparison](ai-model-comparison/README.md) tested two
newer 4B candidates against the 7B model, including repeated difficult topics
and actual memory/CPU measurements. Qwen3 4B Instruct 2507 was the strongest
efficiency candidate under the editor's existing prompts and settings. That
benchmark does not change the production registry or installed preferences.

## What was failing

- Qwen2.5 1.5B mixed places into character lists and produced generic or
  invented labels for franchises. In a three-case comparison, both the original
  and revised prompts passed only the farm-animal case.
- Search favored any “List of…” title, even an unrelated list. Wikipedia also
  returned the novel *Animal Farm* for “Farm animals.”
- The original reference consisted of the first 1,500 characters of an
  extract. That misses later character sections. TextExtracts also omits lists
  and tables, precisely the structures this application needs.
  [MediaWiki TextExtracts documentation](https://www.mediawiki.org/wiki/Extension:TextExtracts#Caveats).
- Reference instructions were not enforced against the output, so invented
  words could still reach the tray. Exact matching also needs to recognize
  regular plurals such as a source's “cows” and a button's “Cow.”
- The existing CI evaluation uses a 0.5B smoke model and records results
  without a quality threshold. Its general recognition check can pass an
  answer with only one correct item among several invented names.

## Changes

Following the [three-model comparison](ai-model-comparison/README.md), setup
recommends **Qwen3 4B Instruct 2507**, Q4_K_M (~2.5 GB), on measured
12 GB-class computers. The gate is 11 GiB usable RAM; that gate allows ordinary
firmware reservations but is inferred from a 16 GB host, not verified on every
12 GB computer. Lower-memory or unmeasured machines retain the 1.5B option;
7B remains available on 16 GB-class computers. Explicit installed-model
preferences remain honored. With no explicit preference, a downloaded Qwen3
is selected ahead of the other choices. Downloads use immutable publisher
metadata, exact size, SHA-256 and GGUF header validation.

Both backends retain an 8,192-token context and temperatures of 0.25 with a
source and 0.4 without one. The built-in engine now caps **both** generation
and prompt-processing threads at half the logical cores, with a maximum of
six and minimum of one. The measured six-thread comparison reduced Qwen3 CPU
time by about 40% on one matched prompt. That is a focused result, not a
guaranteed reduction for every workload.

### Instructions on every request

Source-based word requests use standing system instructions and JSON request
data. The rules prioritize the requested category and subgroup, require names
or terms supported by the source, distinguish membership from incidental
mentions, omit uncertain candidates, and allow an empty or shorter list.
Existing buttons, rejections, kept examples, prior suggestions and writing
style remain distinct constraints. The existing source-evidence check still
runs after generation.

Unsourced words retain their previous prompt. Mixed-function phrases retain
their established prompt structure, with an added rule against invented ages,
dates, relatives, plans and past experiences. Personal phrases should provide
usable current needs or preferences rather than a made-up biography.
Shortening everything into one universal prompt was faster but regressed
Disney franchise accuracy and did not cure unfamiliar-name hallucination.
Single-function phrase requests now restrict the JSON schema to that function
as well as applying the existing meaning-based filter. Structured output
constrains the answer's shape; it does not prove factual accuracy.

No user needs to repeat these rules. A useful request supplies only the scope:
“Bluey characters, names only” or “Only Death Eaters, full names.” An exact
article or pasted source remains the reliable way to supply missing facts.

The [prototype prompt trial](ai-model-comparison/qwen3-prompt-trial.json)
contains actual output for 14 selected cases at seeds 42 and 43. All seven
source cases passed twice. Its initially recorded 24/28 score used the older
Disney check, which failed to reject SpongeBob and Scooby-Doo; the current
fixture catches those cross-franchise mistakes; the rescored report is 23/28
and preserves the original scores. The broad production retest is
[recorded separately](ai-model-comparison/qwen3-production-prompts.json):
36/38 checks passed, with 36 complete first replies and **16/16 source checks**
passing across seeds 42 and 43. The two failures were unsourced Bluey and Death
Eater lists. Source-generation median was 5.90 seconds; the original comparison
used different CPU thread settings, so the timing difference cannot be credited
to the prompt alone. These are fixed short sources, not long live articles.

Manual review still found unsupported personal-history phrases in that broad
run, despite its permissive phrase checks passing. The added biography rule
is evaluated in [the phrase retest](ai-model-comparison/qwen3-phrase-instructions.json):
five of five checks passed at seed 42, with complete replies. Manual review of
those five outputs found no invented ages or past visits. This small retest
does not establish that all personal claims or function-balance errors are solved.
General recognition checks do not guarantee every label's factual correctness,
semantic variety, or a balanced phrase mix.

The [official Qwen model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
specifies that this variant supports only non-thinking mode; it needs no
`/no_think` instruction or explicit thinking toggle. Its general sampling
recommendation is temperature 0.7; our lower task-specific temperatures remain
the settings used in these local AAC tests, not a universal model recommendation.

Reference retrieval reads rendered article lists, tables and headings. Local
passage ranking favors relevant sections, enumerations and coverage of
different characters rather than long biographies. Search ranks subject
overlap before a list bonus. A supplied description can disambiguate already
retrieved articles locally, without being sent to Wikipedia. Requests are
cached for five minutes, and at most three usable articles are fetched per
lookup. An exact article bypasses search.

Users can supply an English Wikipedia title or URL, or paste text from any
reference page. Pasted text takes priority and remains local. An unreadable
exact reference produces an actionable error rather than quietly switching
sources. Reference identity stays visible, and editing the request/reference
clears stale candidates. The browser receives source metadata, not article
contents. Online lookup remains opt-in.

Sourced word suggestions must occur in the selected reference, including
regular singular/plural pairs. This is an evidence check, **not a semantic
proof** that an item belongs to the requested category. The model must still
distinguish characters from actors, animals from their products, and the
requested subgroup from other names in the same article. Requested phrase
functions are checked against the phrase's actual meaning before delivery.

## Measured results on this Windows computer

| Evaluation | Result | Limits |
| --- | --- | --- |
| Original 1.5B prompt: Harry Potter, Disney, farm animals | 1/3 passed | Character mistakes remained |
| Revised 1.5B prompt, same three topics | 1/3 passed | Prompt edits alone were insufficient |
| 7B: first six existing word cases | 6/6 passed | Existing recognition rules are permissive |
| 7B: three strict fixed-reference cases | 3/3 passed, twice | Every item must belong to a complete allowed set |
| Live Wikipedia livestock reference after passage/plural fixes | Passed; eight animal labels | One live example, not a broad web benchmark |

The strict cases cover Bluey character names, “Death Eaters only, full names,”
and an eight-item request whose reference supplies only three characters. The
last case returns those three names instead of inventing five more. Simple
7B generations took roughly 20–46 seconds including the first model load;
strict reference cases took roughly 16–38 seconds. A longer live reference
generation took about 80 seconds. A larger model trades speed and memory for
better category adherence on CPU.

The source-selection fixes were also exercised against live Bluey and Harry
Potter searches and exact article retrieval. Wikipedia rate limiting was
observed during repeated uncached investigation requests; caching reduces
repeat traffic, but a failed automatic lookup still needs the visible fallback
notice. Arbitrary websites are supported by pasted text, not automatic URL
fetching.

## Reproduce quality checks

Install the AI extra, then select a real offered model and report path:

```powershell
python scripts/evaluate_ai_quality.py --model qwen3 --download --report ai-quality.json
```

This runs all fixed cases and fails below 100% by default. A focused strict
reference run is:

```powershell
python scripts/evaluate_ai_quality.py --model qwen3 --case bluey-reference-characters --case death-eaters-reference-subset --case reference-exhaustion --report ai-reference-quality.json
```

Downloads require `--download` when the model is not already present. Use
`--floor` to set a deliberate threshold. Fixed reference fixtures avoid
Wikipedia drift; a broad live-source evaluation remains separate work. The
three-model comparison covers the additional phrase and topic cases. Strict checks prevent
one recognizable name from hiding an otherwise inaccurate reference answer.

## Browser verification

Thirty AI setup, steering, reference and upgrade browser checks passed on
Chromium, including the exact-link/pasted-text interaction, stale suggestion
clearing, downloaded-model selection, desktop layout and a 390 × 844 viewport.
The new reference controls passed the suite's serious/critical accessibility
checks and produced no page errors. The broader initial 31-test selection
also included one failing pre-existing assertion: selected preview cells now
use an accent selection border, while the test expects the old function color
on that selected cell. Those existing visual edits were preserved.

Model publisher background:
[Qwen2.5 7B model card](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF).
These local results, rather than general model-card claims, are the basis for
the new setup recommendation.
