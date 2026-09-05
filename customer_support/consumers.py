import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import SupportTicket, TicketReply

User = get_user_model()


def is_support_staff_user(user):
    """Returns True if the user has staff or admin capabilities."""
    if not user or not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or getattr(user, 'is_staff', False)
        or getattr(user, 'role', '') in ['support_staff', 'admin', 'employee']
    )


class TicketChatConsumer(AsyncWebsocketConsumer):
 
    async def connect(self):
        self.ticket_id = self.scope['url_route']['kwargs']['ticket_id']
        self.room_group_name = f"ticket_{self.ticket_id}"
        self.user = self.scope.get('user')

        # Authentication check
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Permission check
        is_allowed = await self.check_ticket_access(self.user, self.ticket_id)
        if not is_allowed:
            await self.close(code=4003)
            return

        # Join ticket room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Notify other party that user is active
        role_label = "Support Agent" if is_support_staff_user(self.user) else "Customer"
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_presence',
                'user_id': self.user.id,
                'username': self.user.username,
                'role_label': role_label,
                'status': 'online',
                'sender_channel_name': self.channel_name,
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            # Notify exit
            if self.user and self.user.is_authenticated:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_presence',
                        'user_id': self.user.id,
                        'username': self.user.username,
                        'status': 'offline',
                        'sender_channel_name': self.channel_name,
                    }
                )

            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = data.get('action')

        if action == 'chat_message':
            message_text = data.get('message', '').strip()
            if not message_text:
                return

            is_staff = is_support_staff_user(self.user)
            reply_data = await self.save_ticket_reply(self.ticket_id, self.user, message_text, is_staff)

            if reply_data:
                # Broadcast message to ticket room
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'ticket_message',
                        'reply': reply_data,
                    }
                )

                # Also broadcast to staff console
                await self.channel_layer.group_send(
                    'support_console',
                    {
                        'type': 'console_notification',
                        'event': 'new_reply',
                        'ticket_id': self.ticket_id,
                        'sender': self.user.username,
                        'is_staff': is_staff,
                        'message_preview': message_text[:80] + ('...' if len(message_text) > 80 else ''),
                    }
                )

        elif action == 'typing':
            is_typing = bool(data.get('is_typing', False))
            is_staff = is_support_staff_user(self.user)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'ticket_typing',
                    'user_id': self.user.id,
                    'username': self.user.get_full_name() or self.user.username,
                    'is_staff': is_staff,
                    'is_typing': is_typing,
                    'sender_channel_name': self.channel_name,
                }
            )

        elif action == 'status_update':
            is_staff = is_support_staff_user(self.user)
            if not is_staff:
                return  # only staff can update status directly via websocket

            new_status = data.get('status')
            status_info = await self.update_ticket_status(self.ticket_id, new_status)
            if status_info:
                # Broadcast status change to ticket room
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'ticket_status_changed',
                        'status': status_info['status'],
                        'status_display': status_info['status_display'],
                        'resolved_at': status_info.get('resolved_at'),
                    }
                )

                # Broadcast to console overview
                await self.channel_layer.group_send(
                    'support_console',
                    {
                        'type': 'console_notification',
                        'event': 'status_change',
                        'ticket_id': self.ticket_id,
                        'new_status': status_info['status'],
                        'new_status_display': status_info['status_display'],
                    }
                )

    # -------------------------------------------------------------
    # Group message handlers
    # -------------------------------------------------------------
    async def ticket_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'reply': event['reply'],
        }))

    async def ticket_typing(self, event):
        # Don't echo typing indicators back to the sender
        if event.get('sender_channel_name') == self.channel_name:
            return

        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_staff': event['is_staff'],
            'is_typing': event['is_typing'],
        }))

    async def ticket_status_changed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': event['status'],
            'status_display': event['status_display'],
            'resolved_at': event.get('resolved_at'),
        }))

    async def user_presence(self, event):
        if event.get('sender_channel_name') == self.channel_name:
            return

        await self.send(text_data=json.dumps({
            'type': 'presence',
            'user_id': event['user_id'],
            'username': event['username'],
            'role_label': event.get('role_label', ''),
            'status': event['status'],
        }))

    # -------------------------------------------------------------
    # Database helper methods
    # -------------------------------------------------------------
    @database_sync_to_async
    def check_ticket_access(self, user, ticket_id):
        try:
            ticket = SupportTicket.objects.get(pk=ticket_id)
            if is_support_staff_user(user):
                return True
            return ticket.user_id == user.id
        except SupportTicket.DoesNotExist:
            return False

    @database_sync_to_async
    def save_ticket_reply(self, ticket_id, user, message, is_staff):
        try:
            ticket = SupportTicket.objects.get(pk=ticket_id)
            reply = TicketReply.objects.create(
                ticket=ticket,
                sender=user,
                message=message,
                is_staff_reply=is_staff
            )

            # Auto-reopen ticket if customer replies to a resolved/closed ticket
            if not is_staff and ticket.status in ['resolved', 'closed']:
                ticket.status = 'in_progress'
                ticket.resolved_at = None
                ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])
            else:
                ticket.updated_at = timezone.now()
                ticket.save(update_fields=['updated_at'])

            created_time_str = reply.created_at.strftime("%b %d, %I:%M %p")

            return {
                'id': reply.id,
                'message': reply.message,
                'is_staff_reply': reply.is_staff_reply,
                'sender_id': user.id,
                'sender_username': user.username,
                'sender_display': user.get_full_name() or user.username,
                'created_at_iso': reply.created_at.isoformat(),
                'created_at_formatted': created_time_str,
                'ticket_status': ticket.status,
                'ticket_status_display': ticket.get_status_display(),
                'attachment_url': None,
                'attachment_name': None,
                'is_image': False,
                'is_pdf': False,
                'file_size': None,
                'file_icon': None,
            }
        except Exception:
            return None

    @database_sync_to_async
    def update_ticket_status(self, ticket_id, new_status):
        try:
            ticket = SupportTicket.objects.get(pk=ticket_id)
            if new_status in dict(SupportTicket.Status.choices):
                ticket.status = new_status
                if new_status in ['resolved', 'closed']:
                    if not ticket.resolved_at:
                        ticket.resolved_at = timezone.now()
                else:
                    ticket.resolved_at = None
                ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])
                return {
                    'status': ticket.status,
                    'status_display': ticket.get_status_display(),
                    'resolved_at': ticket.resolved_at.isoformat() if ticket.resolved_at else None,
                }
        except Exception:
            pass
        return None


class SupportConsoleConsumer(AsyncWebsocketConsumer):
    """
    Real-time consumer for Support Staff Console.
    Broadcasts new incoming tickets, customer replies, and live metric updates.
    """

    async def connect(self):
        self.user = self.scope.get('user')

        # Only staff or admins can connect to console WebSocket
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        is_staff = is_support_staff_user(self.user)
        if not is_staff:
            await self.close(code=4003)
            return

        self.room_group_name = 'support_console'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        # Console consumer primarily receives server-pushed updates
        pass

    async def console_notification(self, event):
        """Sends toast notification / metric update to connected support staff"""
        await self.send(text_data=json.dumps(event))

    async def ticket_created(self, event):
        """Pushes new ticket alert to support staff"""
        await self.send(text_data=json.dumps({
            'type': 'ticket_created',
            'ticket': event.get('ticket', {}),
        }))
