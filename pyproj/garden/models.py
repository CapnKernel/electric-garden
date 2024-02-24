from django.db import models

class Plant(models.Model):
    name = models.CharField(max_length=100) # Example: 'Dwarf bean, Gourmet Delight'
    code = models.CharField(max_length=10) # Example: 'BR' or '豆DGD'
    barcode = models.CharField(max_length=10) # Example: 'P=018'
    spacing = models.CharField(max_length=10, null=True, blank=True) # Example: '15' for sowing 15cm apart
    germination = models.CharField(max_length=10, null=True, blank=True) # Example: '7' for germination in 7 days, or '10-14' for 10-14 days
    harvest = models.CharField(max_length=10, null=True, blank=True) # Example: '60' for harvest in 60 days, or '60-70' for 60-70 days

    class Meta:
        # verbose_name_plural = "Plants"
        pass

    def __str__(self):
        return self.name

class Packet(models.Model):
    barcode = models.CharField(max_length=10) # Example: 'P=114'
    plant = models.ForeignKey(Plant, on_delete=models.PROTECT)
    deleted = models.BooleanField(default=False)
    location = models.CharField(max_length=10, null=True, blank=True) # Example: 'T=1062'
    brand = models.CharField(max_length=100, null=True, blank=True) # Example: "Mr Fothergill's"
    expiry = models.DateField(null=True, blank=True) # Example: '1-Aug-2022'
    full_name = models.CharField(max_length=100, null=True, blank=True) # Example: 'Marketmore'
    notes = models.TextField(null=True, blank=True) # Example: 'Sow in full sun'

    class Meta:
        # verbose_name_plural = "Packets"
        pass

    def __str__(self):
        return f'{self.barcode}: {self.plant.name}'

class Planting(models.Model):
    barcode = models.CharField(max_length=10) # Example: 'P=1114'
    packet = models.ForeignKey(Packet, on_delete=models.PROTECT)
    deleted = models.BooleanField(default=False)
    planted = models.DateField()
    location = models.CharField(max_length=50, null=True, blank=True) # Example: 'Front garden parsley box'
    notes = models.TextField(null=True, blank=True) # Example: "From Kath's seedling box"

    class Meta:
        # verbose_name_plural = "Plantings"
        pass

    def __str__(self):
        return f'{self.barcode}: {self.packet.plant.name} on {self.planted}'

