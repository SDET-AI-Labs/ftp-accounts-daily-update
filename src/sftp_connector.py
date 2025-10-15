import datetime
from stat import S_ISREG, S_ISDIR

import paramiko

class SFTPConnector:
    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.sftp = None

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # Force password-only authentication to avoid interference from local SSH agents/keys
        self.client.connect(
            self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            allow_agent=False,
            look_for_keys=False,
        )
        self.sftp = self.client.open_sftp()

    def list_files_in_folder(self, remote_folder):
        """List files in the specified remote folder."""
        if self.sftp is None:
            raise RuntimeError("SFTP session has not been established. Call connect() first.")

        try:
            return self.sftp.listdir_attr(remote_folder)
        except FileNotFoundError:
            return []
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Error listing files in {remote_folder}: {exc}") from exc

    def _collect_candidate_files(self, remote_folder: str, *, name_filters: list[str] | None = None):
        """Collect candidate regular files in a folder; if none and filters provided,
        attempt to search inside subfolders whose names match any filter.

        This allows configs like:
          base: /Woodford/RAReporting
          filters: ["RevAI_Fleet", "RevAI_RentalAgreements", "Daily_Bookings"]
        where files actually live within those subfolders.
        """
        entries = self.list_files_in_folder(remote_folder)
        files = [e for e in entries if hasattr(e, "st_mode") and S_ISREG(e.st_mode)]
        # Apply filename filters if provided
        lowered = [s.lower() for s in (name_filters or []) if s]
        if lowered and files:
            files = [f for f in files if any(f.filename.lower().startswith(s) for s in lowered)]

        if files:
            return files

        # If no files found at base and filters exist, try matching subdirectories by name
        if lowered:
            dirs = [e for e in entries if hasattr(e, "st_mode") and S_ISDIR(e.st_mode)]
            matched_dirs = [d for d in dirs if any(d.filename.lower().startswith(s) for s in lowered)]
            collected = []
            for d in matched_dirs:
                subpath = f"{remote_folder.rstrip('/')}/{d.filename}"
                try:
                    subentries = self.list_files_in_folder(subpath)
                except Exception:
                    continue
                collected.extend([e for e in subentries if hasattr(e, "st_mode") and S_ISREG(e.st_mode)])
            if collected:
                return collected
        return []

    def get_latest_file_info(self, remote_folder, *, name_filters: list[str] | None = None):
        """Get the latest file's name and modification date-time in the folder.

        name_filters: optional list of substrings; if provided, only files whose
        names contain at least one of these substrings are considered.
        """
        files = self._collect_candidate_files(remote_folder, name_filters=name_filters)

        if not files:
            return None, None
        latest_file = max(files, key=lambda f: f.st_mtime)
        ts = datetime.datetime.fromtimestamp(latest_file.st_mtime)
        latest_dt = ts.strftime('%m/%d/%Y %H:%M:%S')
        return latest_file.filename, latest_dt

    def get_latest_file_info_before_date(self, remote_folder: str, before_date: datetime.date, *, name_filters: list[str] | None = None):
        """Get the latest file strictly before the given calendar date (local time)."""
        files = self._collect_candidate_files(remote_folder, name_filters=name_filters)
        if not files:
            return None, None

        def to_local_date(attr):
            return datetime.datetime.fromtimestamp(attr.st_mtime).date()

        eligible = [f for f in files if to_local_date(f) < before_date]
        if not eligible:
            return None, None

        latest_file = max(eligible, key=lambda f: f.st_mtime)
        ts = datetime.datetime.fromtimestamp(latest_file.st_mtime)
        latest_dt = ts.strftime('%m/%d/%Y %H:%M:%S')
        return latest_file.filename, latest_dt

    def get_latest_file_info_on_date(self, remote_folder: str, on_date: datetime.date, *, name_filters: list[str] | None = None):
        """Get the latest file whose local calendar date equals on_date."""
        files = self._collect_candidate_files(remote_folder, name_filters=name_filters)
        if not files:
            return None, None

        def to_local_date(attr):
            return datetime.datetime.fromtimestamp(attr.st_mtime).date()

        eligible = [f for f in files if to_local_date(f) == on_date]
        if not eligible:
            return None, None

        latest_file = max(eligible, key=lambda f: f.st_mtime)
        ts = datetime.datetime.fromtimestamp(latest_file.st_mtime)
        latest_dt = ts.strftime('%m/%d/%Y %H:%M:%S')
        return latest_file.filename, latest_dt

    def get_latest_files_per_prefix(self, remote_folder: str, prefixes: list[str], *, on_date: datetime.date | None = None):
        """Return a dict of {prefix: (filename, datetime_str)} for each prefix using startswith matching.
        If on_date is provided, restrict to that calendar date; otherwise consider all dates.
        Also searches matching subfolders if base has no files for that prefix.
        """
        result: dict[str, tuple[str | None, str | None]] = {}
        lowered = [p.lower() for p in prefixes if p]
        today = on_date
        for p in lowered:
            files = self._collect_candidate_files(remote_folder, name_filters=[p])
            if not files:
                result[p] = (None, None)
                continue
            if today:
                files = [f for f in files if datetime.datetime.fromtimestamp(f.st_mtime).date() == today]
                if not files:
                    result[p] = (None, None)
                    continue
            latest_file = max(files, key=lambda f: f.st_mtime)
            ts = datetime.datetime.fromtimestamp(latest_file.st_mtime)
            latest_dt = ts.strftime('%m/%d/%Y %H:%M:%S')
            result[p] = (latest_file.filename, latest_dt)
        return result

    def disconnect(self):
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()