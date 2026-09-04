"""
runserver_ngrok.py
──────────────────
Management command providing exact instructions and workflow for local draft-mode
testing via ngrok and WhatsApp Manager's "Preview Flow" tool.

Usage:
    python manage.py runserver_ngrok
    python manage.py runserver_ngrok --run
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.conf import settings


class Command(BaseCommand):
    help = "Displays ngrok tunnel setup instructions and starts Django for WhatsApp Flow testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            type=int,
            default=8000,
            help="Port on which Django runs (default: 8000)",
        )
        parser.add_argument(
            "--run",
            action="store_true",
            help="Directly launch 'python manage.py runserver' after printing instructions",
        )

    def handle(self, *args, **options):
        port = options["port"]
        run_server = options["run"]
        testing_mode = getattr(settings, "TESTING_MODE", True)

        self.stdout.write(self.style.SUCCESS("=" * 76))
        self.stdout.write(self.style.SUCCESS("  WHATSAPP FLOW LOCAL DRAFT-MODE TESTING GUIDE (via ngrok)"))
        self.stdout.write(self.style.SUCCESS("=" * 76))
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("STEP 1: Start Django Development Server"))
        self.stdout.write(f"    python manage.py runserver {port}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"STEP 2: In a separate terminal, expose port {port} via ngrok"))
        self.stdout.write(f"    ngrok http {port}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("STEP 3: Copy the ngrok HTTPS forwarding URL"))
        self.stdout.write("    Example: https://abcdef1234.ngrok-free.app")
        self.stdout.write(self.style.NOTICE("    NOTE: The ngrok URL changes on every restart (free tier)."))
        self.stdout.write(self.style.NOTICE("          Update Endpoint URI in WhatsApp Manager each test session."))
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("STEP 4: Configure WhatsApp Flow Endpoint in WhatsApp Manager"))
        self.stdout.write("    1. Go to: Meta Business Suite -> WhatsApp Manager -> Flows")
        self.stdout.write(f"    2. Open your Flow: ID {getattr(settings, 'WHATSAPP_FLOW_ID', '<FLOW_ID>')}")
        self.stdout.write("    3. Navigate to: Flow Settings -> Endpoint")
        self.stdout.write("    4. Set Endpoint URI to:")
        self.stdout.write(self.style.SUCCESS("       <YOUR_NGROK_HTTPS_URL>/webhook/flow-data-exchange/"))
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("STEP 5: Quick Connectivity Health Check"))
        self.stdout.write("    Open in your browser or curl:")
        self.stdout.write("       <YOUR_NGROK_HTTPS_URL>/webhook/flow-data-exchange/health/")
        self.stdout.write("    Expected response: HTTP 200 {\"status\": \"ok\", ...}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("STEP 6: Test the Flow via Preview"))
        self.stdout.write("    Click 'Preview Flow' inside WhatsApp Manager to test:")
        self.stdout.write("    Category -> Product -> Quantity -> Delivery -> Summary -> Confirmation")
        self.stdout.write("")
        self.stdout.write(f"  Current TESTING_MODE: {testing_mode}")
        if testing_mode:
            self.stdout.write(
                self.style.NOTICE(
                    "  [TESTING_MODE=True] Outbound Cloud API trigger calls ('hi') are safely disabled.\n"
                    "  Use WhatsApp Manager 'Preview Flow' to test data exchange."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "  [TESTING_MODE=False] Live outbound Graph API calls enabled (Requires published Flow)."
                )
            )
        self.stdout.write(self.style.SUCCESS("=" * 76))
        self.stdout.write("")

        if run_server:
            self.stdout.write(self.style.SUCCESS(f"Starting Django development server on port {port}...\n"))
            call_command("runserver", f"{port}")
