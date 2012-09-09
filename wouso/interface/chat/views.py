from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils import simplejson
from models import *

from wouso.core.user.models import *
from wouso.core.config.models import BoolSetting
from datetime import datetime, timedelta
import random, array


def create_room(roomName, deletable=False, renameable=False):
    ''' creates a new chatroom and saves it '''
    newRoom = ChatRoom(name=roomName, deletable=deletable, renameable=renameable)
    newRoom.save()
    return newRoom

def get_author(request):

    return request.user.get_profile().get_extension(ChatUser)

def shuffle_text(text):
    if isinstance(text, unicode):
        temp= array.array('u', text)
        converter= temp.tounicode
    else:
        temp= array.array('c', text)
        converter= temp.tostring
    random.shuffle(temp)
    return converter()


def change_text(text):
    text = text.split(" ")
    random.shuffle(text)
    new_text = ""
    for world in text:
        new_text = new_text + world[0] + shuffle_text(world[1:len(world)-1]) + world[len(world)-1] + " "
    return new_text

def add_message(text, sender, toRoom, user_to, messType, comand):
    '''content, author, room, user_to, messType, comand'''

    timeStamp = datetime.now()
    diff = timeStamp - sender.lastMessageTS

    #TODO: Putem renunta la spam:) este inutil.
    #difference_in_seconds = 1;
    #if diff.total_seconds() > 0.5:
    difference_in_seconds = (diff.microseconds + (diff.seconds + diff.days * 24 * 3600) * 10**6) / 10**6
    if sender.has_modifier('block-communication')or not sender.canAccessChat:
        return False
    if difference_in_seconds > 0.5:
        if sender.has_modifier('change-messages'):
            text = change_text(text)
        msg = ChatMessage(content=text, author=sender, destRoom=toRoom, timeStamp=timeStamp,
                            destUser = user_to, messType=messType, comand=comand)
        msg.save()
    else:
        raise ValueError('Spam')


def serve_message(user, room=None, position=None):


    obj = {'user': unicode(user)}
    if room == None:
        query = ChatMessage.objects.filter(timeStamp__gt=user.lastMessageTS, destRoom__participants=user)
        obj['count'] = query.count()
    else:
        number = int(position)
        query = ChatMessage.objects.filter(destRoom=room)
        query = query[len(query)-number-10:] if len(query) > (10 + number) else query

        number_query = 10 if len(query) == 0 else len(query) - number
        obj['count'] = number_query


    if not query:
        return None

    lastTS = datetime.now()
    msgs = []
    for m in query:
        mesaj = {}
        if (m.destUser == user and m.messType == "special") or m.messType == "normal":
            mesaj['room'] = m.destRoom.name
            mesaj['user'] = unicode(m.author.nickname)
            mesaj['text'] = m.content
            mesaj['comand'] = m.comand
            mesaj['mess_type'] = m.messType
            mesaj['dest_user'] = unicode(m.destUser.nickname)
            lastTS = m.timeStamp
            msgs.append(mesaj)
        else:
            continue
    if room == None:
        user.lastMessageTS = lastTS
        user.save()

    obj['msgs'] = msgs

    return obj


@login_required
def index(request):
    user = request.user.get_profile()
    chat = get_author(request)
    if user.has_modifier('block-global-chat-page') or user.has_modifier('block-communication') or not chat.canAccessChat:
        return HttpResponseRedirect(reverse('wouso.interface.views.homepage'))
    if BoolSetting.get('disable-Chat').get_value():
        return HttpResponseRedirect(reverse('wouso.interface.views.homepage'))

    return render_to_response('chat/chat.html',
                            {'chat_user': user,
                            },
                            context_instance=RequestContext(request))


@login_required
def log_request(request):

    Room = roomexist('global')

    all_message = ChatMessage.objects.filter(destRoom=Room).filter(messType='normal')
    all_message = all_message[len(all_message)-50:] if len(all_message) > 50 else all_message

    return render_to_response('chat/global_log.html',
                            {
                            'log':all_message,
                            },
                            context_instance=RequestContext(request))


@login_required
def online_players(request):

    # gather users online in the last ten minutes
    oldest = datetime.now() - timedelta(minutes = 1000)
    online_last10 = Player.objects.filter(last_seen__gte=oldest).order_by('user__username')

    def is_not_blocked(x):
        return not x.has_modifier('block-communication')

    online_last10 = filter(is_not_blocked, online_last10)

    return render_to_response('chat/chat_last.html',
                            {
                            'last': online_last10,
                            },
                            context_instance=RequestContext(request))



@login_required
def private_log(request):

    user = get_author(request)
    position = request.POST['number']

    room = roomexist(request.POST['room'])
    return HttpResponse(simplejson.dumps(serve_message(user, room, position)))


@login_required
def special_message(user, room = None, message = None):

    obj = {'user': unicode(user)}
    obj['count'] = 1

    msgs = []
    mesaj = {}
    mesaj['room'] = room
    mesaj['user'] = user.nickname
    mesaj['text'] = None
    mesaj['mess_type'] = 'special'
    mesaj['comand'] = message
    mesaj['dest_user'] = unicode(user.nickname)
    msgs.append(mesaj)
    print msgs
    obj['msgs'] = msgs
    return obj


@login_required
def sendmessage(request):
    """ Default endpoint (/chat/m/)
    """
    user = get_author(request)
    data = request.REQUEST

    if data['opcode'] == 'message':
        room = roomexist(data['room'])
        if user.user.has_perm('chat.super_chat_user'):
            if data['msg'][0] == '/' and data['room'] == 'global':
                text = data['msg'].split(" ")
                if len(text) > 1:
                    try:
                        sender = Player.objects.get(nickname=text[1])
                        sender = sender.user.get_profile().get_extension(ChatUser)
                    except:
                        return HttpResponse(simplejson.dumps(serve_message(user, None, None)))

                    if text[0] == '/kick':
                        add_message(text[1], user, room, sender, "special", "kick")
                    if text[0] == '/unban':
                        sender.canAccessChat = True
                        sender.save()
                    if text[0] == '/ban':
                        sender.canAccessChat = False
                        sender.save()
                    return HttpResponse(simplejson.dumps(serve_message(user, None, None)))


        try:
            assert room is not None
            # content, author, room, user_to, messType, comand
            add_message(data['msg'], user, room, user, "normal", "normal")
        except (ValueError, AssertionError):
            return HttpResponseBadRequest()
    elif data['opcode'] == 'keepAlive':
        chat_global = roomexist('global')
        if user.has_modifier('block-communication')or not user.canAccessChat:
            return HttpResponse(simplejson.dumps(special_message(user, None, "block-communication")))

            #add_message("", user, chat_global, user, "special", "block-communication")
        elif user.has_modifier('block-global-chat-page') or not user.canAccessChat:
            return HttpResponse(simplejson.dumps(special_message(user, None, "kick")))
            #add_message("", user, chat_global, user, "special", "kick")

        if user not in chat_global.participants.all():
            chat_global.participants.add(user)
    elif data['opcode'] == 'getRoom':
        try:
            user_to = Player.objects.get(id=data['to'])
            user_to = user_to.get_extension(ChatUser)
        except ChatUser.DoesNotExist:
            return HttpResponseBadRequest()
        if user.has_modifier('block-communication'):
            return HttpResponseBadRequest()
        if user_to.has_modifier('block-communication'):
            return HttpResponseBadRequest()
        rooms = ChatRoom.objects.exclude(name='global').filter(participants=user).filter(participants=user_to)
        rooms = [r for r in rooms if r.participants.count() <= 2]
        if len(rooms) > 1:
            return HttpResponseBadRequest()
        if rooms:
            room = rooms[0]
        else:
            name = '%d-%d' % ((user.id, user_to.id) if user.id < user_to.id else (user_to.id, user.id))
            room = create_room(name)
        room.participants.add(user)
        room.participants.add(user_to.id)
        return json_response(room.to_dict())
    return HttpResponse(simplejson.dumps(serve_message(user, None, None)))

def json_response(object):
     return HttpResponse(simplejson.dumps(object))

def roomexist(room_name):
    try:
        return ChatRoom.objects.get(name = room_name)
    except ChatRoom.DoesNotExist:
        return None

