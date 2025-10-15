from __future__ import annotations

import datetime
import stat
import unittest
from types import SimpleNamespace
from unittest import mock

import main


class FakeSFTPAttr(SimpleNamespace):
    def __init__(self, filename: str, modified_at: datetime.datetime):
        super().__init__(
            filename=filename,
            st_mtime=modified_at.timestamp(),
            st_mode=stat.S_IFREG,
        )


class CollectLatestFileDetailsTests(unittest.TestCase):
    @mock.patch("main.load_multiple_configs_from_file")
    @mock.patch("src.sftp_connector.paramiko.SSHClient")
    def test_returns_latest_file(self, mock_ssh_client, mock_load_configs):
        mock_load_configs.return_value = [
            {
                "name": "Wheels FTP",
                "host": "sftp.rategain.com",
                "username": "wheels.ai",
                "password": "secret",
                "port": 22,
                "folders": [
                    {
                        "label": "Dryyve Italy Booking",
                        "path": "/Dryyve/Processed Bookings/Italy",
                    }
                ],
            }
        ]

        sftp_mock = mock.Mock()
        sftp_mock.listdir_attr.return_value = [
            FakeSFTPAttr("old.csv", datetime.datetime(2025, 10, 12, 8, 0, 0)),
            FakeSFTPAttr("new.csv", datetime.datetime(2025, 10, 14, 9, 30, 0)),
        ]

        ssh_client_mock = mock.Mock()
        ssh_client_mock.open_sftp.return_value = sftp_mock
        mock_ssh_client.return_value = ssh_client_mock

        rows = main.collect_latest_file_details(
            account_filter="Wheels FTP",
            folder_filter="Dryyve Italy Booking",
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["Account Name"], "Wheels FTP")
        self.assertEqual(row["Folder"], "Dryyve Italy Booking")
        self.assertEqual(row["Latest File Name"], "new.csv")
        self.assertEqual(
            row["Latest File Date"],
            datetime.datetime(2025, 10, 14, 9, 30, 0).strftime("%m/%d/%Y"),
        )

        mock_ssh_client.assert_called_once_with()
        ssh_client_mock.connect.assert_called_once_with(
            "sftp.rategain.com",
            port=22,
            username="wheels.ai",
            password="secret",
        )
        sftp_mock.listdir_attr.assert_called_once_with("/Dryyve/Processed Bookings/Italy")
        sftp_mock.close.assert_called_once_with()
        ssh_client_mock.close.assert_called_once_with()

    @mock.patch("main.load_multiple_configs_from_file")
    @mock.patch("src.sftp_connector.paramiko.SSHClient")
    def test_handles_empty_folder(self, mock_ssh_client, mock_load_configs):
        mock_load_configs.return_value = [
            {
                "name": "Wheels FTP",
                "host": "sftp.rategain.com",
                "username": "wheels.ai",
                "password": "secret",
                "port": 22,
                "folders": [
                    {
                        "label": "Dryyve Italy Booking",
                        "path": "/Dryyve/Processed Bookings/Italy",
                    }
                ],
            }
        ]

        sftp_mock = mock.Mock()
        sftp_mock.listdir_attr.return_value = []

        ssh_client_mock = mock.Mock()
        ssh_client_mock.open_sftp.return_value = sftp_mock
        mock_ssh_client.return_value = ssh_client_mock

        rows = main.collect_latest_file_details(
            account_filter="Wheels FTP",
            folder_filter="Dryyve Italy Booking",
        )

        self.assertEqual(rows[0]["Latest File Name"], "-")
        self.assertEqual(rows[0]["Latest File Date"], "Manual")
        sftp_mock.close.assert_called_once_with()
        ssh_client_mock.close.assert_called_once_with()

    @mock.patch("main.load_multiple_configs_from_file")
    @mock.patch("src.sftp_connector.paramiko.SSHClient")
    def test_reports_missing_folder(self, mock_ssh_client, mock_load_configs):
        mock_load_configs.return_value = [
            {
                "name": "Wheels FTP",
                "host": "sftp.rategain.com",
                "username": "wheels.ai",
                "password": "secret",
                "port": 22,
                "folders": [
                    {
                        "label": "Dryyve Italy Inventory",
                        "path": "/Dryyve/Processed Inventory/Italy",
                    }
                ],
            }
        ]

        sftp_mock = mock.Mock()
        ssh_client_mock = mock.Mock()
        ssh_client_mock.open_sftp.return_value = sftp_mock
        mock_ssh_client.return_value = ssh_client_mock

        rows = main.collect_latest_file_details(
            account_filter="Wheels FTP",
            folder_filter="Dryyve Italy Booking",
        )

        self.assertEqual(rows[0]["Latest File Date"], "Folder not configured")
        ssh_client_mock.connect.assert_called_once_with(
            "sftp.rategain.com",
            port=22,
            username="wheels.ai",
            password="secret",
        )
        sftp_mock.listdir_attr.assert_not_called()
        sftp_mock.close.assert_called_once_with()
        ssh_client_mock.close.assert_called_once_with()



if __name__ == "__main__":
    unittest.main()


