"""Indian number-plate cleaning, validation and OCR-confusion correction.

Format handled: SS DD LLL NNNN
  SS   = 2-letter state/UT code      (TN)
  DD   = 1-2 digit RTO district code (37, or 3 in DL3C...)
  LLL  = 1-3 letter series           (AB)
  NNNN = 4 digit number              (1234)
Not handled: BH-series (22BH1234AA), temporary and diplomatic plates.
"""
import re

STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ",
    "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
    "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}

MAX_FIXES = 2  # more corrections than this = probably not a plate
PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")

# Where a digit is expected but OCR gave a letter, and vice versa.
TO_DIGIT = {"O": "0", "D": "0", "Q": "0", "U": "0", "I": "1", "L": "1",
            "J": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "A": "4", "T": "7"}
TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G",
             "4": "A", "7": "T"}


def clean(text: str) -> str:
    """Uppercase and strip everything except A-Z and 0-9."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def is_valid(plate: str) -> bool:
    return bool(PLATE_RE.match(plate)) and plate[:2] in STATE_CODES


def _coerce(chunk: str, kind: str):
    """Force every char in chunk to a letter ('L') or digit ('D'). Returns (text, fixes) or None."""
    out, fixes = [], 0
    for ch in chunk:
        if kind == "L":
            if ch.isalpha():
                out.append(ch)
            elif ch in TO_LETTER:
                out.append(TO_LETTER[ch]); fixes += 1
            else:
                return None
        else:
            if ch.isdigit():
                out.append(ch)
            elif ch in TO_DIGIT:
                out.append(TO_DIGIT[ch]); fixes += 1
            else:
                return None
    return "".join(out), fixes


def _fit(s: str):
    """Best (plate, fixes) for an exact-length string, trying each valid layout."""
    best = None
    n = len(s)
    for d in (2, 1):              # prefer 2-digit district codes
        for ser in (2, 1, 3):     # prefer 2-letter series
            if 2 + d + ser + 4 != n:
                continue
            pieces = [(s[:2], "L"), (s[2:2 + d], "D"),
                      (s[2 + d:2 + d + ser], "L"), (s[-4:], "D")]
            text, fixes = "", 0
            for chunk, kind in pieces:
                r = _coerce(chunk, kind)
                if r is None:
                    break
                text += r[0]; fixes += r[1]
            else:
                # 1-digit district codes are printed mainly on Delhi plates (DL3C...);
                # elsewhere treat that layout as a last resort.
                cost = fixes + (2 if d == 1 and text[:2] != "DL" else 0)
                if is_valid(text) and fixes <= MAX_FIXES and (best is None or cost < best[2]):
                    best = (text, fixes, cost)
    return best[:2] if best else None


def normalize_ocr(raw: str):
    """OCR text -> (valid_plate, n_fixes) or None.

    Tries the whole cleaned string first; if OCR picked up extra junk
    (e.g. the 'IND' strip on HSRP plates), tries every 8-10 char window.
    """
    s = clean(raw)
    if s.startswith("IND"):
        s = s[3:]
    if len(s) < 8:
        return None
    best = _fit(s) if len(s) <= 10 else None
    if best is None:
        for L in (10, 9, 8):
            for i in range(0, len(s) - L + 1):
                r = _fit(s[i:i + L])
                if r and (best is None or r[1] < best[1]):
                    best = (r[0], r[1] + 1)   # small penalty for trimming
    return best


def normalize_user_input(raw: str):
    """Form input: strict clean only, no confusion fixing (humans type the real thing)."""
    s = clean(raw)
    return s if is_valid(s) else None


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def mask_mobile(m: str) -> str:
    return "XXXXXX" + m[-4:] if m and len(m) >= 4 else m
