def chat_users(request):
    if not request.user.is_authenticated:
        return {
            "private_chat_users": [],
            "group_chats": [],
        }

    private_groups = request.user.chat_groups.filter(is_private=True)
    private_chat_users = set()
    for group in private_groups:
        for member in group.members.all():
            if member != request.user:
                private_chat_users.add(member)

    group_chats = request.user.chat_groups.filter(is_private=False)

    return {
        "private_chat_users": list(private_chat_users),
        "group_chats": group_chats,
    }