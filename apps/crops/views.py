from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CropForm, HarvestForm, SaleForm
from .models import Crop, Harvest, Sale


@login_required(login_url='login')
def crop_list(request):
    crops = Crop.objects.filter(owner=request.user)
    form = CropForm(request.POST or None)
    form.instance.owner = request.user
    if request.method == 'POST' and form.is_valid():
        crop = form.save(commit=False)
        crop.save()
        messages.success(request, f'{crop.name} was added to your crop records.')
        return redirect('crops:crop_list')

    return render(request, 'crops/crop_list.html', {
        'crops': crops,
        'form': form,
    })


@login_required(login_url='login')
def crop_edit(request, pk):
    crop = get_object_or_404(Crop, pk=pk, owner=request.user)
    form = CropForm(request.POST or None, instance=crop)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'{crop.name} was updated.')
        return redirect('crops:crop_list')
    return render(request, 'crops/crop_form.html', {'form': form, 'crop': crop})


@login_required(login_url='login')
@require_POST
def crop_delete(request, pk):
    crop = get_object_or_404(Crop, pk=pk, owner=request.user)
    name = crop.name
    crop.delete()
    messages.success(request, f'{name} and its related harvest and sales records were deleted.')
    return redirect('crops:crop_list')


@login_required(login_url='login')
def harvest_list(request):
    harvests = Harvest.objects.filter(crop__owner=request.user).select_related('crop')
    form = HarvestForm(request.POST or None, owner=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Harvest recorded.')
        return redirect('crops:harvest_list')
    return render(request, 'crops/harvest_list.html', {
        'harvests': Paginator(harvests, 15).get_page(request.GET.get('page')),
        'form': form,
    })


@login_required(login_url='login')
def sale_list(request):
    sales = Sale.objects.filter(harvest__crop__owner=request.user).select_related('harvest__crop')
    form = SaleForm(request.POST or None, owner=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Sale recorded.')
        return redirect('crops:sale_list')
    return render(request, 'crops/sale_list.html', {
        'sales': Paginator(sales, 15).get_page(request.GET.get('page')),
        'form': form,
    })


@login_required(login_url='login')
def yield_report(request):
    harvests = Harvest.objects.filter(crop__owner=request.user).select_related('crop')
    crop_id = request.GET.get('crop', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    if crop_id.isdigit():
        harvests = harvests.filter(crop_id=int(crop_id))
    if start_date:
        harvests = harvests.filter(harvest_date__gte=start_date)
    if end_date:
        harvests = harvests.filter(harvest_date__lte=end_date)

    report = (
        harvests.values('harvest_date', 'crop__name', 'crop__variety', 'unit')
        .annotate(quantity=Sum('quantity'), harvest_count=Count('id'))
        .order_by('-harvest_date', 'crop__name', 'unit')
    )

    return render(request, 'crops/yield_report.html', {
        'report': report,
        'crops': Crop.objects.filter(owner=request.user),
        'selected_crop': crop_id,
        'start_date': start_date,
        'end_date': end_date,
    })
