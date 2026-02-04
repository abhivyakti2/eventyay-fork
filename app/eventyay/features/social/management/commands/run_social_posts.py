from django.core.management.base import BaseCommand

from eventyay.features.social.tasks import run_due_posts


class Command(BaseCommand):
    help = "Run due scheduled social posts (for cron use)"

    def handle(self, *args, **options):
        run_due_posts()
        self.stdout.write("done")
