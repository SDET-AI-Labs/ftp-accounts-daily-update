import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Union


def _candidate_credentials_paths() -> List[Path]:
    """Return a list of possible credentials.txt locations to try in order."""
    candidates: List[Path] = []
    # 1) Environment override
    env_path = os.environ.get("CREDENTIALS_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    here = Path(__file__).resolve()
    src_dir = here.parent  # src/
    root_dir = src_dir.parent

    # 2) Alongside this file (src/credentials.txt)
    candidates.append(src_dir / "credentials.txt")
    # 3) Project root creds (credentials.txt)
    candidates.append(root_dir / "credentials.txt")
    # 4) CWD-based paths (when launched from elsewhere)
    cwd = Path.cwd()
    candidates.append(cwd / "src" / "credentials.txt")
    candidates.append(cwd / "credentials.txt")

    # 5) PyInstaller extracted data dir (if packed with --add-data src/credentials.txt;src)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "src" / "credentials.txt")

    # Deduplicate while preserving order
    seen = set()
    uniq: List[Path] = []
    for p in candidates:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return uniq


def _resolve_credentials_path() -> Path:
    for p in _candidate_credentials_paths():
        if p.exists():
            return p
    # Fallback to src/credentials.txt next to this file
    return Path(__file__).resolve().parent / "credentials.txt"


def _clean_value(raw_value: str) -> str:
    """Strip quotes and trailing comments from a value line.

    If the value contains a quoted string, return the first quoted segment verbatim (without quotes),
    even if it contains a '#'. Only treat '#' as a comment delimiter when the value is unquoted.
    """
    rv = raw_value.strip()
    # Prefer explicit quoted content
    # Match either 'single-quoted' or "double-quoted" segments; group 2 captures the content
    m = re.search(r"([\'\"])(.*?)\1", rv)
    if m:
        return m.group(2).strip()
    # No quoted content found; remove inline comments and trim
    value = rv.split('#', 1)[0].strip()
    # Remove surrounding quotes if present (defensive)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return value.strip()


def _normalise_key(raw_key: str) -> str:
    return re.sub(r"[^a-z]", "", raw_key.lower())


def _derive_folder_label(account_name: str, raw_key: str) -> str:
    label = raw_key.strip()
    if not label:
        return "Folder"

    pattern = re.compile(re.escape(account_name), re.IGNORECASE)
    label = pattern.sub("", label).strip(" _-:")
    if not label:
        label = raw_key.strip()

    label = label.replace("_", " ").replace("-", " ")
    if label:
        label = label[0].upper() + label[1:]
    return label or "Folder"


def _parse_folder_value(raw: str) -> tuple[str, List[str]]:
    """Extract a folder path and optional filename filters from a free-form value.

    Supports values like:
      "'/Woodford/RAReporting' files we check in the folder \"RevAI_Fleet\", \"RevAI_RentalAgreements\", \"Daily_Bookings\""
    -> ("/Woodford/RAReporting", ["RevAI_Fleet", "RevAI_RentalAgreements", "Daily_Bookings"]).
    """
    value = raw.strip()
    # Find all quoted segments (single or double quotes)
    quoted = re.findall(r"'([^']*)'|\"([^\"]*)\"", value)
    # Flatten, keeping non-empty
    segments: List[str] = [a or b for (a, b) in quoted if (a or b)]

    path = value
    filters: List[str] = []

    # Prefer the first quoted segment that looks like a path
    for seg in segments:
        if seg.startswith("/") or "/" in seg:
            path = seg
            break
    else:
        # No quoted path found; treat the entire value as the path (do not split on spaces)
        # This preserves folder names that contain spaces, e.g., "/Woodford/Processed Booking".
        path = value if value else "/"

    # Remaining quoted segments (excluding the chosen path) are treated as filename filters
    for seg in segments:
        if seg == path:
            continue
        if seg:
            filters.append(seg)

    return path or "/", filters


def load_multiple_configs_from_file(file_path: Union[Path, str, None] = None) -> List[Dict]:
    if file_path is None:
        file_path = _resolve_credentials_path()
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Credentials file not found at {file_path}")

    content = file_path.read_text(encoding="utf-8")
    blocks = re.split(r"-{5,}", content)

    configs: List[Dict] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        account: Dict = {"name": lines[0], "folders": []}
        last_folder = None

        for line in lines[1:]:
            if line.startswith("--"):
                continue
            if ":" not in line:
                # Continuation line (e.g., extra filters on the next line)
                # Extract quoted strings and append as filters to the last folder if present.
                if last_folder is not None:
                    _p, extra_filters = _parse_folder_value(line)
                    if extra_filters:
                        existing = set(s.lower() for s in last_folder.get("filters", []))
                        for f in extra_filters:
                            if f.lower() not in existing:
                                last_folder.setdefault("filters", []).append(f)
                                existing.add(f.lower())
                continue

            raw_key, raw_value = line.split(":", 1)
            value = _clean_value(raw_value)
            key_norm = _normalise_key(raw_key)

            if key_norm in {"host", "hosturl", "ftpurl", "url"}:
                host_match = re.search(r"([a-zA-Z0-9.-]+)", value)
                if host_match:
                    account["host"] = host_match.group(1)
                port_match = re.search(r"(\d{2,5})", value)
                if port_match:
                    account["port"] = int(port_match.group(1))
            elif key_norm == "username":
                account["username"] = value
            elif key_norm == "password":
                account["password"] = value
            elif key_norm == "port":
                digits = re.findall(r"\d+", value)
                if digits:
                    account["port"] = int(digits[0])
            elif key_norm == "folders":
                # Section marker, skip to next line where actual folder entries appear.
                continue
            elif key_norm in {"folder"}:
                path, filters = _parse_folder_value(value)
                last_folder = {"label": "Folder", "path": path or "/", "filters": filters}
                account["folders"].append(last_folder)
            elif key_norm in {"folders", "locations"}:
                # Section marker, skip to next line where actual folder entries appear.
                continue
            else:
                folder_label = _derive_folder_label(account["name"], raw_key)
                path, filters = _parse_folder_value(value)
                last_folder = {"label": folder_label, "path": path, "filters": filters}
                account["folders"].append(last_folder)

        if "port" not in account:
            account["port"] = 22

        if all(key in account for key in ("host", "username", "password")):
            if not account["folders"]:
                account["folders"].append({"label": "Root", "path": "/"})
            configs.append(account)

    return configs