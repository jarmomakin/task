# Submission

**Name:** Jarmo Mäkinen
**Email:** jarmo.makin@gmail.com

## Approach

The parser uses `pdfplumber`'s layout-preserving text extraction and a pipeline of rule-based heuristics:

1. **Section detection** - The document is split into three sections (income statement, assets, liabilities) by scanning for Finnish keyword anchors (`tuloslaskelma`, `tase`, `vastaavaa`, `vastattavaa`, `aktiva`, `passiva`). Noise sections (cash flow, notes, key figures, board proposal) are stripped by stopping at known markers.

2. **Year detection** - Fiscal years are extracted from header and column-header lines using a four-digit year regex; years are sorted descending so columns map naturally to most-recent-first.

3. **Number tokenisation** - A regex respecting Finnish thousand-separator spaces (`1 200 000`) without merging adjacent table columns. Negative values and decimal commas are normalised.

4. **Variable matching** - Each target variable has a tuple of Finnish label regex patterns. Each section is scanned for the first matching line; amounts on that line are selected based on year count and whether a budget column is present.

5. **Budget-column handling** - Detected by the presence of `budjetti` in the income statement header. When found, the last two numeric columns (actual years) are taken instead of the first two.

6. **Scaling** - When `1 000 euroa` appears in the document, all extracted values are multiplied by 1 000 to convert to euros.

Key decisions:

- Anchor balance-sheet total patterns to start-of-normalized-line to avoid matching subtotal rows (e.g. `Pitkaikainen vieras paaoma yht.` instead of `Vieras paaoma yhteensa`).
- Extract amounts from the raw (non-normalised) line to preserve spacing that distinguishes adjacent columns.

## AI Tools

**GitHub Copilot (Claude Sonnet 4.6)** was used throughout:

- Analyzed the README and expected JSON fixtures to understand scope and edge cases before writing any code.
- Inspected raw extracted text from all five PDFs inside Docker to map Finnish label variants and column layouts.
- Implemented the full parser in `src/parser.py` iteratively: first draft, then two targeted fix passes after examining test failure output and debug traces.
- The two key bugs found and fixed via AI-assisted debug logging: (1) greedy number regex merging adjacent table columns into a single token, and (2) balance-sheet total labels matching subtotal rows due to missing start-of-line anchors.
