# production/migrations/0040_add_model_to_sizequantity.py

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('production', '0039_remove_cut_consumption_p_model_consumption_p_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sizequantity',
            name='model',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='production.model',
                verbose_name='Модель'
            ),
        ),
    ]
