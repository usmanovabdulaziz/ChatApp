from django.urls import path
from a_rtchat.views import *

urlpatterns = [
    path('', chat_views, name='home'),
    path('chat/<username>', get_or_create_chatroom, name='start-chat'),
    path('chat/room/<chatroom_name>', chat_views, name='chatroom'),
    path('chat/new_groupchat/', create_groupchat, name='new_groupchat'),
]