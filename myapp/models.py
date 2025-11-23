from django.db import models
# Create your models here.  

class MonthlyWeather(models.Model):
    lat = models.FloatField()
    lon = models.FloatField()
    date = models.DateField()
    avg_temp = models.FloatField()

    class Meta:
        unique_together = ('lat', 'lon', 'date')  # 1 row per city per date

    def __str__(self):
        return f"{self.date} - ({self.lat}, {self.lon}): {self.avg_temp}°C"
    

from django.db import models

class SmartSuggestion(models.Model):
    city = models.CharField(max_length=100)
    date = models.DateField()

    clothing = models.TextField()
    activities = models.TextField()
    health = models.TextField()
    travel = models.TextField()

    class Meta:
        unique_together = ('city', 'date')

    def __str__(self):
        return f"{self.city} - {self.date}"
