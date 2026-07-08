"""
scripts/smoke_test_qwen.py — Step 3: Local AI Infrastructure Validation.

This is a REAL integration (smoke) test. It does NOT use FakeAdapter, mocks,
or any monkeypatched inference call. It loads the actual
Qwen2.5-VL-3B-Instruct model configured in config.py and drives it through
the real prompt_manager -> qwen_adapter -> vlm_inference chain, exactly as
Phase-1 extraction modules will.

It intentionally does NOT touch task_registry.py, output_contract.py, or any
other project file on disk. To exercise the real prompt_manager.run() path
without an actual NCERT task (which needs chapter-specific context vars not
relevant here), it registers one throwaway task ("_smoke_test") and matching
output contract IN MEMORY, at runtime, for the duration of this process only.
Nothing is written back to the repo.

Run:
    cd ncert_pipeline
    python scripts/smoke_test_qwen.py

Optional env vars (same ones config.py already reads):
    NCERT_VLM_MODEL       default "Qwen/Qwen2.5-VL-3B-Instruct"
    NCERT_VLM_4BIT        "1" (default) or "0"
    NCERT_VLM_DEVICE      "auto" (default) | "cuda" | "cpu"
    NCERT_VLM_MAX_NEW_TOKENS
"""
import os
import sys
import time
import platform

# Make the ncert_pipeline package root importable, same convention as
# tests/test_qwen_adapter.py.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# ---------------------------------------------------------------------------
# Tiny result-tracking helpers
# ---------------------------------------------------------------------------
RESULTS = []  # list of (check_name, passed: bool, detail: str)


def record(name, passed, detail=""):
    RESULTS.append((name, bool(passed), detail))
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return passed


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def warn(msg):
    print(f"[WARN] {msg}")


# ===========================================================================
# SECTION 1 — Environment
# ===========================================================================
section("1. ENVIRONMENT")

print(f"Python version      : {platform.python_version()}")
print(f"Platform             : {platform.platform()}")

torch = None
transformers = None
cuda_available = False
gpu_name = None
gpu_total_mem_gb = None

try:
    import torch as _torch
    torch = _torch
    print(f"Torch version        : {torch.__version__}")
    cuda_available = torch.cuda.is_available()
    print(f"CUDA available       : {cuda_available}")
    if cuda_available:
        gpu_name = torch.cuda.get_device_name(0)
        gpu_total_mem_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"GPU name             : {gpu_name}")
        print(f"GPU total memory     : {gpu_total_mem_gb:.2f} GB")
    else:
        warn("No CUDA GPU detected — will fall back to CPU (much slower, and "
             "4-bit quantization will be skipped).")
    record("torch import + version reported", True, torch.__version__)
except Exception as e:
    record("torch import + version reported", False, str(e))

try:
    import transformers as _transformers
    transformers = _transformers
    print(f"Transformers version : {transformers.__version__}")
    record("transformers import + version reported", True, transformers.__version__)
except Exception as e:
    record("transformers import + version reported", False, str(e))

if torch is None or transformers is None:
    print("\nCannot continue — torch and/or transformers failed to import. "
          "Install project requirements first: pip install -r requirements.txt")
    sys.exit(1)

record("CUDA availability reported", True, f"cuda_available={cuda_available}")


# ===========================================================================
# SECTION 2 — Test image
# ===========================================================================
section("2. TEST IMAGE")

test_image = None
try:
    from PIL import Image, ImageDraw, ImageFont

    img_path = os.path.join(_ROOT, "pdf_in")
    candidates = []
    if os.path.isdir(img_path):
        candidates = [os.path.join(img_path, f) for f in os.listdir(img_path)
                       if f.lower().endswith((".png", ".jpg", ".jpeg"))]

    if candidates:
        test_image = Image.open(candidates[0]).convert("RGB")
        print(f"Using existing repository image: {candidates[0]}")
        record("test image obtained", True, f"from repo: {candidates[0]}")
    else:
        # No sample image in the repo — create a simple synthetic one, as
        # the task instructions explicitly allow.
        img = Image.new("RGB", (640, 480), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, 600, 440], outline=(0, 0, 0), width=3)
        draw.ellipse([120, 120, 300, 300], outline=(30, 90, 200), width=4)
        draw.line([300, 210, 520, 210], fill=(200, 60, 60), width=4)
        draw.polygon([(520, 195), (520, 225), (560, 210)], fill=(200, 60, 60))
        font = ImageFont.load_default()
        draw.text((150, 350), "Sun", fill=(0, 0, 0), font=font)
        draw.text((420, 180), "Energy transfer", fill=(0, 0, 0), font=font)
        draw.text((60, 60), "SMOKE TEST DIAGRAM", fill=(0, 0, 0), font=font)

        tmp_dir = os.path.join(_ROOT, ".smoke_test_tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        img_save_path = os.path.join(tmp_dir, "synthetic_test_image.png")
        img.save(img_save_path)
        test_image = img
        print(f"No sample image found in pdf_in/ — generated a synthetic one.")
        print(f"Saved to: {img_save_path}")
        record("test image obtained", True, "synthetic image generated")
except Exception as e:
    record("test image obtained", False, str(e))


# ===========================================================================
# SECTION 3 — Model loading, singleton behavior, device, quantization, VRAM
# ===========================================================================
section("3. MODEL LOADING / SINGLETON / DEVICE / QUANTIZATION / VRAM")

from config import VLM_MODEL_ID, VLM_USE_4BIT, VLM_DEVICE  # noqa: E402
from modules import vlm_inference  # noqa: E402

print(f"Configured model id  : {VLM_MODEL_ID}")
print(f"Configured 4-bit     : {VLM_USE_4BIT}")
print(f"Configured device    : {VLM_DEVICE}")

model_1 = processor_1 = device_1 = None
model_load_time = None
try:
    t0 = time.time()
    model_1, processor_1, device_1 = vlm_inference.get_model()
    model_load_time = time.time() - t0
    print(f"Resolved device       : {device_1}")
    print(f"Model load time       : {model_load_time:.2f}s")
    record("model loads successfully", True, f"{model_load_time:.2f}s on {device_1}")
except Exception as e:
    record("model loads successfully", False, str(e))

record("device reported (CUDA or CPU)", model_1 is not None, str(device_1))

# --- Singleton check: call get_model() again, must return the SAME objects
# and must be near-instant (no reload).
if model_1 is not None:
    try:
        t0 = time.time()
        model_2, processor_2, device_2 = vlm_inference.get_model()
        second_call_time = time.time() - t0
        is_singleton = (model_1 is model_2) and (processor_1 is processor_2)
        record(
            "model loads only once (singleton)",
            is_singleton,
            f"second get_model() call took {second_call_time:.4f}s, same object={is_singleton}"
        )
        record("is_model_loaded() reports True after loading", vlm_inference.is_model_loaded(), "")
    except Exception as e:
        record("model loads only once (singleton)", False, str(e))
else:
    record("model loads only once (singleton)", False, "skipped — model failed to load")

# --- Quantization check
if model_1 is not None:
    try:
        loaded_in_4bit = bool(getattr(model_1, "is_loaded_in_4bit", False))
        quant_cfg = getattr(getattr(model_1, "config", None), "quantization_config", None)
        if VLM_USE_4BIT and device_1 == "cuda":
            if loaded_in_4bit or quant_cfg is not None:
                record("quantization working correctly", True,
                       f"is_loaded_in_4bit={loaded_in_4bit}, quantization_config={'present' if quant_cfg else 'none'}")
            else:
                warn("4-bit quantization was requested but the loaded model does not report "
                     "is_loaded_in_4bit=True or a quantization_config — bitsandbytes may not be "
                     "installed/working, and vlm_inference fell back to full precision.")
                record("quantization working correctly", False,
                       "requested but not applied (bitsandbytes likely unavailable — check warnings above)")
        elif VLM_USE_4BIT and device_1 != "cuda":
            warn("4-bit quantization was requested but device is not CUDA — quantization is "
                 "CUDA-only in this codebase, so it was correctly skipped.")
            record("quantization working correctly", True, "correctly skipped on non-CUDA device")
        else:
            record("quantization working correctly", True, "4-bit disabled by config — running full precision")
    except Exception as e:
        record("quantization working correctly", False, str(e))
else:
    record("quantization working correctly", False, "skipped — model failed to load")

# --- VRAM usage
if model_1 is not None and cuda_available:
    try:
        allocated_gb = torch.cuda.memory_allocated() / (1024 ** 3)
        reserved_gb = torch.cuda.memory_reserved() / (1024 ** 3)
        print(f"VRAM allocated        : {allocated_gb:.2f} GB")
        print(f"VRAM reserved         : {reserved_gb:.2f} GB")
        record("VRAM usage reported", True, f"allocated={allocated_gb:.2f}GB reserved={reserved_gb:.2f}GB")
    except Exception as e:
        record("VRAM usage reported", False, str(e))
elif model_1 is not None:
    print("VRAM usage            : N/A (running on CPU)")
    record("VRAM usage reported", True, "N/A — CPU device, no VRAM to report")
else:
    record("VRAM usage reported", False, "skipped — model failed to load")


# ===========================================================================
# SECTION 4 — Real adapter-level call (qwen_adapter -> vlm_inference)
# ===========================================================================
section("4. ADAPTER-LEVEL REAL INFERENCE (qwen_adapter)")

from prompt_manager.adapters.qwen_adapter import QwenAdapter  # noqa: E402

SIMPLE_PROMPT = (
    "Return ONLY valid JSON, with no markdown, no code fences, and no extra "
    "commentary. The JSON must have exactly this shape:\n"
    '{"title": "<a short description of what is shown in this image>"}'
)

adapter_response = None
adapter_inference_time = None
if model_1 is not None and test_image is not None:
    try:
        adapter = QwenAdapter()
        t0 = time.time()
        adapter_response = adapter.generate_json(SIMPLE_PROMPT, images=[test_image])
        adapter_inference_time = time.time() - t0

        print(f"Inference time         : {adapter_inference_time:.2f}s")
        print(f"Raw model output       : {adapter_response.raw_output!r}")
        print(f"Cleaned output          : {adapter_response.cleaned_output!r}")
        print(f"Parsed JSON             : {adapter_response.parsed_output}")

        record("prompt_manager's adapter successfully calls the real model",
               True, f"{adapter_inference_time:.2f}s")
        record("model returns a response", bool(adapter_response.raw_output),
               "" if adapter_response.raw_output else "empty raw output")
        fences_stripped = adapter_response.cleaned_output != adapter_response.raw_output
        record(
            "JSON cleanup works on the real response",
            isinstance(adapter_response.cleaned_output, str) and len(adapter_response.cleaned_output) > 0,
            "markdown fences/prose were stripped" if fences_stripped
            else "raw output was already clean JSON — nothing to strip",
        )
        record("JSON parsing succeeds", adapter_response.success and adapter_response.parsed_output is not None,
               adapter_response.error_message or "")
    except Exception as e:
        record("adapter successfully calls the real model", False, str(e))
        record("model returns a response", False, "exception during generate_json()")
        record("JSON cleanup works on the real response", False, "skipped — exception above")
        record("JSON parsing succeeds", False, "skipped — exception above")
else:
    for name in ("adapter successfully calls the real model", "model returns a response",
                 "JSON cleanup works on the real response", "JSON parsing succeeds"):
        record(name, False, "skipped — model or test image unavailable")


# ===========================================================================
# SECTION 5 — Full path through prompt_manager (task_registry -> adapter)
# ===========================================================================
section("5. FULL PATH THROUGH prompt_manager (prompt_manager -> qwen_adapter)")

pm_result = None
if model_1 is not None and test_image is not None:
    try:
        from prompt_manager import task_registry, output_contract
        from prompt_manager.prompt_manager import PromptManager, TaskContext
        from prompt_manager.task_registry import TaskSpec
        from prompt_manager.output_contract import OutputContract, FieldSpec

        # --- Register a throwaway task + contract IN MEMORY only, for this
        # process only. Nothing is written to disk in task_registry.py /
        # output_contract.py — this is purely a smoke-test convenience so we
        # can exercise the real PromptManager.run() code path with a trivial
        # schema instead of a full NCERT task.
        tmp_dir = os.path.join(_ROOT, ".smoke_test_tmp", "_smoke_test")
        os.makedirs(tmp_dir, exist_ok=True)
        template_path = os.path.join(tmp_dir, "v1.txt")
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(
                "{{ instruction }}\n\n"
                'Respond with a single valid JSON object with exactly one key: '
                '"title" (a short string describing what is shown in the image).'
            )

        # TaskSpec.template_path() builds its path from PROMPTS_DIR + name,
        # so instead of fighting that convention (which would mean writing
        # into the real prompts/ directory), we build the dataclass via
        # __new__ and override template_path on the instance to point at our
        # temp file. TaskSpec is frozen, so object.__setattr__ is required.
        smoke_spec = TaskSpec.__new__(TaskSpec)
        object.__setattr__(smoke_spec, "name", "_smoke_test")
        object.__setattr__(smoke_spec, "current_version", "v1")
        object.__setattr__(smoke_spec, "required_context_vars", ["instruction"])
        object.__setattr__(smoke_spec, "optional_context_vars", [])
        object.__setattr__(smoke_spec, "expects_images", True)
        object.__setattr__(smoke_spec, "output_contract_name", "_smoke_test")
        object.__setattr__(smoke_spec, "template_path", lambda version=None: template_path)

        task_registry.TASKS["_smoke_test"] = smoke_spec
        output_contract.CONTRACTS["_smoke_test"] = OutputContract(
            "_smoke_test", [FieldSpec("title", required=True, is_evidence_triple=False)]
        )

        manager = PromptManager(adapter=QwenAdapter())
        context = TaskContext(
            variables={"instruction": (
                "Return ONLY valid JSON. Describe briefly what is shown in this image."
            )},
            images=[test_image],
        )

        t0 = time.time()
        pm_result = manager.run("_smoke_test", context)
        pm_time = time.time() - t0

        print(f"TaskResult.task_name        : {pm_result.task_name}")
        print(f"TaskResult.success          : {pm_result.success}")
        print(f"TaskResult.parsed_output    : {pm_result.parsed_output}")
        print(f"TaskResult.raw_model_output : {pm_result.raw_model_output!r}")
        print(f"TaskResult.model_adapter_id : {pm_result.model_adapter_id}")
        print(f"TaskResult.inference_time   : {pm_result.inference_time}s")
        print(f"TaskResult.retry_count      : {pm_result.retry_count}")
        print(f"TaskResult.validation_errors: {pm_result.validation_errors}")

        record("prompt_manager successfully calls qwen_adapter", True, f"total call time {pm_time:.2f}s")
        record("output contract validation succeeds", pm_result.success, str(pm_result.validation_errors))
        record("a valid TaskResult is returned", pm_result is not None and hasattr(pm_result, "task_name"), "")
        record("inference time is displayed", pm_result.inference_time is not None,
               f"{pm_result.inference_time}s")
    except Exception as e:
        import traceback
        traceback.print_exc()
        record("prompt_manager successfully calls qwen_adapter", False, str(e))
        record("output contract validation succeeds", False, "skipped — exception above")
        record("a valid TaskResult is returned", False, "skipped — exception above")
        record("inference time is displayed", False, "skipped — exception above")
    finally:
        # Clean up the in-memory registrations so this script leaves no
        # trace on repeated imports within the same process.
        task_registry.TASKS.pop("_smoke_test", None)
        output_contract.CONTRACTS.pop("_smoke_test", None)
else:
    for name in ("prompt_manager successfully calls qwen_adapter", "output contract validation succeeds",
                 "a valid TaskResult is returned", "inference time is displayed"):
        record(name, False, "skipped — model or test image unavailable")


# ===========================================================================
# SECTION 6 — Summary
# ===========================================================================
section("6. PASS / FAIL SUMMARY")

n_pass = sum(1 for _, p, _ in RESULTS if p)
n_fail = sum(1 for _, p, _ in RESULTS if not p)

for name, passed, detail in RESULTS:
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")

print(f"\n{n_pass} passed, {n_fail} failed, {len(RESULTS)} total checks.")

if n_fail == 0:
    print("\nOVERALL: PASS — local AI infrastructure is verified end-to-end.")
    sys.exit(0)
else:
    print("\nOVERALL: FAIL — see the FAIL lines and [WARN] messages above for details.")
    sys.exit(1)