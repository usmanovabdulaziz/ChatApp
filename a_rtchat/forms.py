from django.forms import ModelForm
from django import forms
from .models import *


class ChatMessageCreateForm(ModelForm):
    class Meta:
        model = GroupMessage
        fields = ['body']
        widgets = {
            'body': forms.TextInput(attrs={'placeholder': 'Add message ...', 'class': 'p-4 text-black', 'max_length': '400', 'autofocus': True}),
        }