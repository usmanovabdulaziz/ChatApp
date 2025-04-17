import re
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.http import HttpResponse
from django.contrib import messages
from django.http import Http404
from .models import *
from .forms import *

def slugify(text):
    """
    Convert text into a slug format suitable for WebSocket group names.
    - Removes special characters, keeps only letters, numbers, spaces, and hyphens.
    - Replaces spaces with hyphens.
    - Converts to lowercase for WebSocket compatibility.
    Example: "EXADEL Group!" -> "exadel-group"
    """
    text = re.sub(r'[^a-zA-Z0-9\s-]', '', text)  # Keep only letters, numbers, spaces, and hyphens
    text = text.replace(' ', '-')  # Replace spaces with hyphens
    text = re.sub(r'-+', '-', text)  # Replace multiple hyphens with a single hyphen
    return text.lower()  # Convert to lowercase for WebSocket compatibility

@login_required
def chat_views(request, chatroom_name='public-chat'):
    """
    View for rendering the chatroom page and handling message submission.
    - Fetches the chat group by chatroom_name.
    - Displays the last 30 messages.
    - Handles private chats by checking membership and identifying the other user.
    - For group chats, verifies email if the user is not a member.
    - Processes new messages via HTMX POST requests.
    """
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    chat_messages = chat_group.chat_messages.all()[:30]  # Get the last 30 messages
    form = ChatmessageCreateForm()

    other_user = None
    if chat_group.is_private:
        # Check if the current user is a member of the private chat
        if request.user not in chat_group.members.all():
            raise Http404()  # Raise 404 if the user is not a member
        # Identify the other user in the private chat
        for member in chat_group.members.all():
            if member != request.user:
                other_user = member
                break
    if chat_group.groupchat_name:
        # For group chats, check if the user is a member
        if request.user not in chat_group.members.all():
            # Add the user to the group if their email is verified
            if request.user.emailaddress_set.filter(verified=True).exists():
                chat_group.members.add(request.user)
            else:
                messages.warning(request, 'You need to verify your email to join the chat!')
                return redirect('profile-settings')

    if request.htmx:
        # Handle new message submission via HTMX
        form = ChatmessageCreateForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.author = request.user
            message.group = chat_group
            message.save()
            context = {
                'message': message,
                'user': request.user,
            }
            return render(request, 'a_rtchat/partials/chat_messgae_p.html', context)

    context = {
        'chat_messages': chat_messages,
        'form': form,
        'other_user': other_user,
        'chatroom_name': chatroom_name,
        'chat_group': chat_group,
    }

    return render(request, 'a_rtchat/chat.html', context)

@login_required
def get_or_create_chatroom(request, username):
    """
    View for starting or accessing a private chat with another user.
    - Redirects to home if the user tries to chat with themselves.
    - Creates a new private chat if one doesn't exist between the users.
    - Redirects to the chatroom page.
    """
    if request.user.username == username:
        return redirect('home')  # Prevent users from chatting with themselves

    other_user = User.objects.get(username=username)
    my_chatrooms = request.user.chat_groups.filter(is_private=True)

    if my_chatrooms.exists():
        # Check if a private chat already exists with the other user
        for chatroom in my_chatrooms:
            if other_user in chatroom.members.all():
                chatroom = chatroom
                break
            else:
                # Create a new private chat if none exists
                chatroom = ChatGroup.objects.create(is_private=True)
                chatroom.members.add(other_user, request.user)
    else:
        # Create a new private chat if the user has no private chats
        chatroom = ChatGroup.objects.create(is_private=True)
        chatroom.members.add(other_user, request.user)

    return redirect('chatroom', chatroom.group_name)

@login_required
def create_groupchat(request):
    """
    View for creating a new group chat.
    - Validates the group name and prevents duplicate names (case-sensitive).
    - Generates a WebSocket-compatible group_name using slugify.
    - Adds the creator as a member and redirects to the chatroom.
    """
    form = NewGroupForm()

    if request.method == 'POST':
        form = NewGroupForm(request.POST)
        if form.is_valid():
            groupchat_name = form.cleaned_data['groupchat_name']
            # Check if a group with the same name already exists (case-sensitive)
            if ChatGroup.objects.filter(groupchat_name__exact=groupchat_name).exists():
                messages.error(request, f"A group named '{groupchat_name}' already exists. Please choose a different name.")
                return render(request, 'a_rtchat/create_groupchat.html', {'form': form})

            new_groupchat = form.save(commit=False)
            new_groupchat.admin = request.user
            new_groupchat.is_private = False  # Set as a group chat (not private)
            # Save groupchat_name as entered by the user
            new_groupchat.groupchat_name = groupchat_name  # Preserve case as entered
            # Generate group_name for WebSocket
            new_groupchat.group_name = slugify(groupchat_name)  # Example: "EXADEL" -> "exadel"
            # Ensure group_name uniqueness by appending a counter if needed
            base_group_name = new_groupchat.group_name
            counter = 1
            while ChatGroup.objects.filter(group_name=new_groupchat.group_name).exists():
                new_groupchat.group_name = f"{base_group_name}-{counter}"  # Example: "exadel" -> "exadel-1"
                counter += 1
            new_groupchat.save()
            new_groupchat.members.add(request.user)
            messages.success(request, f"Group '{groupchat_name}' has been successfully created!")
            return redirect('chatroom', new_groupchat.group_name)

    context = {
        'form': form
    }
    return render(request, 'a_rtchat/create_groupchat.html', context)


@login_required
def chatroom_edit_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin:
        raise Http404()

    form = ChatRoomEditForm(instance=chat_group)

    if request.method == 'POST':
        form = ChatRoomEditForm(request.POST, instance=chat_group)
        if form.is_valid():
            form.save()

            remove_members = request.POST.getlist('remove_members')
            for member_id in remove_members:
                member = User.objects.get(id=member_id)
                chat_group.members.remove(member)

            return redirect('chatroom', chatroom_name)

    context = {
        'form': form,
        'chat_group': chat_group
    }
    return render(request, 'a_rtchat/chatroom_edit.html', context)


@login_required
def chatroom_delete_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin:
        raise Http404()

    if request.method == "POST":
        chat_group.delete()
        messages.success(request, 'Chatroom deleted')
        return redirect('home')

    return render(request, 'a_rtchat/chatroom_delete.html', {'chat_group': chat_group})


@login_required
def chatroom_leave_view(request, chatroom_name):
    """
    View for handling the action of leaving a chatroom.
    - GET: Renders a modal to confirm leaving the chat.
    - POST: Removes the user from the chat and redirects to the home page.
    """
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    # Check if the user is a member of the chat
    if request.user not in chat_group.members.all():
        raise Http404()  # Raise 404 if the user is not a member

    # Prevent the admin from leaving the chat via this view
    if request.user == chat_group.admin:
        messages.error(request, "Admins cannot leave the chat. Please delete the chat instead.")
        if request.htmx:
            # For HTMX requests, render an error message
            return render(request, 'a_rtchat/partials/error_message.html',
                          {'message': "Admins cannot leave the chat. Please delete the chat instead."})
        return redirect('chatroom', chatroom_name)

    if request.method == "POST":
        # Remove the user from the chat group
        chat_group.members.remove(request.user)
        messages.success(request, 'You left the Chat')
        return redirect('home')

    # On GET, render the modal for confirmation
    context = {
        'chat_group': chat_group,
    }
    return render(request, 'a_rtchat/partials/modal_chat_leave.html', context)