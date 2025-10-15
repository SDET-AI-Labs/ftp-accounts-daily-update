# FTP Accounts Daily Update

This project connects to multiple SFTP accounts, checks the latest file available in the configured folders for each account, and exports the results to an Excel workbook named `Accounts_Daily_Update_<MM-DD-YYYY>.xlsx`.

## Project Structure

```
FTP-Accounts_Daily_Update
├── .venv/                    # Python virtual environment (excluded from version control)
├── errors/                   # Captures Excel snapshots of rows that failed during a run
├── logs/                     # Timestamped execution logs for audit and troubleshooting
├── main.py                   # Entry point – orchestrates the SFTP checks and Excel export
├── requirements.txt          # Python dependencies (paramiko, pandas, openpyxl)
├── result/                   # Successful Excel exports (Accounts_Daily_Update_<date>.xlsx)
└── src/
    ├── __init__.py
    ├── config.py             # Parses SFTP credentials and target folders
    └── sftp_connector.py     # Thin wrapper around Paramiko's SFTP client
```

## Setup

1. **Create and activate a virtual environment** (recommended name: `.venv`):

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. **Install dependencies**:

   ```powershell
   pip install -r requirements.txt
   ```

3. **Maintain the credentials file**: update `src/credentials.txt` with every SFTP account you want to monitor. Each block is separated by a line of dashes (`-----`). Example:

   ```text
   BudgetBC
   Host: sftp.rategain.com
   Username: budgetbc
   Password: "A20nA4Pg9vR7"
   Port: 22
   OpenRA: '/BudgetBC/Processed OpenRA'
   Booking: '/BudgetBC/Processed Booking'
   Inventory: '/BudgetBC/Processed Inventory'
   ---------------------------------------
   ```

   Any key that is not one of `Host`, `Username`, `Password`, or `Port` is treated as a folder label. The value should be the remote folder path where files land on the SFTP server. Add as many key/value pairs as you need per account.

## Running the Daily Update

```powershell
python main.py
```

- The script connects to each configured SFTP account.
- For every folder listed under that account, it fetches the most recent file (by modification timestamp) and captures its name and date.
- Results are written to `result/Accounts_Daily_Update_<MM-DD-YYYY>.xlsx`.
- If any folders fail (connection error, permission issue, missing path, etc.), a companion workbook is produced at `errors/Accounts_Daily_Update_errors_<MM-DD-YYYY>.xlsx` listing only the problematic rows.
- Detailed run logs are saved under `logs/run_<timestamp>.log`.
- If a folder is empty, the Excel file will display `-` for that entry (and the detailed reason appears in the log).

### One-click runner (Windows)

- Double-click `run_report.bat` in the project root. It will:
   - Create the `.venv` if missing
   - Install/upgrade dependencies
   - Run `main.py` with any arguments you pass

Examples:

```powershell
.# all accounts (today-only default)
.\run_report.bat

# skip Wizard
.\run_report.bat --skip Wizard

# only Woodford
.\run_report.bat --account "Woodford South Africa"
```

### Using a custom credentials location

- Set the environment variable `CREDENTIALS_PATH` to the full path of your credentials file before running. The app also searches common locations (src/credentials.txt, ./credentials.txt, current working directory).

### Build a standalone EXE (no Python needed)

- Run `./build_exe.ps1` in PowerShell (it uses PyInstaller). Then copy `dist/ftp-accounts-report/` to the target PC and run `ftp-accounts-report.exe`.
- The EXE bundles `src/credentials.txt`. To use an external credentials file with the EXE, set `CREDENTIALS_PATH`.

## Notes

- The script does not delete, upload, or download files; it only reads metadata (names and timestamps).
- Ensure each account's credentials and folder paths are correct—failed connections or invalid folders are reported in the Excel output.
- Keep the `.venv/` folder out of version control; it is specific to your machine.

## Next Steps

- Add unit tests for parsing and SFTP interactions using mocks.
- Schedule the script (e.g., Windows Task Scheduler) to run automatically every day.
- Extend the Excel export with additional metadata (file sizes, counts, etc.) if required.