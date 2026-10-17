from rest_framework import serializers
from spinalcure.utils import B64UUIDField
from .models import Payment

class PaymentSerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('receipt_number', 'payment_status')
