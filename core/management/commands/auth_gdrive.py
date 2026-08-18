"""
Management Command: auth_gdrive
================================
Interactive 1-time authorization helper for Google Drive OAuth 2.0.
Used when Organization Policies disable service account key creation.

Usage:
  python manage.py auth_gdrive --credentials /path/to/client_secret.json

Outputs:
  Saved authorized token to /home/server_admin/ODtech/google_drive_credentials.json
"""

import os
import sys
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Authenticate Google Drive using OAuth 2.0 Client ID (when Service Account Keys are disabled)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--credentials',
            default='client_secret.json',
            help='Path to downloaded OAuth Client ID JSON file from Google Cloud Console.',
        )
        parser.add_argument(
            '--out',
            default='/home/server_admin/ODtech/google_drive_credentials.json',
            help='Output path for authorized user token JSON file.',
        )

    def handle(self, *args, **options):
        client_secret_path = options['credentials']
        out_path = options['out']

        if not os.path.exists(client_secret_path):
            self.stderr.write(
                f"ERROR: Credentials file '{client_secret_path}' not found.\n"
                f"Download OAuth client ID JSON from Google Cloud Console (APIs & Services -> Credentials)."
            )
            return

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow

            SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            
            # Use redirect URI for local or oob
            self.stdout.write(self.style.NOTICE(
                "\n=======================================================\n"
                "           Google Drive 1-Time Authorization           \n"
                "=======================================================\n"
            ))

            try:
                # Try running local server flow on port 8085
                creds = flow.run_local_server(
                    host='0.0.0.0',
                    port=8085,
                    open_browser=False,
                    authorization_prompt_message=(
                        "1. Open the following URL in your web browser:\n\n{url}\n\n"
                        "2. Log in and grant permissions.\n"
                    ),
                    success_message="Authorization successful! You may close this tab."
                )
            except Exception as srv_err:
                self.stdout.write(f"Local server listener notice ({srv_err}). Using console flow...\n")
                creds = flow.run_console()

            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(creds.to_json())

            self.stdout.write(self.style.SUCCESS(
                f"\nSUCCESS: Authorized Google Drive token saved to:\n  {out_path}\n"
                f"You can now run: python manage.py backup_db --triggered-by=manual\n"
            ))

        except ImportError:
            self.stderr.write(
                "ERROR: Required packages not installed. Run: pip install google-auth-oauthlib"
            )
        except Exception as e:
            self.stderr.write(f"ERROR during authorization: {e}")
