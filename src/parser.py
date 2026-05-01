"""
Financial Statement Parser

YOUR TASK: Implement the parse_financial_statement function below.

Given a path to a PDF containing Finnish financial statements,
extract the target variables and return a list of FinancialStatement objects.

Some PDFs contain data for multiple fiscal years - return one object per year.

You may:
- Use the provided pdf_reader module or implement your own extraction
- Add helper functions, classes, or modules as needed
- Use any approach you think is appropriate

Run tests with: docker compose run test
"""

from pathlib import Path
import re
from src.schema import FinancialStatement
from src.pdf_reader import extract_pdf


STOP_MARKERS = (
    "rahavirtalaskelma",
    "liitetiedot",
    "tunnusluvut",
    "hallituksen esitys",
)


VARIABLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "revenue": (r"\bliikevaihto\b",),
    "operating_profit": (
        r"\bliikevoitto\b",
        r"\bliiketulos\b",
        r"\bliiketoiminnan\s+tulos\b",
    ),
    "profit_before_taxes": (
        r"\bvoitto\s*\(?.*\)?\s*ennen\s+veroja\b",
        r"\btulos\s+ennen\s+tilinpäätössiirtoja\s+ja\s+veroja\b",
        r"\btulos\s+ennen\s+veroja\b",
    ),
    "net_profit": (
        r"\btilikauden\s+voitto\b",
        r"\btilikauden\s+tulos\b",
    ),
    "fixed_assets": (
        r"^pysyvät\s+vastaavat\s+yhteensä\b",
        r"^pysyvät\s+vastaavat\s+yht\.?\b",
    ),
    "current_assets": (
        r"^vaihtuvat\s+vastaavat\s+yhteensä\b",
        r"^vaihtuvat\s+vastaavat\s+yht\.?\b",
    ),
    "total_assets": (r"^vastaavaa\s+yhteensä\b",),
    "equity": (
        r"^oma\s+pääoma\s+yhteensä\b",
        r"^oma\s+pääoma\s+yht\.?\b",
    ),
    "liabilities": (
        r"^vieras\s+pääoma\s+yhteensä\b",
        r"^vieras\s+pääoma\s+yht\.?\b",
    ),
    "total_equity_and_liabilities": (r"^vastattavaa\s+yhteensä\b",),
}


def _normalize_line(line: str) -> str:
    line = line.lower().replace("−", "-")
    return re.sub(r"\s+", " ", line).strip()


def _extract_years(lines: list[str]) -> list[int]:
    years: list[int] = []
    for line in lines:
        for match in re.finditer(r"\b(20\d{2})\b", line):
            year = int(match.group(1))
            if 2000 <= year <= 2100 and year not in years:
                years.append(year)
    return sorted(years, reverse=True)


def _extract_amounts(line: str) -> list[float]:
    # Parse Finnish-style amounts while keeping adjacent table columns separate.
    matches = re.findall(r"[-−]?\d{1,3}(?:\s\d{3})*(?:,\d+)?|[-−]?\d+(?:,\d+)?", line)
    values: list[float] = []
    for token in matches:
        cleaned = token.replace("−", "-").replace(" ", "")
        cleaned = cleaned.replace(",", ".")
        try:
            values.append(float(cleaned))
        except ValueError:
            continue
    return values


def _select_values_for_years(values: list[float], year_count: int, has_budget_column: bool) -> list[float]:
    if not values:
        return []

    if year_count <= 1:
        return [values[-1]]

    if has_budget_column and len(values) >= 3:
        return values[-2:]

    if len(values) >= 2:
        return values[:2]

    return []


def _find_statement_sections(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    normalized = [_normalize_line(line) for line in lines]

    idx_tulos = next((i for i, line in enumerate(normalized) if "tuloslaskelma" in line), 0)
    idx_tase = next((i for i, line in enumerate(normalized) if line == "tase"), len(lines))

    income_lines = lines[idx_tulos:idx_tase]
    balance_lines = lines[idx_tase:]

    stop_index = len(balance_lines)
    for i, line in enumerate(balance_lines):
        lower = _normalize_line(line)
        if any(marker in lower for marker in STOP_MARKERS):
            stop_index = i
            break
    balance_lines = balance_lines[:stop_index]

    normalized_balance = [_normalize_line(line) for line in balance_lines]
    idx_assets = next(
        (
            i
            for i, line in enumerate(normalized_balance)
            if (
                "vastaavaa" in line
                or "aktiva" in line
                or "v a s t a a v a a" in line
            )
            and "vastattavaa" not in line
        ),
        0,
    )
    idx_liabilities = next(
        (
            i
            for i, line in enumerate(normalized_balance)
            if "vastattavaa" in line or "passiva" in line or "v a s t a t t a v a a" in line
        ),
        len(balance_lines),
    )

    assets_lines = balance_lines[idx_assets:idx_liabilities]
    liabilities_lines = balance_lines[idx_liabilities:]
    return income_lines, assets_lines, liabilities_lines


def _extract_variable_map(
    lines: list[str],
    years: list[int],
    multiplier: float,
    has_budget_column: bool,
    variable_names: tuple[str, ...],
) -> dict[str, dict[int, float]]:
    extracted: dict[str, dict[int, float]] = {}
    normalized_lines = [_normalize_line(line) for line in lines]

    for variable in variable_names:
        patterns = VARIABLE_PATTERNS[variable]
        for raw_line, norm_line in zip(lines, normalized_lines):
            if not any(re.search(pattern, norm_line) for pattern in patterns):
                continue

            values = _extract_amounts(raw_line)
            selected = _select_values_for_years(values, len(years), has_budget_column)
            if not selected:
                continue

            mapping: dict[int, float] = {}
            for year, value in zip(years, selected):
                mapping[year] = value * multiplier

            if mapping:
                extracted[variable] = mapping
                break

    return extracted


def parse_financial_statement(pdf_path: str | Path) -> list[FinancialStatement]:
    """
    Parse a Finnish financial statement PDF and extract key metrics.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of FinancialStatement objects, one per fiscal year found in the PDF.
        Most PDFs have one year, but some have multiple (e.g., current + previous).

    Example:
        >>> results = parse_financial_statement("pdfs/test_01.pdf")
        >>> for stmt in results:
        ...     print(f"{stmt.fiscal_year}: revenue={stmt.revenue}")
    """
    doc = extract_pdf(pdf_path)
    lines = [line.rstrip() for line in doc.text.splitlines() if line.strip()]
    normalized_lines = [_normalize_line(line) for line in lines]

    multiplier = 1000.0 if any("1 000 euro" in line or "1000 euro" in line for line in normalized_lines) else 1.0

    income_lines, assets_lines, liabilities_lines = _find_statement_sections(lines)

    header_sample = lines[:30] + income_lines[:20] + assets_lines[:10] + liabilities_lines[:10]
    years = _extract_years(header_sample)
    if not years:
        raise ValueError(f"Could not detect fiscal year from: {pdf_path}")

    has_budget_column = any("budjetti" in _normalize_line(line) for line in income_lines[:15])

    year_data: dict[int, FinancialStatement] = {
        year: FinancialStatement(fiscal_year=year) for year in years
    }

    income_vars = (
        "revenue",
        "operating_profit",
        "profit_before_taxes",
        "net_profit",
    )
    assets_vars = (
        "fixed_assets",
        "current_assets",
        "total_assets",
    )
    liabilities_vars = (
        "equity",
        "liabilities",
        "total_equity_and_liabilities",
    )

    extracted_income = _extract_variable_map(
        income_lines, years, multiplier, has_budget_column, income_vars
    )
    extracted_assets = _extract_variable_map(
        assets_lines, years, multiplier, has_budget_column, assets_vars
    )
    extracted_liabilities = _extract_variable_map(
        liabilities_lines, years, multiplier, has_budget_column, liabilities_vars
    )

    for variable_maps in (extracted_income, extracted_assets, extracted_liabilities):
        for variable, values_by_year in variable_maps.items():
            for year, value in values_by_year.items():
                if year in year_data:
                    setattr(year_data[year], variable, value)

    return list(year_data.values())


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.parser <pdf_path>")
        sys.exit(1)

    results = parse_financial_statement(sys.argv[1])
    print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
