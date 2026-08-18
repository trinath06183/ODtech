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
        parser.add_argument(
            '--port',
            type=int,
            default=0,
            help='Port to listen on for OAuth callback (default: 0 = dynamic free port).',
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
            from google_auth_oauthlib.flow import Flow

            SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']
            
            # Use redirect URI http://localhost:8088/
            redirect_uri = "http://localhost:8088/"
            flow = Flow.from_client_secrets_file(
                client_secret_path,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )

            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )

            self.stdout.write(self.style.NOTICE(
                "\n=======================================================\n"
                "           Google Drive 1-Time Authorization           \n"
                "=======================================================\n"
            ))
            self.stdout.write("1. Open this URL in your web browser:\n")
            self.stdout.write(self.style.WARNING(f"\n{auth_url}\n"))
            self.stdout.write(
                "\n2. Sign in and grant permission.\n"
                "3. After clicking Allow, your browser will redirect to a page like:\n"
                "   http://localhost:8088/?state=...&code=4/0A...\n"
                "   (Even if the page says 'Site can't be reached', that is completely normal!)\n\n"
                "4. Copy the ENTIRE URL from your browser address bar and paste it below:\n"
            )

            callback_url = input("\nPaste Full Redirect URL here: ").strip()

            if not callback_url:
                self.stderr.write("ERROR: No URL provided. Aborted.")
                return

            flow.fetch_token(authorization_response=callback_url)
            creds = flow.credentials

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
