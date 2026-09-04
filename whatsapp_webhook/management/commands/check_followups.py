from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from whatsapp_webhook.models import WhatsAppFollowUp
from whatsapp_webhook.services import send_followup_reminder


class Command(BaseCommand):
    help = "Finds pending WhatsApp follow-ups older than 12 hours without a reply, and dispatches the follow-up reminder template."

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=float,
            default=12.0,
            help='Minimum elapsed hours since the interactive message was sent (default: 12.0).'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List candidate follow-ups without actually sending messages.'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of follow-up messages to send in one run (default: 50).'
        )

    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        limit = options['limit']

        cutoff = timezone.now() - timedelta(hours=hours)

        self.stdout.write(self.style.NOTICE("=" * 65))
        self.stdout.write(self.style.NOTICE(" [WHATSAPP FOLLOW-UP CHECKER]"))
        self.stdout.write(f" -> Current Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.stdout.write(f" -> Cutoff Threshold: {hours} hours (sent before {cutoff.strftime('%Y-%m-%d %H:%M:%S %Z')})")
        if dry_run:
            self.stdout.write(self.style.WARNING(" -> MODE: DRY-RUN (No messages will be sent)"))
        self.stdout.write(self.style.NOTICE("=" * 65))

        pending_qs = WhatsAppFollowUp.objects.filter(
            customer_replied=False,
            followup_template_sent=False,
            interactive_message_sent_at__lte=cutoff
        ).order_by('interactive_message_sent_at')[:limit]

        total_pending = pending_qs.count()

        if total_pending == 0:
            self.stdout.write(self.style.SUCCESS("[OK] No pending follow-ups due for reminder at this time.\n"))
            return

        self.stdout.write(self.style.WARNING(f"Found {total_pending} pending follow-up(s) requiring reminder:\n"))

        sent_count = 0
        error_count = 0

        for idx, fu in enumerate(pending_qs, start=1):
            elapsed_hrs = fu.hours_since_sent
            self.stdout.write(
                f"[{idx}/{total_pending}] ID: {fu.id} | Customer: {fu.customer_name or 'N/A'} | Phone: +{fu.phone_number} | Elapsed: {elapsed_hrs:.1f}h ago"
            )

            if dry_run:
                continue

            result = send_followup_reminder(fu)
            if result.get("success"):
                sent_count += 1
                self.stdout.write(self.style.SUCCESS(f"     -> Reminder template sent successfully to +{fu.phone_number}"))
            else:
                error_count += 1
                err_msg = result.get("error", "Unknown error")
                self.stdout.write(self.style.ERROR(f"     -> Failed to send to +{fu.phone_number}: {err_msg}"))

        self.stdout.write("\n" + "=" * 65)
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry-run complete. {total_pending} candidate(s) found."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Follow-up check complete: {sent_count} sent, {error_count} failed out of {total_pending}."))
        self.stdout.write("=" * 65 + "\n")
