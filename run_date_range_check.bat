@echo off
REM One-time batch file to check FTP files from Oct 16 to Oct 22, 2025
echo ========================================
echo FTP Files Date Range Check
echo Oct 16, 2025 to Oct 22, 2025
echo ========================================
echo.

python check_date_range_files.py

echo.
echo ========================================
echo Check complete!
echo Results saved in the 'result' folder
echo ========================================
pause
