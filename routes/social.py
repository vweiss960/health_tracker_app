import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import (db, User, Friendship, Challenge, ChallengeParticipant,
                    SharedItem, TrainingPlan, SavedPlaylist, TrainingEntry,
                    PushSubscription, SystemConfig)
from datetime import datetime, date, timezone
from sqlalchemy import or_, and_

social_bp = Blueprint('social', __name__)


# ── Web Push helpers ──────────────────────────────────────────────────────────

def _get_vapid_keys():
    """Return (private_key, public_key) VAPID strings, generating once if needed."""
    priv = SystemConfig.get('vapid_private_key')
    pub = SystemConfig.get('vapid_public_key')
    if not priv or not pub:
        try:
            import base64
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.serialization import (
                Encoding, PublicFormat, PrivateFormat, NoEncryption
            )
            # Generate an EC P-256 key pair (required for VAPID)
            private_key = ec.generate_private_key(ec.SECP256R1())
            priv = private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()).decode()
            pub_bytes = private_key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
            pub = base64.urlsafe_b64encode(pub_bytes).decode().rstrip('=')
            SystemConfig.set('vapid_private_key', priv)
            SystemConfig.set('vapid_public_key', pub)
        except Exception as e:
            current_app.logger.error(f'VAPID key generation failed: {e}')
            return None, None
    return priv, pub


def _send_push(user_id, title, body, icon='/static/icons/icon-192.png'):
    """Send a Web Push notification to all subscriptions for a user."""
    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs:
        return
    priv, pub = _get_vapid_keys()
    if not priv:
        return
    try:
        from pywebpush import webpush, WebPushException
        payload = json.dumps({'title': title, 'body': body, 'icon': icon})
        dead = []
        for sub in subs:
            try:
                webpush(
                    subscription_info={'endpoint': sub.endpoint, 'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                    data=payload,
                    vapid_private_key=priv,
                    vapid_claims={'sub': 'mailto:admin@gritboard.app'},
                )
            except WebPushException as e:
                if e.response and e.response.status_code in (404, 410):
                    dead.append(sub)
            except Exception:
                pass
        for sub in dead:
            db.session.delete(sub)
        if dead:
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f'Push send failed: {e}')


# ── helpers ──────────────────────────────────────────────────────────────────

def _friend_ids(user_id):
    """Return set of user_ids who are accepted friends of user_id."""
    rows = Friendship.query.filter(
        or_(
            and_(Friendship.sender_id == user_id, Friendship.status == 'accepted'),
            and_(Friendship.recipient_id == user_id, Friendship.status == 'accepted')
        )
    ).all()
    ids = set()
    for r in rows:
        ids.add(r.recipient_id if r.sender_id == user_id else r.sender_id)
    return ids


def _friendship_between(uid_a, uid_b):
    """Return the Friendship row (either direction) between two users, or None."""
    return Friendship.query.filter(
        or_(
            and_(Friendship.sender_id == uid_a, Friendship.recipient_id == uid_b),
            and_(Friendship.sender_id == uid_b, Friendship.recipient_id == uid_a)
        )
    ).first()


# ── main social page ──────────────────────────────────────────────────────────

@social_bp.route('/')
@login_required
def index():
    fids = _friend_ids(current_user.id)
    friends = User.query.filter(User.id.in_(fids)).all() if fids else []

    pending_received = Friendship.query.filter_by(
        recipient_id=current_user.id, status='pending'
    ).all()

    my_challenges = ChallengeParticipant.query.filter_by(
        user_id=current_user.id
    ).join(Challenge).all()

    open_challenges = Challenge.query.filter(
        Challenge.end_date >= date.today(),
        Challenge.is_public == True,
        ~Challenge.participants.any(ChallengeParticipant.user_id == current_user.id)
    ).order_by(Challenge.start_date).limit(10).all()

    friend_challenges = Challenge.query.filter(
        Challenge.end_date >= date.today(),
        Challenge.creator_id.in_(fids),
        Challenge.is_public == False,
        ~Challenge.participants.any(ChallengeParticipant.user_id == current_user.id)
    ).order_by(Challenge.start_date).limit(10).all() if fids else []

    inbox = SharedItem.query.filter_by(
        recipient_id=current_user.id
    ).order_by(SharedItem.created_at.desc()).limit(30).all()

    unread_count = SharedItem.query.filter_by(
        recipient_id=current_user.id, seen=False
    ).count()

    return render_template(
        'social.html',
        friends=friends,
        pending_received=pending_received,
        my_challenges=my_challenges,
        open_challenges=open_challenges,
        friend_challenges=friend_challenges,
        inbox=inbox,
        unread_count=unread_count,
        today=date.today(),
    )


# ── friend search & requests ──────────────────────────────────────────────────

@social_bp.route('/api/vapid-public-key')
@login_required
def vapid_public_key():
    _, pub = _get_vapid_keys()
    return jsonify({'publicKey': pub})


@social_bp.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    data = request.get_json()
    endpoint = data.get('endpoint', '').strip()
    p256dh = data.get('p256dh', '').strip()
    auth = data.get('auth', '').strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Missing subscription fields'}), 400
    existing = PushSubscription.query.filter_by(
        user_id=current_user.id, endpoint=endpoint
    ).first()
    if not existing:
        db.session.add(PushSubscription(
            user_id=current_user.id, endpoint=endpoint, p256dh=p256dh, auth=auth
        ))
        db.session.commit()
    return jsonify({'ok': True})


@social_bp.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    data = request.get_json()
    endpoint = data.get('endpoint', '').strip()
    sub = PushSubscription.query.filter_by(
        user_id=current_user.id, endpoint=endpoint
    ).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()
    return jsonify({'ok': True})


@social_bp.route('/api/friends')
@login_required
def api_friends():
    """Return accepted friends list for use by share modals on other pages."""
    fids = _friend_ids(current_user.id)
    friends = User.query.filter(User.id.in_(fids)).all() if fids else []
    return jsonify([
        {'id': f.id, 'username': f.username, 'display_name': f.display_name or f.username}
        for f in friends
    ])


@social_bp.route('/search-users')
@login_required
def search_users():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    users = User.query.filter(
        User.username.ilike(f'%{q}%'),
        User.id != current_user.id
    ).limit(10).all()
    fids = _friend_ids(current_user.id)
    result = []
    for u in users:
        fs = _friendship_between(current_user.id, u.id)
        result.append({
            'id': u.id,
            'username': u.username,
            'display_name': u.display_name or u.username,
            'friendship_status': fs.status if fs else None,
            'is_sender': fs.sender_id == current_user.id if fs else None,
        })
    return jsonify(result)


@social_bp.route('/friend-request', methods=['POST'])
@login_required
def send_friend_request():
    data = request.get_json()
    target_id = int(data.get('user_id', 0))
    if not target_id or target_id == current_user.id:
        return jsonify({'error': 'Invalid user'}), 400
    if not User.query.get(target_id):
        return jsonify({'error': 'User not found'}), 404
    existing = _friendship_between(current_user.id, target_id)
    if existing:
        return jsonify({'error': 'Request already exists'}), 409
    db.session.add(Friendship(sender_id=current_user.id, recipient_id=target_id))
    db.session.commit()
    sender_name = current_user.display_name or current_user.username
    _send_push(target_id, 'New Friend Request', f'{sender_name} sent you a friend request on GritBoard!')
    return jsonify({'ok': True})


@social_bp.route('/friend-respond', methods=['POST'])
@login_required
def respond_friend_request():
    data = request.get_json()
    friendship_id = int(data.get('friendship_id', 0))
    action = data.get('action')  # 'accept' or 'decline'
    fs = Friendship.query.get(friendship_id)
    if not fs or fs.recipient_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404
    fs.status = 'accepted' if action == 'accept' else 'declined'
    fs.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'ok': True, 'status': fs.status})


@social_bp.route('/remove-friend', methods=['POST'])
@login_required
def remove_friend():
    data = request.get_json()
    friend_id = int(data.get('user_id', 0))
    fs = _friendship_between(current_user.id, friend_id)
    if not fs:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(fs)
    db.session.commit()
    return jsonify({'ok': True})


# ── challenges ────────────────────────────────────────────────────────────────

@social_bp.route('/challenge/create', methods=['POST'])
@login_required
def create_challenge():
    data = request.get_json()
    try:
        start = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    except (KeyError, ValueError):
        return jsonify({'error': 'Invalid dates'}), 400
    if end <= start:
        return jsonify({'error': 'End date must be after start date'}), 400

    challenge = Challenge(
        creator_id=current_user.id,
        title=data.get('title', '').strip(),
        description=data.get('description', '').strip(),
        challenge_type=data.get('challenge_type', 'workouts_logged'),
        target_value=float(data.get('target_value', 1)),
        start_date=start,
        end_date=end,
        is_public=bool(data.get('is_public', False)),
    )
    db.session.add(challenge)
    db.session.flush()
    # Creator auto-joins
    db.session.add(ChallengeParticipant(challenge_id=challenge.id, user_id=current_user.id))
    db.session.commit()
    return jsonify({'ok': True, 'challenge_id': challenge.id})


@social_bp.route('/challenge/<int:cid>/join', methods=['POST'])
@login_required
def join_challenge(cid):
    challenge = Challenge.query.get_or_404(cid)
    if ChallengeParticipant.query.filter_by(challenge_id=cid, user_id=current_user.id).first():
        return jsonify({'error': 'Already joined'}), 409
    db.session.add(ChallengeParticipant(challenge_id=cid, user_id=current_user.id))
    db.session.commit()
    return jsonify({'ok': True})


@social_bp.route('/challenge/<int:cid>/leave', methods=['POST'])
@login_required
def leave_challenge(cid):
    p = ChallengeParticipant.query.filter_by(
        challenge_id=cid, user_id=current_user.id
    ).first_or_404()
    db.session.delete(p)
    db.session.commit()
    return jsonify({'ok': True})


@social_bp.route('/challenge/<int:cid>')
@login_required
def challenge_detail(cid):
    challenge = Challenge.query.get_or_404(cid)
    participants = ChallengeParticipant.query.filter_by(challenge_id=cid).all()
    # Compute live progress for each participant
    board = []
    for p in participants:
        progress = _compute_progress(p.user_id, challenge)
        p.current_value = progress
        board.append({'user': p.user, 'value': progress, 'participant': p})
    board.sort(key=lambda x: x['value'], reverse=True)
    db.session.commit()
    my_part = next((x for x in board if x['user'].id == current_user.id), None)
    return render_template('challenge_detail.html', challenge=challenge,
                           board=board, my_part=my_part, today=date.today())


def _compute_progress(user_id, challenge):
    """Calculate a user's current progress value for a challenge."""
    ct = challenge.challenge_type
    start, end = challenge.start_date, min(challenge.end_date, date.today())
    if ct == 'workouts_logged':
        return TrainingEntry.query.filter(
            TrainingEntry.user_id == user_id,
            TrainingEntry.date >= start,
            TrainingEntry.date <= end
        ).count()
    elif ct == 'calories_burned':
        rows = TrainingEntry.query.filter(
            TrainingEntry.user_id == user_id,
            TrainingEntry.date >= start,
            TrainingEntry.date <= end,
            TrainingEntry.calories_burned != None
        ).all()
        return sum(r.calories_burned or 0 for r in rows)
    elif ct == 'streak_days':
        # Count distinct days with at least one training entry
        from sqlalchemy import func
        count = db.session.query(func.count(func.distinct(TrainingEntry.date))).filter(
            TrainingEntry.user_id == user_id,
            TrainingEntry.date >= start,
            TrainingEntry.date <= end
        ).scalar()
        return count or 0
    return 0


# ── share items ───────────────────────────────────────────────────────────────

@social_bp.route('/share', methods=['POST'])
@login_required
def share_item():
    data = request.get_json()
    recipient_id = int(data.get('recipient_id', 0))
    item_type = data.get('item_type')  # workout_plan, playlist, motivation_link
    message = data.get('message', '').strip()[:500]

    if not recipient_id or recipient_id == current_user.id:
        return jsonify({'error': 'Invalid recipient'}), 400
    if not User.query.get(recipient_id):
        return jsonify({'error': 'User not found'}), 404

    if item_type == 'workout_plan':
        plan_name = data.get('plan_name', '').strip()
        exercises = TrainingPlan.query.filter_by(
            user_id=current_user.id, name=plan_name
        ).order_by(TrainingPlan.day_of_week, TrainingPlan.order_index).all()
        if not exercises:
            return jsonify({'error': 'Plan not found'}), 404
        item_data = json.dumps({
            'plan_name': plan_name,
            'exercises': [
                {
                    'day': e.day_of_week, 'exercise': e.exercise_name,
                    'category': e.category, 'sets': e.sets, 'reps': e.reps,
                    'rest_seconds': e.rest_seconds, 'notes': e.notes,
                    'order_index': e.order_index,
                }
                for e in exercises
            ]
        })

    elif item_type == 'playlist':
        playlist_id = int(data.get('playlist_id', 0))
        pl = SavedPlaylist.query.filter_by(id=playlist_id, user_id=current_user.id).first()
        if not pl:
            return jsonify({'error': 'Playlist not found'}), 404
        item_data = json.dumps({
            'title': pl.title, 'youtube_id': pl.youtube_id,
            'playlist_type': pl.playlist_type, 'thumbnail': pl.thumbnail,
            'channel': pl.channel,
        })

    elif item_type == 'motivation_link':
        item_data = json.dumps({
            'url': data.get('url', '').strip(),
            'title': data.get('title', '').strip(),
            'notes': data.get('notes', '').strip(),
        })

    else:
        return jsonify({'error': 'Unknown item type'}), 400

    db.session.add(SharedItem(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        item_type=item_type,
        item_data=item_data,
        message=message,
    ))
    db.session.commit()
    sender_name = current_user.display_name or current_user.username
    type_label = item_type.replace('_', ' ')
    _send_push(recipient_id, 'New Shared Item', f'{sender_name} shared a {type_label} with you on GritBoard!')
    return jsonify({'ok': True})


@social_bp.route('/inbox/mark-seen', methods=['POST'])
@login_required
def mark_seen():
    data = request.get_json()
    item_id = int(data.get('item_id', 0))
    item = SharedItem.query.filter_by(id=item_id, recipient_id=current_user.id).first()
    if item:
        item.seen = True
        db.session.commit()
    return jsonify({'ok': True})


@social_bp.route('/inbox/accept-workout', methods=['POST'])
@login_required
def accept_workout():
    """Clone a shared workout plan into the recipient's own training plans."""
    data = request.get_json()
    item_id = int(data.get('item_id', 0))
    item = SharedItem.query.filter_by(
        id=item_id, recipient_id=current_user.id, item_type='workout_plan'
    ).first_or_404()

    payload = json.loads(item.item_data)
    sender = User.query.get(item.sender_id)
    new_name = f"{payload['plan_name']} (from {sender.display_name or sender.username})"

    for ex in payload.get('exercises', []):
        db.session.add(TrainingPlan(
            user_id=current_user.id,
            name=new_name,
            day_of_week=ex.get('day', 'monday'),
            exercise_name=ex.get('exercise', ''),
            category=ex.get('category'),
            sets=ex.get('sets'),
            reps=ex.get('reps'),
            rest_seconds=ex.get('rest_seconds'),
            notes=ex.get('notes'),
            order_index=ex.get('order_index', 0),
        ))

    item.seen = True
    db.session.commit()
    return jsonify({'ok': True, 'plan_name': new_name})


@social_bp.route('/inbox/save-playlist', methods=['POST'])
@login_required
def save_shared_playlist():
    """Save a shared playlist to the recipient's saved playlists."""
    data = request.get_json()
    item_id = int(data.get('item_id', 0))
    item = SharedItem.query.filter_by(
        id=item_id, recipient_id=current_user.id, item_type='playlist'
    ).first_or_404()

    payload = json.loads(item.item_data)
    already = SavedPlaylist.query.filter_by(
        user_id=current_user.id, youtube_id=payload['youtube_id']
    ).first()
    if not already:
        db.session.add(SavedPlaylist(
            user_id=current_user.id,
            title=payload['title'],
            youtube_id=payload['youtube_id'],
            playlist_type=payload.get('playlist_type', 'playlist'),
            thumbnail=payload.get('thumbnail'),
            channel=payload.get('channel'),
        ))

    item.seen = True
    db.session.commit()
    return jsonify({'ok': True})
