"""Read QuickBooks Online report exports (CSV or XLSX).

QBO reports start with a few title lines (company name, report name, dates)
before the column headings, and end with totals and a footer. The readers
here find the heading row by its column names and skip everything that is
not a data row.
"""
import csv
import io
import re
from datetime import date, datetime

import openpyxl


class QbParseError(ValueError):
    pass


def read_rows(data, filename):
    """Return the rows of a CSV or XLSX file as lists of cell values."""
    if (filename or "").lower().endswith(".xlsx") or data[:2] == b"PK":
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet = book.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    text = data.decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(text)))


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def find_columns(rows, required, optional=(), first_column=None):
    """Find the heading row and return (index of the next row, {key: column}).

    :param required: {key: [heading names]}; every key must be found
    :param optional: {key: [heading names]}
    :param first_column: key of a column that QBO leaves without a heading
        (the account name in a trial balance); it is column 0
    """
    wanted = dict(required, **dict(optional))
    for index, row in enumerate(rows):
        headings = [_norm(cell) for cell in row]
        columns = {}
        for key, names in wanted.items():
            for name in names:
                if name in headings:
                    columns[key] = headings.index(name)
                    break
        if all(key in columns for key in required):
            if first_column:
                columns[first_column] = 0
            return index + 1, columns
    names = ", ".join(names[0] for names in required.values())
    raise QbParseError(f"Column headings not found: {names}")


def cell(row, columns, key):
    column = columns.get(key)
    if column is None or column >= len(row):
        return None
    value = row[column]
    return value.strip() if isinstance(value, str) else value


def parse_amount(value):
    """Parse 1,234.56, -1,234.56, (1,234.56) and $1,234.56. Blank is 0."""
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if not text or text == "-":
        return 0.0
    try:
        amount = float(text)
    except ValueError as e:
        raise QbParseError(f"Not an amount: {value}") from e
    return -amount if negative else amount


def parse_date(value):
    """Parse a date cell; return None when the cell is not a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _is_total(name):
    return _norm(name).startswith("total") or _norm(name) in ("", "net income")


def parse_account_list(rows):
    """Account List report: [{name, type, detail_type, number}]."""
    start, columns = find_columns(
        rows,
        required={"name": ["account", "full name", "name"], "type": ["type", "account type"]},
        optional={"detail_type": ["detail type"], "number": ["account #", "account number", "number"]},
    )
    accounts = []
    for row in rows[start:]:
        name, qb_type = cell(row, columns, "name"), cell(row, columns, "type")
        if not name or not qb_type:
            continue
        accounts.append({
            "name": str(name),
            "type": str(qb_type),
            "detail_type": str(cell(row, columns, "detail_type") or ""),
            "number": str(cell(row, columns, "number") or "").strip(),
        })
    return accounts


def parse_trial_balance(rows):
    """Trial Balance report: [{name, balance}], balance = debit - credit."""
    start, columns = find_columns(
        rows, required={"debit": ["debit"], "credit": ["credit"]}, first_column="name"
    )
    lines = []
    for row in rows[start:]:
        name = cell(row, columns, "name")
        if _norm(name) == "total":
            break  # the report footer follows
        if not name or _is_total(name):
            continue
        try:
            balance = parse_amount(cell(row, columns, "debit")) - parse_amount(cell(row, columns, "credit"))
        except QbParseError:
            continue
        lines.append({"name": str(name), "balance": balance})
    return lines


def parse_aging(rows, partner_headings):
    """A/R or A/P Aging Detail: [{date, type, number, partner, due_date, open_balance}].

    Rows without a date are bucket headings and subtotals, and are skipped.
    """
    start, columns = find_columns(
        rows,
        required={
            "date": ["date"],
            "partner": partner_headings,
            "open_balance": ["open balance"],
        },
        optional={
            "type": ["transaction type"],
            "number": ["num", "no.", "number"],
            "due_date": ["due date"],
        },
    )
    entries = []
    for row in rows[start:]:
        when = parse_date(cell(row, columns, "date"))
        partner = cell(row, columns, "partner")
        if not when or not partner:
            continue
        balance = parse_amount(cell(row, columns, "open_balance"))
        if not balance:
            continue
        entries.append({
            "date": when,
            "type": str(cell(row, columns, "type") or ""),
            "number": str(cell(row, columns, "number") or "").strip(),
            "partner": str(partner),
            "due_date": parse_date(cell(row, columns, "due_date")) or when,
            "open_balance": balance,
        })
    return entries


def parse_contacts(rows, name_headings):
    """Customer or Vendor Contact List: [{name, email, phone}]."""
    start, columns = find_columns(
        rows,
        required={"name": name_headings},
        optional={"email": ["email"], "phone": ["phone numbers", "phone"]},
    )
    contacts = []
    for row in rows[start:]:
        name = cell(row, columns, "name")
        if not name or _is_total(name):
            continue
        contacts.append({
            "name": str(name),
            "email": str(cell(row, columns, "email") or "").strip(),
            "phone": str(cell(row, columns, "phone") or "").strip(),
        })
    return contacts


def parse_pl_by_month(rows):
    """Profit and Loss with columns by month: [{name, month, amount}].

    Amounts are as QBO shows them, positive for income and for expenses alike;
    the caller turns them into debits and credits by account type. Sub-accounts
    are listed by their own name, without the parent.
    """
    for index, row in enumerate(rows):
        months = {}
        for column, value in enumerate(row):
            parsed = None
            if isinstance(value, (datetime, date)):
                parsed = value if isinstance(value, date) else value.date()
            elif value:
                for fmt in ("%b %Y", "%B %Y"):
                    try:
                        parsed = datetime.strptime(str(value).strip(), fmt).date()
                        break
                    except ValueError:
                        continue
            if parsed:
                months[column] = parsed.replace(day=1)
        if months:
            break
    else:
        raise QbParseError("Month columns not found: export Profit and Loss with columns by month")
    amounts = []
    for row in rows[index + 1:]:
        name = row[0] if row else None
        if not name or _is_total(name) or _norm(name) in ("gross profit", "net operating income", "net other income"):
            continue
        for column, month in months.items():
            if column < len(row):
                amount = parse_amount(row[column])
                if amount:
                    amounts.append({"name": str(name).strip(), "month": month, "amount": amount})
    return amounts
