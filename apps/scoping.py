from django.shortcuts import get_object_or_404

from apps.info.models import Info


def public_infos():
    return Info.objects.all()


def public_info(pk):
    return get_object_or_404(public_infos(), pk=pk)
