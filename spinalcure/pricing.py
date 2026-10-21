"""Full price / discounted price, shared by courses and events."""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


def original_price_field():
    return models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name=_('Full price (₹)'),
        help_text=_('Optional. Shown struck out next to the fee, e.g. full price 75,000 and fee 45,000.'))


class DiscountMixin:
    """For models with `fees` and `original_fees`."""

    @property
    def has_discount(self):
        return bool(self.original_fees and self.fees is not None and self.original_fees > self.fees)

    @property
    def discount_percent(self):
        return round((1 - self.fees / self.original_fees) * 100) if self.has_discount else 0

    def clean_discount(self):
        if self.original_fees is not None and self.original_fees <= (self.fees or 0):
            raise ValidationError({'original_fees': _('The full price must be higher than the fee people pay.')})
