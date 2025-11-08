from __future__ import annotations

import argparse
import datetime
import logging
from pathlib import Path
import sys
from stat import S_ISREG

import pandas as pd

from src.config import load_multiple_configs_from_file
from src.sftp_connector import SFTPConnector


# When frozen as a single-file EXE (PyInstaller --onefile), __file__ points inside the temp bundle.
# Prefer the executable's directory so outputs are created next to the EXE.
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
RESULT_DIR = BASE_DIR / "result"
ERROR_DIR = BASE_DIR / "errors"
LOG_DIR = BASE_DIR / "logs"


def _matches_filter(value: str, pattern: str | None) -> bool:
    if not pattern:
        return True
    return pattern.lower() in value.lower()


def collect_latest_file_details(
    account_filter: str | None = None,
    folder_filter: str | None = None,
    previous_day: bool = False,
    today_only: bool = False,
    skip_accounts: list[str] | None = None,
    on_date: datetime.date | None = None,
):
    configs = load_multiple_configs_from_file()
    results = []
    logger = logging.getLogger(__name__)

    for config in configs:
        if not _matches_filter(config["name"], account_filter):
            continue
        if skip_accounts and any(_matches_filter(config["name"], s) for s in skip_accounts):
            logger.info("Skipping account '%s' due to skip list", config["name"])
            continue

        logger.info("Connecting to '%s' (%s)", config["name"], config.get("host", "-"))
        connector = SFTPConnector(
            host=config["host"],
            port=config.get("port", 22),
            username=config["username"],
            password=config["password"],
        )

        try:
            connector.connect()
            logger.info("Connected to '%s'", config["name"])
        except Exception as exc:  # noqa: BLE001
            logger.error("Connection error for '%s': %s", config["name"], exc)
            results.append(
                {
                    "Account Name": config["name"],
                    "Folder": "-",
                    "Latest File Name": "-",
                    "Latest File Date": f"Connection error: {exc}",
                }
            )
            connector.disconnect()
            continue

        try:
            folders = config.get("folders", [])
            if folder_filter:
                folders = [folder for folder in folders if _matches_filter(folder.get("label", ""), folder_filter)]

            if not folders:
                logger.warning("No folders configured for '%s' matching filter '%s'", config["name"], folder_filter)
                results.append(
                    {
                        "Account Name": config["name"],
                        "Folder": folder_filter or "-",
                        "Latest File Name": "-",
                        "Latest File Date": "Folder not configured",
                    }
                )
                continue

            for folder in folders:
                folder_label = folder.get("label", "Folder")
                folder_path = folder.get("path", "/")
                filters = folder.get("filters", [])
                logger.info("Checking folder '%s' (%s) for '%s'", folder_label, folder_path, config["name"])
                logger.info("Folder filters for '%s': %s", folder_label, filters if filters else "<none>")
                try:
                    # Special handling: if filters are provided (e.g., Inventory prefixes),
                    # return one line per prefix with its own latest file.
                    if filters and len(filters) >= 1:
                        # If an explicit on_date is provided, restrict per-prefix lookup to that date.
                        per = connector.get_latest_files_per_prefix(folder_path, filters, on_date=on_date if today_only else None)
                        for pfx_lower, (fname, fdt) in per.items():
                            label = f"{folder_label} - {pfx_lower}"
                            if fname and fdt:
                                logger.info(
                                    "Latest file for '%s' in '%s': %s (%s)",
                                    config["name"],
                                    label,
                                    fname,
                                    fdt,
                                )
                                results.append(
                                    {
                                        "Account Name": config["name"],
                                        "Folder": label,
                                        "Latest File Name": fname,
                                        "Latest File Date": fdt,
                                    }
                                )
                            else:
                                # Fallback to any date for that prefix
                                fb_name, fb_dt = connector.get_latest_file_info(folder_path, name_filters=[pfx_lower])
                                if fb_name and fb_dt:
                                    logger.warning(
                                        "No file met the date criteria for '%s' in '%s'; using latest available file instead: %s (%s)",
                                        config["name"],
                                        label,
                                        fb_name,
                                        fb_dt,
                                    )
                                    results.append(
                                        {
                                            "Account Name": config["name"],
                                            "Folder": label,
                                            "Latest File Name": fb_name,
                                            "Latest File Date": fb_dt,
                                        }
                                    )
                                else:
                                    logger.warning(
                                        "No files found for '%s' in '%s' (%s). Recording '-'",
                                        config["name"],
                                        label,
                                        folder_path,
                                    )
                                    results.append(
                                        {
                                            "Account Name": config["name"],
                                            "Folder": label,
                                            "Latest File Name": "-",
                                            "Latest File Date": "-",
                                        }
                                    )
                        continue

                    if today_only:
                        target_date = on_date or datetime.datetime.now().date()
                        latest_file, latest_date = connector.get_latest_file_info_on_date(
                            folder_path, target_date, name_filters=filters
                        )
                    elif previous_day:
                        # previous_day semantics: latest strictly before today (or before on_date if provided)
                        target_date = on_date or datetime.datetime.now().date()
                        latest_file, latest_date = connector.get_latest_file_info_before_date(
                            folder_path, target_date, name_filters=filters
                        )
                    else:
                        latest_file, latest_date = connector.get_latest_file_info(
                            folder_path, name_filters=filters
                        )
                    if latest_file and latest_date:
                        logger.info(
                            "Latest file for '%s' in '%s': %s (%s)",
                            config["name"],
                            folder_label,
                            latest_file,
                            latest_date,
                        )
                        results.append(
                            {
                                "Account Name": config["name"],
                                "Folder": folder_label,
                                "Latest File Name": latest_file,
                                "Latest File Date": latest_date,
                            }
                        )
                    else:
                        # Try a fallback: if date-based selection returned none, pick the latest available regardless of date.
                        fb_file = fb_date = None
                        if today_only or previous_day:
                            try:
                                fb_file, fb_date = connector.get_latest_file_info(folder_path, name_filters=filters)
                            except Exception as exc:  # noqa: BLE001
                                logger.error("Fallback latest lookup failed for '%s' in '%s': %s", config["name"], folder_label, exc)
                        if fb_file and fb_date:
                            logger.warning(
                                "No file met the date criteria for '%s' in '%s' (%s); using latest available file instead: %s (%s)",
                                config["name"],
                                folder_label,
                                folder_path,
                                fb_file,
                                fb_date,
                            )
                            results.append(
                                {
                                    "Account Name": config["name"],
                                    "Folder": folder_label,
                                    "Latest File Name": fb_file,
                                    "Latest File Date": fb_date,
                                }
                            )
                        else:
                            # Provide a more specific reason in logs while writing '-' to Excel
                            try:
                                all_attrs = connector.list_files_in_folder(folder_path)
                                reg_files = [f for f in all_attrs if hasattr(f, "st_mode") and S_ISREG(f.st_mode)]
                                reason = ""
                                if not reg_files:
                                    reason = "Empty folder"
                                else:
                                    # Apply name filters if any
                                    matched = reg_files
                                    if filters:
                                        lowered = [s.lower() for s in filters if s]
                                        if lowered:
                                            matched = [f for f in matched if any(s in f.filename.lower() for s in lowered)]
                                    if not matched and filters:
                                        reason = "No files matched configured filters"
                                    elif previous_day:
                                        today = datetime.datetime.now().date()
                                        before = [f for f in matched if datetime.datetime.fromtimestamp(f.st_mtime).date() < today]
                                        if not before:
                                            reason = "No file before today"
                                    elif today_only:
                                        today = datetime.datetime.now().date()
                                        on = [f for f in matched if datetime.datetime.fromtimestamp(f.st_mtime).date() == today]
                                        if not on:
                                            reason = "No file from today"
                                reason_suffix = f" — reason: {reason}" if reason else ""
                            except Exception:
                                reason_suffix = ""

                            logger.warning(
                                "No files found for '%s' in '%s' (%s). Recording '-'%s",
                                config["name"],
                                folder_label,
                                folder_path,
                                reason_suffix,
                            )
                            results.append(
                                {
                                    "Account Name": config["name"],
                                    "Folder": folder_label,
                                    "Latest File Name": "-",
                                    "Latest File Date": "-",
                                }
                            )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Error retrieving latest file for '%s' in '%s': %s",
                        config["name"],
                        folder_label,
                        exc,
                    )
                    results.append(
                        {
                            "Account Name": config["name"],
                            "Folder": folder_label,
                            "Latest File Name": "-",
                            "Latest File Date": f"Error: {exc}",
                        }
                    )
        finally:
            connector.disconnect()
            logger.info("Disconnected from '%s'", config["name"])

    return results


def write_results_to_excel(rows, output_path: Path | None = None):
    if output_path is None:
        today = datetime.datetime.now().strftime("%m-%d-%Y")
        output_path = RESULT_DIR / f"Accounts_Daily_Update_{today}.xlsx"
    else:
        output_path = Path(output_path).expanduser().resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows)
    df.to_excel(output_path, index=False)
    return output_path


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Collect latest SFTP file timestamps and export to Excel.")
    parser.add_argument("--account", help="Filter by account name (partial match).", default=None)
    parser.add_argument("--folder", help="Filter by folder label (partial match).", default=None)
    parser.add_argument(
        "--output",
        help="Optional output Excel file path. Defaults to result/Accounts_Daily_Update_<date>.xlsx.",
        default=None,
    )
    parser.add_argument(
        "--previous-day",
        action="store_true",
        help="Pick the latest file strictly before today (useful to report yesterday if today's files are still incoming).",
    )
    parser.add_argument(
        "--today-only",
        action="store_true",
        help="Only consider files whose date is today.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Alias for --today-only.",
    )
    parser.add_argument(
        "--skip",
        action="append",
        help="Account names to skip (can be given multiple times). Example: --skip Wizard",
        default=None,
    )
    parser.add_argument(
        "--date",
        help="Single calendar date to report for (format: YYYY-MM-DD).",
        default=None,
    )
    parser.add_argument(
        "--start-date",
        help="Start date (inclusive) for a date range (format: YYYY-MM-DD).",
        default=None,
    )
    parser.add_argument(
        "--end-date",
        help="End date (inclusive) for a date range (format: YYYY-MM-DD).",
        default=None,
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()
    if getattr(args, "latest", False):
        args.today_only = True
    run_started = datetime.datetime.now()

    # Parse optional date/date-range arguments (ISO yyyy-mm-dd)
    dates: list[datetime.date] | None = None
    if args.date or args.start_date or args.end_date:
        def _parse(d: str | None) -> datetime.date | None:
            if not d:
                return None
            try:
                return datetime.datetime.strptime(d, "%Y-%m-%d").date()
            except Exception as exc:  # noqa: BLE001
                print(f"Invalid date format: {d}. Expected YYYY-MM-DD.")
                raise

        if args.date:
            single = _parse(args.date)
            if single is None:
                print("Invalid --date value")
                return
            dates = [single]
        else:
            start = _parse(args.start_date) or _parse(args.end_date)
            end = _parse(args.end_date) or _parse(args.start_date)
            if not start or not end:
                print("Both --start-date and --end-date must be provided, or use --date for a single date.")
                return
            if start > end:
                print("Start date must be on or before end date.")
                return
            dates = []
            cur = start
            while cur <= end:
                dates.append(cur)
                cur = cur + datetime.timedelta(days=1)

    # Default behavior: today-only unless explicitly overridden
    if not args.today_only and not args.previous_day:
        args.today_only = True

    for directory in (RESULT_DIR, ERROR_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    log_file = LOG_DIR / f"run_{run_started.strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    logger = logging.getLogger(__name__)
    # If dates were provided, run once per date and write per-date outputs.
    if dates:
        logger.info(
            "Run started | account filter=%s | folder filter=%s | previous_day=%s | dates=%s | skip=%s",
            args.account,
            args.folder,
            args.previous_day,
            f"{dates[0]} to {dates[-1]}" if len(dates) > 1 else f"{dates[0]}",
            args.skip,
        )

        for dt in dates:
            logger.info("Collecting for calendar date: %s", dt)
            rows = collect_latest_file_details(
                account_filter=args.account,
                folder_filter=args.folder,
                previous_day=bool(args.previous_day),
                today_only=not bool(args.previous_day),
                skip_accounts=args.skip or [],
                on_date=dt,
            )

            if not rows:
                logger.warning("No data returned for date %s. Skipping.", dt)
                continue

            report_date = dt.strftime("%m-%d-%Y")
            if args.output:
                outp = Path(args.output)
                if len(dates) > 1:
                    result_path = outp.with_name(outp.stem + "_" + report_date + outp.suffix)
                else:
                    result_path = outp
            else:
                result_path = RESULT_DIR / f"Accounts_Daily_Update_{report_date}.xlsx"

            output_path = write_results_to_excel(rows, output_path=result_path)
            logger.info("Report for %s saved to %s", report_date, output_path)

            error_keywords = ("error", "connection error")
            error_rows = [
                row
                for row in rows
                if isinstance(row.get("Latest File Date"), str)
                and (
                    row["Latest File Date"].lower().startswith(error_keywords)
                    or row["Latest File Date"] == "Folder not configured"
                )
            ]

            if error_rows:
                error_path = write_results_to_excel(
                    error_rows,
                    output_path=ERROR_DIR / f"Accounts_Daily_Update_errors_{report_date}.xlsx",
                )
                logger.warning("Errors detected for %s; details saved to %s", report_date, error_path)
            else:
                logger.info("No errors detected for %s.", report_date)

        print(f"Date range processing completed. Check {RESULT_DIR} and {ERROR_DIR} for outputs and logs: {log_file}")
        return

    logger.info(
        "Run started | account filter=%s | folder filter=%s | previous_day=%s | today_only=%s | skip=%s",
        args.account,
        args.folder,
        args.previous_day,
        args.today_only,
        args.skip,
    )

    rows = collect_latest_file_details(
        account_filter=args.account,
        folder_filter=args.folder,
        previous_day=bool(args.previous_day),
        today_only=bool(args.today_only),
        skip_accounts=args.skip or [],
        on_date=None,
    )
    if not rows:
        print("No data found. Please verify your credentials file.")
        logger.warning("No data returned from collection.")
        return

    report_date = run_started.strftime("%m-%d-%Y")
    if args.output:
        result_path = Path(args.output)
    else:
        result_path = RESULT_DIR / f"Accounts_Daily_Update_{report_date}.xlsx"

    output_path = write_results_to_excel(rows, output_path=result_path)
    logger.info("Main report saved to %s", output_path)

    error_keywords = ("error", "connection error")
    error_rows = [
        row
        for row in rows
        if isinstance(row.get("Latest File Date"), str)
        and (
            row["Latest File Date"].lower().startswith(error_keywords)
            or row["Latest File Date"] == "Folder not configured"
        )
    ]

    if error_rows:
        error_path = write_results_to_excel(
            error_rows,
            output_path=ERROR_DIR / f"Accounts_Daily_Update_errors_{report_date}.xlsx",
        )
        logger.warning("Errors detected; details saved to %s", error_path)
        error_message = f"Errors saved to {error_path}"
    else:
        logger.info("No errors detected during this run.")
        error_message = "No errors detected."

    print(f"Data saved to {output_path}\n{error_message}\nLogs: {log_file}")


if __name__ == "__main__":
    main()
