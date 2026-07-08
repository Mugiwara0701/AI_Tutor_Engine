"""
ocr_engine.py — page-level text acquisition + confidence scoring.

Most NCERT PDFs are born-digital (real text layer), so PyMuPDF's own text
extraction (already used by pdf_parser for lines) is the fast, high-confidence
path. This module is what actually decides *if* a page needs real OCR:

  1. no usable text layer at all (image-only page), OR
  2. a text layer exists but doesn't match the book's expected script
     (the legacy-font symptom, e.g. a Hindi/Sanskrit PDF whose text layer
     decodes to Latin-looking gibberish because of a non-Unicode font's
     custom glyph-to-codepoint mapping — see modules/language_detector.py
     for the full explanation).

and, if so, runs pytesseract on a rendered page image and reports its
confidence — used to fill `pages[].ocr_confidence` and `quality.ocr` in the
final JSON.

Robustness contract (per the language-robustness milestone): this module
must NEVER raise out of ocr_page()/ocr_chapter_pages(), regardless of
whether pytesseract/Pillow are installed, whether the system tesseract
binary exists, or whether the specific language pack (hin/san/...) is
installed. Every failure mode degrades to the best available fallback
(other OCR language -> raw existing text layer -> empty result) with a
logged warning, never a crash that takes down the whole chapter/pipeline.

pip install pytesseract pillow  (+ system tesseract-ocr binary,
+ the relevant tesseract-ocr-<lang> package for non-English books)
"""
import io
import logging
from dataclasses import dataclass

import fitz  # PyMuPDF

from modules import language_detector

logger = logging.getLogger("ncert_pipeline.ocr")

try:
    import pytesseract
    from PIL import Image
    _TESSERACT_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _TESSERACT_AVAILABLE = False


@dataclass
class PageOCRResult:
    page: int
    text: str
    confidence: float
    # "text_layer" | "tesseract" | "tesseract_fallback_<lang>" |
    # "text_layer_unverified" | "none"
    engine: str
    word_count: int


def _text_layer_for_page(doc: fitz.Document, pno: int) -> str:
    return doc[pno].get_text("text")


def _ocr_lang_fallback_chain(tess_lang: str) -> list:
    """Languages to try, in order: the requested one, then English (nearly
    every NCERT page has at least some Latin-script content — page numbers,
    figure labels, English loanwords — and `eng` is the one language pack
    that's virtually always present, so it's a strictly better last resort
    than giving up)."""
    chain = [tess_lang]
    if tess_lang != "eng":
        chain.append("eng")
    return chain


def _degrade(pno: int, fallback_text: str, reason: str) -> "PageOCRResult":
    """Common 'OCR truly isn't available/working' exit path. Never raises.
    Prefers returning the original (possibly imperfect or garbled) text
    layer over an empty result — per spec, the pipeline should continue
    whenever possible rather than dropping a page's content entirely."""
    logger.warning("%s (page %d) — continuing with the existing text layer "
                    "instead of failing the chapter.", reason, pno)
    if fallback_text and fallback_text.strip():
        return PageOCRResult(page=pno, text=fallback_text, confidence=0.15,
                              engine="text_layer_unverified", word_count=len(fallback_text.split()))
    return PageOCRResult(page=pno, text="", confidence=0.0, engine="none", word_count=0)


def _tesseract_ocr_page(doc: fitz.Document, pno: int, lang: str = "en", dpi: int = 200,
                         fallback_text: str = "") -> "PageOCRResult":
    if not _TESSERACT_AVAILABLE:
        return _degrade(pno, fallback_text, "pytesseract/Pillow not installed — cannot OCR page")

    tess_lang = language_detector.ocr_lang_code(lang)
    try:
        page = doc[pno]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
    except Exception as e:
        return _degrade(pno, fallback_text, f"could not rasterize page for OCR ({e})")

    for candidate_lang in _ocr_lang_fallback_chain(tess_lang):
        try:
            data = pytesseract.image_to_data(img, lang=candidate_lang, output_type=pytesseract.Output.DICT)
        except Exception as e:
            # Covers: tesseract binary missing (TesseractNotFoundError),
            # requested traineddata not installed (TesseractError), or any
            # other OS/runtime failure. Try the next language in the chain
            # rather than giving up immediately.
            logger.warning("Tesseract OCR failed for page %d with lang='%s' (%s) — trying next fallback.",
                            pno, candidate_lang, e)
            continue

        words = [w for w in data.get("text", []) if w.strip()]
        confs = [int(c) for c, w in zip(data.get("conf", []), data.get("text", [])) if w.strip() and c != "-1"]
        text = " ".join(words)
        avg_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        engine_name = "tesseract" if candidate_lang == tess_lang else f"tesseract_fallback_{candidate_lang}"
        return PageOCRResult(page=pno, text=text, confidence=round(avg_conf, 3), engine=engine_name,
                              word_count=len(words))

    return _degrade(pno, fallback_text,
                     f"tesseract could not OCR page in language '{tess_lang}' or its fallback")


def ocr_page(doc: fitz.Document, pno: int, min_text_layer_chars: int = 20, lang: str = "en") -> PageOCRResult:
    """Text-layer first; only pays the OCR cost when the page genuinely has
    no usable text layer (e.g. a scanned image page) OR when the text layer
    exists but doesn't match the expected script for `lang` (legacy-font
    garbling — see module docstring)."""
    text = _text_layer_for_page(doc, pno)
    if len(text.strip()) >= min_text_layer_chars:
        if language_detector.is_text_usable_for_language(text, lang):
            wc = len(text.split())
            return PageOCRResult(page=pno, text=text, confidence=0.98, engine="text_layer", word_count=wc)
        logger.info("Page %d text layer doesn't match the expected '%s' script (possible legacy/"
                    "non-Unicode font encoding) — falling back to OCR.", pno, lang)
    else:
        logger.info("Page %d has no usable text layer — falling back to OCR.", pno)
    return _tesseract_ocr_page(doc, pno, lang=lang, fallback_text=text)


def ocr_chapter_pages(pdf_path: str, lang: str = "en") -> list:
    doc = fitz.open(pdf_path)
    results = [ocr_page(doc, p, lang=lang) for p in range(doc.page_count)]
    doc.close()
    return results


def overall_ocr_confidence(results: list) -> float:
    if not results:
        return 0.0
    return round(sum(r.confidence for r in results) / len(results), 3)