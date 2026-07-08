"""
vlm_inference.py — single, reusable Qwen2.5-VL-3B-Instruct handle.

Loaded exactly ONCE (module-level singleton via get_model()) and reused for
every page-batch/figure/table/equation call in the whole run — per spec,
never reload per page. Falls back CPU if no GPU is available; falls back
to fp16/bf16 if 4-bit bitsandbytes quantization isn't installed/supported.

This module ONLY knows how to talk to the model (load it, run one chat-style
generate call given images + a prompt, return raw text). Prompt construction
and result parsing for each schema field live in semantic_processor.py —
kept separate so the model plumbing doesn't get tangled with "what JSON
shape do we want back".
"""
import io
import logging
from typing import List, Optional, Union

logger = logging.getLogger("ncert_pipeline.vlm")

from config import VLM_MODEL_ID, VLM_USE_4BIT, VLM_MAX_NEW_TOKENS, VLM_DEVICE

_MODEL = None
_PROCESSOR = None
_DEVICE = None


def _resolve_device() -> str:
    if VLM_DEVICE != "auto":
        return VLM_DEVICE
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def get_model():
    """Lazily loads the model+processor once; every subsequent call returns
    the same in-memory objects. This is the ONLY place the model is
    instantiated in the whole codebase."""
    global _MODEL, _PROCESSOR, _DEVICE
    if _MODEL is not None:
        return _MODEL, _PROCESSOR, _DEVICE

    import torch
    from transformers import AutoProcessor

    # Qwen2.5-VL uses a DIFFERENT model class than Qwen2-VL
    # (Qwen2_5_VLForConditionalGeneration, not Qwen2VLForConditionalGeneration).
    # Loading 2.5's weights via the 2-VL class name can crash (including hard
    # segfaults) depending on the installed transformers version, so try the
    # correct class first and only fall back if this transformers version
    # genuinely doesn't have it yet.
    try:
        from transformers import Qwen2_5_VLForConditionalGeneration as ModelClass
    except ImportError:
        logger.warning(
            "transformers version too old for Qwen2_5_VLForConditionalGeneration — "
            "run: pip install -U transformers>=4.49.0. Falling back to AutoModelForImageTextToText."
        )
        from transformers import AutoModelForImageTextToText as ModelClass

    _DEVICE = _resolve_device()
    logger.info("Loading %s on device=%s (4bit=%s) using %s...",
                VLM_MODEL_ID, _DEVICE, VLM_USE_4BIT, ModelClass.__name__)

    quantization_config = None
    if VLM_USE_4BIT and _DEVICE == "cuda":
        try:
            from transformers import BitsAndBytesConfig
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
        except Exception as e:
            logger.warning("bitsandbytes 4-bit quantization unavailable (%s) — loading full precision.", e)

    load_kwargs = dict(torch_dtype=torch.float16 if _DEVICE == "cuda" else torch.float32)
    if quantization_config is not None:
        load_kwargs["quantization_config"] = quantization_config
        load_kwargs["device_map"] = "auto"

    _MODEL = ModelClass.from_pretrained(VLM_MODEL_ID, **load_kwargs)
    if quantization_config is None:
        _MODEL = _MODEL.to(_DEVICE)
    _MODEL.eval()
    _PROCESSOR = AutoProcessor.from_pretrained(VLM_MODEL_ID)

    logger.info("Model loaded. Will be reused for the remainder of this run.")
    return _MODEL, _PROCESSOR, _DEVICE


def is_model_loaded() -> bool:
    return _MODEL is not None


def unload_model():
    """Optional explicit teardown (e.g. between very large batch jobs);
    not called automatically — the model is meant to persist for the run."""
    global _MODEL, _PROCESSOR
    _MODEL, _PROCESSOR = None, None
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def generate(prompt: str, images: Optional[List["PIL.Image.Image"]] = None,
             max_new_tokens: Optional[int] = None) -> str:
    """One generate call. `images` is a list of PIL images (can be empty for
    text-only prompts, e.g. concept/glossary extraction from OCR'd text)."""
    import torch
    model, processor, device = get_model()

    content = []
    for img in (images or []):
        content.append({"type": "image", "image": img})
    content.append({"type": "text", "text": prompt})
    messages = [{"role": "user", "content": content}]

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=images or None, return_tensors="pt", padding=True)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    # eos/pad token ids and a mild repetition penalty are set explicitly
    # here rather than left to transformers' defaults. Under greedy decoding
    # (do_sample=False), a prompt whose expected answer is in a script the
    # model is less fluent in (Hindi/Sanskrit, vs. the mostly-English/code
    # data these VL models are typically tuned on) is more likely to fall
    # into a repetition loop that never emits an EOS token, burning the
    # full max_new_tokens on every single call — this is what showed up as
    # "the semantic stage becomes very slow or hangs on non-English pages".
    # repetition_penalty discourages that loop; explicit eos/pad ids make
    # sure a real stop token is honored the instant the model produces one,
    # instead of relying on tokenizer defaults that may be unset for some
    # processor configs. None of this changes behavior for English content
    # that was already terminating normally.
    tokenizer = getattr(processor, "tokenizer", None)
    eos_token_id = getattr(tokenizer, "eos_token_id", None) if tokenizer else None
    pad_token_id = getattr(tokenizer, "pad_token_id", None) if tokenizer else None
    generate_kwargs = dict(max_new_tokens=max_new_tokens or VLM_MAX_NEW_TOKENS,
                            do_sample=False, repetition_penalty=1.15)
    if eos_token_id is not None:
        generate_kwargs["eos_token_id"] = eos_token_id
    if pad_token_id is not None:
        generate_kwargs["pad_token_id"] = pad_token_id
    elif eos_token_id is not None:
        generate_kwargs["pad_token_id"] = eos_token_id

    with torch.inference_mode():
        output_ids = model.generate(**inputs, **generate_kwargs)
    trimmed = output_ids[:, inputs["input_ids"].shape[1]:]
    decoded = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=True)
    return decoded[0].strip() if decoded else ""


def generate_batch(prompts_and_images: List[tuple], max_new_tokens: Optional[int] = None) -> List[str]:
    """True batched generation: builds ALL prompts' chat-template text and
    images, tokenizes/pads them together into ONE tensor, and issues a
    SINGLE model.generate() call across the whole batch, instead of the
    previous `[generate(p, imgs) for p, imgs in ...]` sequential loop
    (the "generate_batch() is not true batching" bottleneck the
    architecture review flagged — GPU utilization was poor because every
    item paid its own forward-pass overhead one at a time).

    Each item is (prompt: str, images: list[PIL.Image] | None). Falls back
    to the old sequential path only if a single call in the batch needs a
    different max_new_tokens than the rest, or on any batching-path error
    (e.g. a processor that doesn't support batched multi-image inputs) --
    correctness is preserved even if the perf win isn't, rather than
    silently producing wrong output for an edge case.
    """
    if not prompts_and_images:
        return []
    if len(prompts_and_images) == 1:
        prompt, images = prompts_and_images[0]
        return [generate(prompt, images, max_new_tokens=max_new_tokens)]

    import torch
    model, processor, device = get_model()

    try:
        texts = []
        images_batch = []
        any_images = False
        for prompt, images in prompts_and_images:
            content = []
            for img in (images or []):
                content.append({"type": "image", "image": img})
                any_images = True
            content.append({"type": "text", "text": prompt})
            messages = [{"role": "user", "content": content}]
            texts.append(processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True))
            images_batch.append(list(images) if images else [])

        # Qwen2.5-VL's processor accepts a flat list of images per batch
        # item when `images` is a list-of-lists; pass None only if truly no
        # item in the whole batch has any image (pure text-only batch).
        inputs = processor(text=texts, images=images_batch if any_images else None,
                            return_tensors="pt", padding=True)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        tokenizer = getattr(processor, "tokenizer", None)
        eos_token_id = getattr(tokenizer, "eos_token_id", None) if tokenizer else None
        pad_token_id = getattr(tokenizer, "pad_token_id", None) if tokenizer else None
        generate_kwargs = dict(max_new_tokens=max_new_tokens or VLM_MAX_NEW_TOKENS,
                                do_sample=False, repetition_penalty=1.15)
        if eos_token_id is not None:
            generate_kwargs["eos_token_id"] = eos_token_id
        if pad_token_id is not None:
            generate_kwargs["pad_token_id"] = pad_token_id
        elif eos_token_id is not None:
            generate_kwargs["pad_token_id"] = eos_token_id

        with torch.inference_mode():
            output_ids = model.generate(**inputs, **generate_kwargs)

        input_len = inputs["input_ids"].shape[1]
        trimmed = output_ids[:, input_len:]
        decoded = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=True)
        return [d.strip() for d in decoded]

    except Exception as e:
        logger.warning("True batched generate_batch() failed (%s); falling back to sequential per-item "
                        "generate() for this batch only.", e)
        return [generate(p, imgs, max_new_tokens=max_new_tokens) for p, imgs in prompts_and_images]