import os
import uuid
from datetime import date, datetime

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, send_from_directory
from flask_login import login_required, current_user
from models import db, ProgressPhoto
from werkzeug.utils import secure_filename
from app import user_today

photos_bp = Blueprint('photos', __name__)

UPLOAD_DIR = '/app/data/photos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


@photos_bp.route('/')
@login_required
def photos_page():
    photos = ProgressPhoto.query.filter_by(user_id=current_user.id)\
        .order_by(ProgressPhoto.date.desc()).all()
    return render_template('photos.html', photos=photos, today=user_today(current_user.tz).isoformat())


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@photos_bp.route('/upload', methods=['POST'])
@login_required
def upload_photo():
    if 'photo' not in request.files:
        return redirect(url_for('photos.photos_page'))

    file = request.files['photo']
    if file.filename == '' or not _allowed_file(file.filename):
        return redirect(url_for('photos.photos_page'))

    # Create user-specific directory
    user_dir = os.path.join(UPLOAD_DIR, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)

    # Compress and save as JPEG to limit storage
    from PIL import Image
    import io
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(user_dir, filename)
    try:
        img = Image.open(file)
        img.thumbnail((1600, 1600), Image.LANCZOS)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(filepath, 'JPEG', quality=80, optimize=True)
    except Exception:
        # Fallback: save original if Pillow fails
        file.seek(0)
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(user_dir, filename)
        file.save(filepath)

    date_str = request.form.get('date')
    photo_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()

    photo = ProgressPhoto(
        user_id=current_user.id,
        date=photo_date,
        filename=filename,
        caption=request.form.get('caption', '').strip() or None,
    )
    db.session.add(photo)
    db.session.commit()
    return redirect(url_for('photos.photos_page'))


@photos_bp.route('/delete/<int:photo_id>', methods=['POST'])
@login_required
def delete_photo(photo_id):
    photo = ProgressPhoto.query.get_or_404(photo_id)
    if photo.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Delete file
    filepath = os.path.join(UPLOAD_DIR, str(current_user.id), photo.filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    db.session.delete(photo)
    db.session.commit()
    return redirect(url_for('photos.photos_page'))


@photos_bp.route('/file/<int:user_id>/<filename>')
@login_required
def serve_photo(user_id, filename):
    if user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    user_dir = os.path.join(UPLOAD_DIR, str(user_id))
    return send_from_directory(user_dir, secure_filename(filename))
