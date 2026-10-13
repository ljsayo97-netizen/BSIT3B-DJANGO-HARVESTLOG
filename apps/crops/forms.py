from decimal import Decimal

from django import forms
from django.db.models import Sum

from .models import Crop, Harvest, Sale


class CropForm(forms.ModelForm):
    class Meta:
        model = Crop
        fields = [
            'name',
            'variety',
            'farm_name',
            'farm_location',
            'farm_size',
            'farm_size_unit',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'variety': forms.TextInput(attrs={'class': 'form-control'}),
            'farm_name': forms.TextInput(attrs={'class': 'form-control'}),
            'farm_location': forms.TextInput(attrs={'class': 'form-control'}),
            'farm_size': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'farm_size_unit': forms.TextInput(attrs={'class': 'form-control'}),
        }


class HarvestForm(forms.ModelForm):
    class Meta:
        model = Harvest
        fields = ['crop', 'harvest_date', 'quantity', 'unit', 'notes']
        widgets = {
            'crop': forms.Select(attrs={'class': 'form-select'}),
            'harvest_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0.001'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['crop'].queryset = Crop.objects.filter(owner=owner)


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['harvest', 'sold_on', 'quantity', 'unit_price', 'buyer']
        widgets = {
            'harvest': forms.Select(attrs={'class': 'form-select'}),
            'sold_on': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0.001'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'buyer': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['harvest'].queryset = Harvest.objects.filter(crop__owner=owner).select_related('crop')
        self.fields['harvest'].label_from_instance = (
            lambda harvest: (
                f'{harvest.crop.name} ({harvest.crop.variety or "no variety"}) — '
                f'{harvest.harvest_date}: {harvest.quantity_remaining} {harvest.unit} available'
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        harvest = cleaned_data.get('harvest')
        quantity = cleaned_data.get('quantity')

        if harvest and quantity:
            already_sold = harvest.sales.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
            if quantity > harvest.quantity - already_sold:
                self.add_error(
                    'quantity',
                    f'Only {harvest.quantity - already_sold} {harvest.unit} remain unsold.',
                )

        return cleaned_data
