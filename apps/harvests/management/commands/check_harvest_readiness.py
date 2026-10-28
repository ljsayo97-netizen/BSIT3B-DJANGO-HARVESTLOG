"""Refresh crop readiness and create harvest notifications."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.harvests.services import sync_harvest_readiness


class Command(BaseCommand):
    help = (
        'Re-check every crop against its system-assigned harvest date and '
        'create in-app notifications for crops that are ready or approaching.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            help='Only check crops owned by this username.',
        )
        parser.add_argument(
            '--no-notify',
            action='store_true',
            help='Update crop statuses without creating new notifications.',
        )

    def handle(self, *args, **options):
        user_model = get_user_model()
        users = user_model.objects.filter(is_active=True)

        username = options.get('username')
        if username:
            users = users.filter(username=username)
            if not users.exists():
                self.stderr.write(
                    self.style.ERROR(f'No active user found with username "{username}".')
                )
                return

        notify = not options['no_notify']
        totals = {'ready': 0, 'approaching': 0, 'notifications_created': 0}

        for user in users.iterator():
            summary = sync_harvest_readiness(user, notify=notify)
            totals['ready'] += summary['ready']
            totals['approaching'] += summary['approaching']
            totals['notifications_created'] += summary['notifications_created']

            if username:
                for crop, result in summary['crops']:
                    self.stdout.write(
                        f'{crop.name} ({crop.farm.name}): {result["status"]} '
                        f'- assigned {crop.expected_harvest_date:%Y-%m-%d}'
                    )

        self.stdout.write(
            self.style.SUCCESS(
                'Harvest readiness check complete: '
                f'{totals["ready"]} ready, '
                f'{totals["approaching"]} approaching, '
                f'{totals["notifications_created"]} new notification(s).'
            )
        )
