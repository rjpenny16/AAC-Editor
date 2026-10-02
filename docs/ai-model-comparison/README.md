# Local AI model comparison — October 1, 2026

This compares the editor's actual word/phrase prompts, JSON output constraints,
passage selection and final suggestion filtering on the current Windows computer.
The production model registry and user preferences were not changed.

## Recommendation

**Qwen3-4B-Instruct-2507, Q4_K_M, is the best efficiency candidate for this
editor.** It matches or improves the current 7B model on this targeted set while
using a 47% smaller model file, finishing typical word lists about 30% sooner,
and consuming about 27% less CPU time across the main comparison.

The most important limit remains: **none of the three models reliably knows
niche character lists without references.** All three invented Bluey names in
both tested seeds. Choosing a smaller model does not solve that first-answer
problem on its own. Accurate automatic source selection and extraction remain
necessary. Qwen3 4B and the current 7B both passed all 16 fixed-reference checks.

## Main comparison

The hardware was an AMD Ryzen 7 7445HS, six physical cores / twelve logical
processors, with 15.23 GiB of usable physical memory. Models ran sequentially
on CPU, in separate processes, using llama-cpp-python 0.3.35, 8,192-token
contexts, eleven generation threads and twelve prompt-processing threads
(the binding's current batch default). Each model file was downloaded into a dedicated
temporary cache and verified against its pinned size, SHA-256 and GGUF header.
No cloud inference service was used.

| Model, Q4_K_M | File size | Main checks | Checks including hard-topic repeat | Complete first replies | Median word-list time | Median phrase time | Peak resident process RAM | Peak private commit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 4B Instruct 2507 | 2.50 GB | 36/38 | 37/41 | 37/41 | 14.7 s | 25.3 s | 5.53 GB | 4.61 GB |
| Qwen3.5 4B, non-thinking | 2.74 GB | 36/38 | 37/41 | 35/41 | 20.2 s | 35.8 s | 4.78 GB | 3.94 GB |
| Qwen2.5 7B Instruct | 4.68 GB | 34/38 | 35/41 | 35/41 | 20.9 s | 32.0 s | 6.24 GB | 5.18 GB |

Sizes and memory above use decimal GB. Resident process memory includes resident
mapped model pages; private commit measures private allocations and is not the
same quantity. These are process measurements, not total system RAM requirements.
The smaller file does **not** halve runtime RAM: context and generation buffers
also occupy memory. Peak memory can be affected by Windows paging and other apps.

Latency medians use the first pass's 25 word and five phrase cases, including
both sourced and unsourced words. Model loading and downloading are excluded.
The repeated hard-topic cases are excluded from latency medians. This is one
computer and one sequential experiment, not a general hardware speed guarantee.

Across the 38 main generations, Qwen3 used 6,064 process CPU seconds; Qwen3.5
used 7,751; and Qwen2.5 7B used 8,308. Average CPU occupancy, calculated as
process CPU time / generation wall time / twelve logical processors, was
83.2%, 78.9% and 82.6%, respectively. Smaller models still occupy much of the
computer while generating with the current thread setting. Battery consumption,
fan noise and power draw were not measured.

## Reducing CPU occupancy

The same Harry Potter prompt and seed 42 were also tested with a six-thread
cap. The first trial limited generation only; the binding still used twelve
threads to process the prompt. A second trial capped **both** generation and
prompt processing at six threads.

| Model | Default elapsed / average CPU | Both stages capped at six: elapsed / average CPU | Process CPU time saved |
| --- | ---: | ---: | ---: |
| Qwen3 4B | 20.72 s / 75.3% | 19.34 s / 48.4% | 40.1% |
| Qwen3.5 4B | 25.71 s / 73.6% | 25.96 s / 45.5% | 37.5% |
| Qwen2.5 7B | 26.95 s / 73.4% | 27.11 s / 46.1% | 36.9% |

For Qwen3, limiting both stages used substantially less CPU time and was slightly
faster on this matched prompt. Qwen3.5 and 7B had similar elapsed time with lower
CPU occupancy. The generated output and token counts matched the default trial
for each model; changing threads did not fix 7B's Hogwarts/Gryffindor error.
These are single-prompt measurements, not a broad latency benchmark of thread
limits. CPU percentages use the process-time formula above, not power measurements.

Reports named `*-generation-threads6.json` retain the first, generation-only
trial; `*-threads6.json` contain the cap on both stages. These six generations
are excluded from the main quality table. There were 129 model generations
overall, including the 123 quality generations.

## What the quality results mean

The main run contains 30 distinct cases and repeats eight fixed-reference cases
with seed 43 after seed 42. Three difficult unsourced cases — Harry Potter,
Bluey and Death Eaters only — are then repeated in a separate process with seed
43. This makes 41 quality generations per model, 123 total. Reports retain raw
and filtered output, finish reasons, token counts, timings and memory readings.

The fixed-reference checks require every item to belong to a known allowed set.
They cover actors versus characters, animal products versus animals, a historical
subgroup, a fictional story's supplied names, a source with no character names,
and an eight-name request whose source has only three names. The exhausted source
should return three, and the empty source should return none.

The ordinary category checks are more permissive: they require some recognizable
vocabulary and reject known category mistakes, but do not prove that every label
is semantically correct or equally useful. Passing a case also does not guarantee
the requested number of items. “Complete first replies” additionally requires
the full requested count, except for the deliberately exhausted/empty sources.
Returning a shorter accurate list is preferable to inventing entries; an
incomplete reply is recorded separately rather than called a hallucination.

Notable outcomes:

- Qwen3 4B passed all 16 reference checks and returned complete useful replies
  on all passing cases. Its unsourced Death Eater answers included “Darth Malfoy”
  under seed 42 and Dumbledore under seed 43. Both Bluey runs invented names.
- Qwen3.5 4B passed 15/16 reference checks. One exhausted-source reply added
  “Brisbane” and “Fetch”; the other correctly returned only three characters.
  Its questions-only and negative-only replies were underfilled after filtering.
  It also suggested both “fridge” and “refrigerator” in one list, a semantic
  duplicate that the current exact-duplicate rule does not catch.
- The 7B model passed all 16 reference checks. Its first unsourced Harry Potter
  reply included Hogwarts and Gryffindor; the second was correct. Both Bluey
  runs invented names. Its Death Eater lists had four valid names rather than
  five, and its questions-only task returned two usable questions rather than five.
- Some structurally valid phrases still sound awkward, such as Qwen3's
  “I went to my 10th birthday.” The scores are not a replacement for editorial
  judgment about communication usefulness.

One scoring defect was corrected during the experiment: the kitchen case rejected
the valid compound noun “kitchen table.” It now rejects the exact label “kitchen”
and a restatement of the title while allowing real kitchen objects. All models
were scored against the same corrected fixtures. The unsourced Death Eater set
also accepts the group's leader, Voldemort, to avoid a disputed membership rule
deciding the comparison. Earlier scores are retained as `original_score` when
rescoring changed a result. Neither correction excuses invented names or names
from the wrong subgroup.

The Qwen3.5 benchmark explicitly disables thinking in its embedded chat template.
The current Python binding does not forward the corresponding template parameter,
so the benchmark supplies a formatter with `enable_thinking=False`. This is a
candidate integration detail, not a production backend change. Testing its
extended-thinking mode would answer a different latency/resource question.

This experiment uses the editor's current sampling settings (temperature 0.25
with a source, 0.4 without), not separately optimized settings for each model.
It does not evaluate changing live Wikipedia search results, long articles,
other quantizations, GPU inference, multilingual output or every AAC use case.

## Reproduce

The candidate pins live in [the comparison harness](../../scripts/compare_ai_models.py).
[cases.json](cases.json) records the common scoring fixtures.

```powershell
python scripts/compare_ai_models.py --model qwen3-4b --cache "$env:TEMP\aac-model-comparison" --report qwen3-4b.json --download
python scripts/compare_ai_models.py --model qwen35-4b --cache "$env:TEMP\aac-model-comparison" --report qwen35-4b.json --download
python scripts/compare_ai_models.py --model qwen25-7b --cache "$env:TEMP\aac-model-comparison" --report qwen25-7b.json --download
```

The strict source fixtures repeat by default with seeds 42 and 43. Repeat the
hard unsourced topics separately with:

```powershell
python scripts/compare_ai_models.py --model qwen3-4b --cache "$env:TEMP\aac-model-comparison" --report qwen3-4b-seed43.json --seed 43 --case harry-potter-characters --case bluey-without-reference --case subgroup-without-reference --repeats 1
```

Use each of the three model keys for the same repeat. A CPU thread limit is
available via `--threads 6`; its measurements are recorded separately from the
main quality/latency table. The current harness caps both stages:

```powershell
python scripts/compare_ai_models.py --model qwen3-4b --cache "$env:TEMP\aac-model-comparison" --report qwen3-4b-threads6.json --threads 6 --case harry-potter-characters --seed 42 --repeats 1
```

Qwen3's two extra unsourced cases were added after its first benchmark process
started, so they were run separately and merged into its main report. Their
original standalone evidence is [qwen3-4b-additional.json](qwen3-4b-additional.json).
All three models ultimately received the same cases, seeds and scoring rules.

The temporary GGUF downloads were removed after the experiment, freeing
approximately 9.92 GB. The reports and harness remain. Existing installed
models and preferences were not changed.

After this comparison, the user selected Qwen3 4B Instruct 2507. It is now a
verified production choice and the recommendation on supported computers.
The subsequent prompt work and deployment settings are documented in
[AI quality notes](../AI_QUALITY.md). The
[production prompt retest](qwen3-production-prompts.json) retains separate
evidence; the tables above describe the original comparison settings.

Publisher references:
[Qwen3 4B Instruct 2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
[Qwen3.5 4B](https://huggingface.co/Qwen/Qwen3.5-4B),
[Qwen3 quantized files](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/a06e946bb6b655725eafa393f4a9745d460374c9),
[Qwen3.5 quantized files](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/tree/e87f176479d0855a907a41277aca2f8ee7a09523),
[current 7B files](https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/tree/8911e8a47f92bac19d6f5c64a2e2095bd2f7d031).
