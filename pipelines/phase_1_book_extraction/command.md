Good — that confirms this is a Windows setup (`.venv/Scripts/activate`). Here's the full setup sequence for your VS Code terminal:

**1. Create and activate a virtual environment** (from the project root, in PowerShell/cmd terminal):

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

You should see `(.venv)` appear at the start of your terminal prompt once it's active. If PowerShell blocks the activation script, run this once first:

```bash
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**2. Upgrade pip** (avoids install failures on some of the heavier packages below):

```bash
python -m pip install --upgrade pip
```

**3. Install everything from requirements.txt:**

```bash
pip install -r requirements.txt
```

That pulls in: `pymupdf`, `pydantic`, `tqdm`, `yake`, `textstat`, `pytesseract`, `pillow`, `torch`, `transformers`, `accelerate`, and `bitsandbytes` (skipped automatically on macOS, since it's CUDA-only).

**4. Only if you don't have an NVIDIA GPU / want CPU-only torch** (the plain `pip install torch` above pulls a huge CUDA build by default on some setups) — optional, only run this instead of step 3's torch line if you hit install issues:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

**5. Tesseract OCR binary** — this is a **system** install, not pip, and it's required for scanned/image-only PDF pages:

- Windows: download and run the installer from https://github.com/UB-Mannheim/tesseract/wiki, then make sure its install folder is on your PATH (or set `pytesseract.pytesseract.tesseract_cmd` — but the pipeline doesn't currently do that, so PATH is simplest).

**6. Verify the install:**

```bash
python -c "import fitz, pydantic, tqdm, yake, textstat, pytesseract, PIL, torch, transformers, accelerate; print('OK')"
```

**7. Run it:**

```bash
python pipeline.py --no-vlm
```

(`--no-vlm` first is a good sanity check since it skips the Qwen2.5-VL model load entirely — confirms PDFs are found and parsed before you pay the cost of downloading/loading the ~3B-param model.)

Once that's clean, drop the flag for a real run:

```bash
python pipeline.py
```

One thing to flag: I was in the middle of building the multi-book orchestrator (`book_orchestrator.py`) you asked for when this message came in — that file didn't get created yet. Let me know and I'll pick that back up.
