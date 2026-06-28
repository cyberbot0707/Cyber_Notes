import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'YOUR_SECRET_KEY_PLACEHOLDER'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


UPLOAD_FOLDER = os.path.join(basedir, 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024


ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'webp', 'heic', 'heif', 'svg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    recovery_code = db.Column(db.String(120), nullable=False)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), default="Без названия")
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default="Без категории")
    date_posted = db.Column(db.String(20), default=lambda: datetime.now().strftime("%d.%m.%Y"))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    file_mapping = db.Column(db.String(256), nullable=True)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        r = request.form.get('recovery_code')
        if User.query.filter_by(username=u).first():
            flash('Этот логин уже занят!', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=u, password=p, recovery_code=r)
        db.session.add(new_user)
        db.session.commit()
        flash('Аккаунт создан! Запомните ваш код.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        user = User.query.filter_by(username=u).first()
        if user and user.password == p:
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        flash('Неверный логин или пароль', 'danger')
    return render_template('login.html')


@app.route('/reset', methods=['GET', 'POST'])
def reset():
    if request.method == 'POST':
        username = request.form.get('username')
        verification = request.form.get('verification')
        new_password = request.form.get('new_password')
        user = User.query.filter_by(username=username).first()
        if user and (verification == user.password or verification == user.recovery_code):
            user.password = new_password
            db.session.commit()
            flash('Пароль успешно изменен!', 'success')
            return redirect(url_for('login'))
        else:
            flash('Ошибка: неверные данные для восстановления!', 'danger')
    return render_template('reset.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))



@app.route('/')
@login_required
def dashboard():
    search = request.args.get('search')
    cat_filter = request.args.get('category')

    query = Note.query.filter_by(user_id=session['user_id'])

    if search:
        query = query.filter(Note.title.contains(search))
    if cat_filter:
        query = query.filter(Note.category == cat_filter)

    notes = query.order_by(Note.id.desc()).all()
    all_user_notes = Note.query.filter_by(user_id=session['user_id']).all()
    categories = sorted(list(set([n.category for n in all_user_notes if n.category])))

    return render_template('dashboard.html', notes=notes, categories=categories, current_cat=cat_filter)


@app.route('/add', methods=['POST'])
@login_required
def add_note():
    title = request.form.get('title') or "Без названия"
    content = request.form.get('content') or ""
    category = request.form.get('category') or "Общие"

    filename_to_save = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename != '' and allowed_file(file.filename):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filename = secure_filename(file.filename)
            filename_to_save = f"{int(datetime.utcnow().timestamp())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename_to_save))

    if content or filename_to_save:
        new_note = Note(
            title=title,
            content=content,
            category=category,
            user_id=session['user_id'],
            file_mapping=filename_to_save
        )
        db.session.add(new_note)
        db.session.commit()

    return redirect(url_for('dashboard'))


@app.route('/edit/<int:note_id>', methods=['POST'])
@login_required
def edit_note(note_id):
    note = Note.query.get(note_id)
    if note and note.user_id == session['user_id']:
        note.title = request.form.get('title') or "Без названия"
        note.category = request.form.get('category') or "Без категории"
        note.content = request.form.get('content')

        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '' and allowed_file(file.filename):
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                filename = secure_filename(file.filename)
                filename_to_save = f"{int(datetime.utcnow().timestamp())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename_to_save))
                note.file_mapping = filename_to_save

        db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/delete/<int:note_id>')
@login_required
def delete_note(note_id):
    note = Note.query.get(note_id)
    if note and note.user_id == session['user_id']:
        db.session.delete(note)
        db.session.commit()
    return redirect(url_for('dashboard'))



@app.route('/download/<int:note_id>')
@login_required
def download_note(note_id):
    note = Note.query.get(note_id)
    if note and note.user_id == session['user_id']:
        text_content = f"Заголовок: {note.title}\nКатегория: {note.category}\nСоздано: {note.date_posted}\n\n{note.content}"

        return Response(
            text_content,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-disposition": f"attachment; filename=CryptoNote_{note.id}.txt"}
        )
    return redirect(url_for('dashboard'))


@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    current_user = User.query.get(session['user_id'])

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'change_password':
            old_pwd = request.form.get('old_password')
            new_pwd = request.form.get('new_password')

            if old_pwd == current_user.password:
                current_user.password = new_pwd
                db.session.commit()
                flash('Пароль успешно изменен!', 'success')
            else:
                flash('Неверный текущий пароль!', 'danger')

        elif action == 'change_recovery':
            pwd = request.form.get('password_for_recovery')
            new_rec = request.form.get('new_recovery_code')

            if pwd == current_user.password:
                current_user.recovery_code = new_rec
                db.session.commit()
                flash('Код восстановления успешно обновлен!', 'success')
            else:
                flash('Неверный пароль! Изменение отклонено.', 'danger')

        return redirect(url_for('account'))

    return render_template('account.html', user=current_user)


@app.after_request
def apply_hsts(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=False)