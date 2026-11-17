"""Hectare monitoring page view."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services import build_hectare_monitoring_context


@login_required(login_url='login')
def hectare_monitoring(request):
    """Render live land usage, capacity, and crop allocation metrics."""
    context = build_hectare_monitoring_context(request.user)
    return render(request, 'hectares/monitoring.html', context)
