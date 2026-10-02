"""Compare pinned local candidates using the editor's real suggestion pipeline.

Each invocation runs one model in a fresh process. Downloads and preferences
are isolated by --cache; no production model registry or preferences change.
Use the same --seed and --repeats for each model. Reports retain actual output,
latency, CPU time, token counts and Windows process memory measurements.
"""

import argparse
import ctypes
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def memory():
    """Working set includes resident mapped weights; private bytes are commit."""
    if os.name != "nt":
        return {}

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                "PrivateUsage",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong,
    ]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"working_set": counters.WorkingSetSize, "private_bytes": counters.PrivateUsage,
            "peak_working_set": counters.PeakWorkingSetSize}


def extra_cases():
    def case(identifier, category, count, request, reference, allowed):
        return {"id": identifier, "category": category, "count": count, "kind": "words",
                "request": request, "reference": reference, "checks": {
                    "allowed_items": allowed, "min_items": min(count, len(allowed)),
                    "no_duplicates": True}}

    return [
        case("bluey-without-reference", "Bluey characters", 8, "Characters only.", "",
             ["Bluey", "Bingo", "Bandit", "Chilli", "Muffin", "Socks", "Chloe", "Rusty",
              "Mackenzie", "Coco", "Indy", "Snickers", "Honey", "Lucky", "Judo", "Jack",
              "Winton", "Calypso", "Trixie", "Stripe", "Frisky", "Rad", "Radley", "Pat",
              "Wendy", "Lila", "Pom Pom", "Doreen", "Jean Luc", "Jean-Luc", "Bob", "Nana",
              "Grandad", "Mort", "Bobo", "Bucky", "Hercules", "Pretzel", "Bentley", "Buddy",
              "Chucky", "Jasper", "Missy", "Captain", "Mia", "Lulu", "Dusty"]),
        case("subgroup-without-reference", "Harry Potter characters", 5,
             "Only Death Eaters, full names. Do not include other characters.", "",
             ["Bellatrix Lestrange", "Lucius Malfoy", "Draco Malfoy", "Barty Crouch Jr",
              "Barty Crouch Jr.", "Bartemius Crouch Jr", "Peter Pettigrew", "Antonin Dolohov",
              "Severus Snape", "Walden Macnair", "Augustus Rookwood", "Corban Yaxley",
              "Fenrir Greyback", "Amycus Carrow", "Alecto Carrow", "Rodolphus Lestrange",
              "Rabastan Lestrange", "Igor Karkaroff", "Thorfinn Rowle", "Voldemort",
              "Lord Voldemort", "Tom Riddle", "Tom Marvolo Riddle"]),
        case("actors-versus-characters", "Frozen characters", 5, "Characters only, not actors.",
             "Frozen characters: Elsa, Anna, Olaf, Kristoff, Sven and Hans. "
             "Cast: Idina Menzel voices Elsa; Kristen Bell voices Anna; Josh Gad voices Olaf. "
             "Arendelle is the kingdom and Let It Go is a song.",
             ["Elsa", "Anna", "Olaf", "Kristoff", "Sven", "Hans"]),
        case("animals-versus-products", "Farm animals", 8, "Animals only.",
             "Farm livestock: cows produce milk, chickens lay eggs, sheep provide wool, "
             "and pigs, goats, ducks, horses and donkeys are raised on farms. "
             "Hay, grain and feed are foods. Barns, tractors and fences are equipment.",
             ["Cow", "Cows", "Chicken", "Chickens", "Sheep", "Pig", "Pigs", "Goat", "Goats",
              "Duck", "Ducks", "Horse", "Horses", "Donkey", "Donkeys"]),
        case("historical-subgroup", "US presidents", 4, "Only presidents who served before 1900.",
             "Presidents before 1900: George Washington, Thomas Jefferson, Abraham Lincoln, "
             "Ulysses S Grant and Grover Cleveland. Presidents after 1900: John F Kennedy, "
             "Ronald Reagan, Barack Obama and Joe Biden. Washington DC is the capital.",
             ["George Washington", "Thomas Jefferson", "Abraham Lincoln", "Ulysses S Grant",
              "Grover Cleveland"]),
        case("source-has-no-members", "Bluey characters", 6, "Characters only.",
             "This excerpt describes Brisbane, Queensland and Australia. It discusses "
             "animation, television broadcasts, production schedules and games. "
             "No character names are given in this excerpt.", []),
        case("source-over-prior-knowledge", "Meadow Club characters", 4, "Only characters named here.",
             "The fictional Meadow Club story has four characters: Nori, Pippa, Tavi and Wren. "
             "Maple is their town, Pebble is their clubhouse and Starfall is their annual event. "
             "The author is Rowan Vale and the illustrator is Ellis Reed.",
             ["Nori", "Pippa", "Tavi", "Wren"]),
    ]


def first_reply_result(case, items, passed):
    """Track useful completeness, including deliberately exhausted references."""
    expected = {"reference-exhaustion": 3, "source-has-no-members": 0}.get(
        case["id"], case["count"]
    )
    complete = len(items) == expected
    return {"target_items": expected, "complete": complete,
            "first_reply_passed": passed and complete}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["qwen3-4b", "qwen35-4b", "qwen25-7b"], required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--repeats", type=int, default=2, help="Repeat strict reference cases")
    parser.add_argument("--case", action="append", default=[], help="Limit to case IDs; repeat to select several")
    parser.add_argument("--threads", type=int, help="CPU thread limit; default matches the editor")
    args = parser.parse_args()
    if args.threads is not None and args.threads < 1:
        parser.error("--threads must be positive")
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA" if os.name == "nt" else "XDG_DATA_HOME"] = str(cache)
    for name in ("TDSNAP_MODEL_URL", "TDSNAP_MODEL_FILE", "TDSNAP_MODEL_SIZE", "TDSNAP_MODEL_SHA256"):
        os.environ.pop(name, None)
    from tdsnap.web import grounding, localai, prompts
    from tests import ai_eval

    candidates = {
        "qwen3-4b": localai.ModelChoice(
            "qwen3-4b", "Qwen3 4B Instruct 2507", "Apache-2.0",
            "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "unsloth/Qwen3-4B-Instruct-2507-GGUF",
            "a06e946bb6b655725eafa393f4a9745d460374c9",
            "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597",
            2_497_281_120, 0, "2.5 GB", "Benchmark candidate"),
        "qwen35-4b": localai.ModelChoice(
            "qwen35-4b", "Qwen3.5 4B", "Apache-2.0",
            "Qwen3.5-4B-Q4_K_M.gguf", "unsloth/Qwen3.5-4B-GGUF",
            "e87f176479d0855a907a41277aca2f8ee7a09523",
            "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
            2_740_937_888, 0, "2.74 GB", "Benchmark candidate"),
        "qwen25-7b": localai.LARGE._replace(key="qwen25-7b"),
    }
    choice = candidates[args.model]
    localai.REGISTRY = (choice,)
    localai.DEFAULT_KEY = choice.key
    if not localai.is_downloaded(choice.key):
        if not args.download:
            parser.error("Missing model; pass --download to allow a verified download.")
        localai.start_download(choice.key)
        previous = -1
        while localai.download_state()["status"] == "downloading":
            state = localai.download_state()
            progress = int(state["done"] * 100 / choice.size)
            if progress // 10 != previous:
                print(f"Downloading {choice.name}: {progress}%", flush=True)
                previous = progress // 10
            time.sleep(1)
        if not localai.is_downloaded(choice.key):
            raise RuntimeError(localai.download_state())

    report = {"model": choice.name, "pin": choice._asdict(), "seed": args.seed,
              "n_ctx": 8192, "n_threads": args.threads or max(2, (os.cpu_count() or 4) - 1),
              "n_threads_batch": args.threads or os.cpu_count(),
              "logical_cpus": os.cpu_count(), "system_memory_bytes": localai.total_memory_bytes(),
              "thinking": False, "baseline_memory": memory(), "results": []}
    args.report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    peaks = {"working_set": 0, "private_bytes": 0}
    stop = threading.Event()

    def sample():
        while not stop.wait(0.1):
            measured = memory()
            for key in peaks:
                peaks[key] = max(peaks[key], measured.get(key, 0))

    watcher = threading.Thread(target=sample, daemon=True)
    watcher.start()
    try:
        started = time.perf_counter()
        if args.threads:
            from llama_cpp import Llama
            error = localai._validation_error(choice.key)
            if error:
                raise RuntimeError(error)
            localai._llm = Llama(model_path=localai.model_path(choice.key), n_ctx=8192,
                                 n_threads=args.threads, n_threads_batch=args.threads, verbose=False)
            localai._llm_path = localai.model_path(choice.key)
        llm = localai._load_llm(choice.key)
        report["n_threads"] = llm.n_threads
        report["n_threads_batch"] = llm.n_threads_batch
        report["load_seconds"] = round(time.perf_counter() - started, 3)
        report["loaded_memory"] = memory()
        report["architecture"] = llm.metadata.get("general.architecture")
        report["chat_format"] = llm.chat_format
        if args.model == "qwen35-4b":
            from llama_cpp.llama_chat_format import Jinja2ChatFormatter
            # The binding doesn't forward template kwargs. Set the official
            # non-thinking flag in the embedded template for this experiment.
            template = "{% set enable_thinking = false %}" + llm.metadata["tokenizer.chat_template"]
            formatter = Jinja2ChatFormatter(
                template=template, eos_token=llm._model.token_get_text(llm.token_eos()),
                bos_token=llm._model.token_get_text(llm.token_bos()),
                stop_token_ids=[llm.token_eos()],
            )
            rendered = formatter(messages=[{"role": "user", "content": "Hi"}]).prompt
            if not rendered.endswith("<think>\n\n</think>\n\n"):
                raise RuntimeError(f"Non-thinking template was not applied: {rendered[-100:]!r}")
            llm.chat_handler = formatter.to_chat_handler()
            report["chat_format"] = "embedded template, enable_thinking=False"

        original = llm.create_chat_completion
        captured = {}
        current_seed = args.seed

        def completion(**kwargs):
            result = original(**kwargs, seed=current_seed)
            captured.clear()
            captured.update(result)
            return result

        llm.create_chat_completion = completion
        cases = ai_eval.load_cases() + extra_cases()
        if args.case:
            cases = [case for case in cases if case["id"] in args.case]
            if set(args.case) - {case["id"] for case in cases}:
                raise ValueError("Unknown requested case")
        report["cases"] = cases
        for repeat in range(args.repeats):
            current_seed = args.seed + repeat
            for case in cases:
                if repeat and not case.get("reference"):
                    continue
                reference = grounding.select_passages(
                    case.get("reference", ""), f"{case['category']} {case.get('request', '')}"
                )
                started = time.perf_counter()
                cpu = time.process_time()
                captured.clear()
                raw, error = localai.generate_words(
                    case["category"], count=prompts.overask(case["count"]), kind=case["kind"],
                    function=case.get("function"), reference=reference,
                    request=case.get("request"), model_key=choice.key,
                )
                elapsed = time.perf_counter() - started
                cpu_elapsed = time.process_time() - cpu
                items = prompts.clean_items(raw, case["count"], case["kind"], case["category"],
                                            reference=reference, function=case.get("function"))
                result = ai_eval.score(case, items)
                if error:
                    result["passed"] = False
                    result["failures"].append(error)
                result.update(first_reply_result(case, items, result["passed"]))
                result.update(items=items, raw_items=raw, error=error, repeat=repeat,
                              seconds=round(elapsed, 3), cpu_seconds=round(cpu_elapsed, 3),
                              usage=captured.get("usage"), memory=memory(),
                              raw_content=(captured.get("choices") or [{}])[0].get("message", {}).get("content"),
                              finish_reason=(captured.get("choices") or [{}])[0].get("finish_reason"))
                report["results"].append(result)
                save()
                print(json.dumps({k: result[k] for k in ("id", "repeat", "passed", "seconds", "items", "failures")}), flush=True)
    except Exception as exc:
        report["fatal_error"] = str(exc)
        raise
    finally:
        stop.set()
        watcher.join()
        report["peak_memory"] = peaks
        report["final_memory"] = memory()
        results = report["results"]
        report["summary"] = {k: v for k, v in ai_eval.summarize(results).items() if k != "results"}
        report["summary"]["complete_first_replies"] = sum(
            r["first_reply_passed"] for r in results
        )
        if results:
            report["median_seconds"] = round(statistics.median(r["seconds"] for r in results), 3)
            report["total_cpu_seconds"] = round(sum(r["cpu_seconds"] for r in results), 3)
        save()
    print(json.dumps(report["summary"]), flush=True)


if __name__ == "__main__":
    main()
