import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename
from . import db, login_manager
from .models import User, Topic, Lesson, QuizQuestion, LessonProgress, QuizAttempt, LearningActivity
from .forms import RegisterForm, LoginForm, AdminLoginForm

bp = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def record(action):
    db.session.add(LearningActivity(user_id=current_user.id, action=action))
    db.session.commit()

def progress_for_user(user_id):
    total = Lesson.query.count()
    if not total: return 0
    done = LessonProgress.query.filter_by(user_id=user_id, completed=True).count()
    return round(done / total * 100)

def topic_progress(topic, user_id):
    total = len(topic.lessons)
    if not total: return 0
    ids = [l.id for l in topic.lessons]
    done = LessonProgress.query.filter_by(user_id=user_id, completed=True).filter(LessonProgress.lesson_id.in_(ids)).count()
    return round(done / total * 100)

def admin_required():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.admin_login'))
    if current_user.role != 'admin': abort(403)
    if not current_user.is_active:
        logout_user(); return redirect(url_for('auth.admin_login'))
    return None

def _save_content_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in {'png','jpg','jpeg','webp'}:
        raise ValueError('Use PNG, JPG, JPEG or WebP images for lesson content.')
    filename = f'lesson_{uuid.uuid4().hex}.{ext}'
    destination = Path(current_app.config['UPLOAD_FOLDER']) / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(destination)
    return f'uploads/{filename}'

@bp.route('/')
def home():
    return render_template('home.html', topics=Topic.query.order_by(Topic.position).all())

@bp.route('/register', methods=['GET','POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('auth.dashboard'))
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter(func.lower(User.email) == form.email.data.lower()).first():
            flash('An account with that email already exists.', 'danger')
        else:
            u = User(full_name=form.full_name.data.strip(), email=form.email.data.lower().strip())
            u.set_password(form.password.data); db.session.add(u); db.session.commit(); login_user(u)
            record('Account registered'); flash('Account created successfully.', 'success')
            return redirect(url_for('auth.dashboard'))
    return render_template('auth/register.html', form=form)

@bp.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('auth.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        u = User.query.filter(func.lower(User.email) == form.email.data.lower()).first()
        if u and u.is_active and u.check_password(form.password.data):
            u.last_login = datetime.utcnow(); db.session.commit(); login_user(u); record('Successful login')
            return redirect(url_for('auth.admin_dashboard' if u.role == 'admin' else 'auth.dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html', form=form)

@bp.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if current_user.is_authenticated:
        if current_user.role == 'admin': return redirect(url_for('auth.admin_dashboard'))
        logout_user()
    form = AdminLoginForm()
    if form.validate_on_submit():
        u = User.query.filter(func.lower(User.email) == form.email.data.strip().lower()).first()
        if u and u.role == 'admin' and u.is_active and u.check_password(form.password.data):
            u.last_login = datetime.utcnow(); db.session.commit(); login_user(u)
            return redirect(url_for('auth.admin_dashboard'))
        flash('Invalid administrator credentials.', 'danger')
    return render_template('admin/login.html', form=form)

@bp.route('/logout')
@login_required
def logout():
    logout_user(); flash('You have been logged out.', 'success'); return redirect(url_for('auth.home'))

@bp.route('/admin/logout')
def admin_logout():
    logout_user(); return redirect(url_for('auth.admin_login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin': return redirect(url_for('auth.admin_dashboard'))
    topics = Topic.query.order_by(Topic.position).all()
    attempts = QuizAttempt.query.filter_by(user_id=current_user.id).order_by(QuizAttempt.created_at.desc()).limit(8).all()
    activities = LearningActivity.query.filter_by(user_id=current_user.id).order_by(LearningActivity.created_at.desc()).limit(8).all()
    topic_rows=[(t, topic_progress(t, current_user.id)) for t in topics]
    return render_template('dashboard.html', topic_rows=topic_rows, progress=progress_for_user(current_user.id), attempts=attempts, activities=activities, completed_count=LessonProgress.query.filter_by(user_id=current_user.id, completed=True).count(), total_lessons=Lesson.query.count())

@bp.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    if current_user.role == 'admin': return redirect(url_for('auth.admin_dashboard'))
    if request.method == 'POST':
        full_name = (request.form.get('full_name') or '').strip(); email = (request.form.get('email') or '').strip().lower()
        if len(full_name) < 2 or len(full_name) > 120 or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            flash('Please enter a valid name and email.', 'danger'); return redirect(url_for('auth.profile'))
        other = User.query.filter(func.lower(User.email) == email, User.id != current_user.id).first()
        if other: flash('That email address is already in use.', 'danger'); return redirect(url_for('auth.profile'))

        current_user.full_name, current_user.email = full_name, email
        new_password = request.form.get('new_password') or ''
        if new_password:
            if not current_user.check_password(request.form.get('current_password') or ''):
                flash('Your current password is incorrect.', 'danger'); return redirect(url_for('auth.profile'))
            if len(new_password) < 8 or new_password != request.form.get('confirm_password'):
                flash('New passwords must match and contain at least 8 characters.', 'danger'); return redirect(url_for('auth.profile'))
            current_user.set_password(new_password)

        db.session.commit(); flash('Profile updated successfully.', 'success'); return redirect(url_for('auth.profile'))
    return render_template('profile.html', attempt_count=QuizAttempt.query.filter_by(user_id=current_user.id).count(), completed=LessonProgress.query.filter_by(user_id=current_user.id, completed=True).count(), total=Lesson.query.count())


def _save_profile_image(file_storage, user_id):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in {'png', 'jpg', 'jpeg', 'webp'}:
        raise ValueError('Use PNG, JPG, JPEG or WebP profile images.')
    filename = f'profile_{user_id}_{uuid.uuid4().hex}.{ext}'
    destination = Path(current_app.config['UPLOAD_FOLDER']) / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(destination)
    return f'uploads/{filename}'

@bp.route('/profile/photo', methods=['POST'])
@login_required
def profile_photo():
    if current_user.role == 'admin': return redirect(url_for('auth.admin_dashboard'))
    profile_image = request.files.get('profile_image')
    if not profile_image or not profile_image.filename:
        flash('Choose a profile picture before uploading.', 'warning')
        return redirect(url_for('auth.profile'))
    try:
        current_user.profile_photo = _save_profile_image(profile_image, current_user.id)
        db.session.commit()
        flash('Profile picture updated successfully.', 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('auth.profile'))

@bp.route('/topics')
@bp.route('/courses')
def topics():
    return render_template('courses.html', topics=Topic.query.order_by(Topic.position).all())

@bp.route('/topic/<int:topic_id>')
@bp.route('/course/<int:course_id>')
def topic_detail(topic_id=None, course_id=None):
    topic = db.session.get(Topic, topic_id or course_id) or abort(404)
    return render_template('course.html', topic=topic, progress=topic_progress(topic, current_user.id) if current_user.is_authenticated else 0)

@bp.route('/lesson/<int:lesson_id>')
@login_required
def lesson(lesson_id):
    lesson = db.session.get(Lesson, lesson_id) or abort(404)
    prog = LessonProgress.query.filter_by(user_id=current_user.id, lesson_id=lesson.id).first()
    # Opening the lesson records that the learner has reached the reading material.
    # The knowledge check is deliberately a separate screen after this step.
    viewed_action = f'Viewed lesson: {lesson.title}'
    if not LearningActivity.query.filter_by(user_id=current_user.id, action=viewed_action).first():
        record(viewed_action)
    return render_template('lesson.html', lesson=lesson, topic=lesson.topic, prog=prog)

@bp.route('/lesson/<int:lesson_id>/quiz', methods=['GET','POST'])
@login_required
def quiz(lesson_id):
    lesson = db.session.get(Lesson, lesson_id) or abort(404)
    viewed_action = f'Viewed lesson: {lesson.title}'
    if not LearningActivity.query.filter_by(user_id=current_user.id, action=viewed_action).first():
        flash('Please read the lesson material before starting the knowledge check.', 'warning')
        return redirect(url_for('auth.lesson', lesson_id=lesson.id))
    qs = lesson.questions
    if request.method == 'GET':
        return render_template('quiz.html', lesson=lesson, topic=lesson.topic, questions=qs)
    score = 0
    for q in qs:
        try: ans = int(request.form.get(f'q_{q.id}', '-1'))
        except ValueError: ans = -1
        if ans == q.correct_index: score += 1
    total = len(qs); pct = round(score / total * 100, 1) if total else 0
    db.session.add(QuizAttempt(user_id=current_user.id, lesson_id=lesson.id, score=score, total=total, percentage=pct)); db.session.commit()
    return render_template('quiz_result.html', lesson=lesson, topic=lesson.topic, score=score, total=total, percentage=pct, questions=qs, answers=request.form)

@bp.route('/lesson/<int:lesson_id>/complete', methods=['POST'])
@login_required
def complete_lesson(lesson_id):
    lesson = db.session.get(Lesson, lesson_id) or abort(404)
    latest = QuizAttempt.query.filter_by(user_id=current_user.id, lesson_id=lesson.id).order_by(QuizAttempt.created_at.desc()).first()
    if not latest or latest.percentage < 70:
        flash('Score at least 70% on the knowledge check before completing this lesson.', 'warning')
        return redirect(url_for('auth.lesson', lesson_id=lesson.id))
    p = LessonProgress.query.filter_by(user_id=current_user.id, lesson_id=lesson.id).first()
    if not p: p = LessonProgress(user_id=current_user.id, lesson_id=lesson.id); db.session.add(p)
    p.completed = True; p.completed_at = datetime.utcnow(); db.session.commit(); record(f'Completed lesson: {lesson.title}')
    return redirect(url_for('auth.topic_detail', topic_id=lesson.topic_id))

# ---------------- Admin ----------------
@bp.route('/admin')
def admin_dashboard():
    gate = admin_required()
    if gate: return gate
    students = User.query.filter_by(role='student').order_by(User.created_at.desc()).all()
    return render_template('admin/dashboard.html', students=students, topics=Topic.query.order_by(Topic.position).all(), lesson_count=Lesson.query.count(), question_count=QuizQuestion.query.count(), attempt_count=QuizAttempt.query.count(), completed_count=LessonProgress.query.filter_by(completed=True).count())

@bp.route('/admin/users')
def admin_students():
    gate = admin_required()
    if gate: return gate
    return render_template('admin/students.html', students=User.query.filter_by(role='student').order_by(User.created_at.desc()).all())

@bp.route('/admin/users/<int:user_id>')
def admin_student_detail(user_id):
    gate = admin_required()
    if gate: return gate
    student = User.query.filter_by(id=user_id, role='student').first() or abort(404)
    progress = LessonProgress.query.filter_by(user_id=student.id, completed=True).count()
    attempts = QuizAttempt.query.filter_by(user_id=student.id).order_by(QuizAttempt.created_at.desc()).all()
    return render_template('admin/student_detail.html', student=student, progress=progress, total=Lesson.query.count(), attempts=attempts)

@bp.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
def admin_toggle_student(user_id):
    gate = admin_required()
    if gate: return gate
    student = User.query.filter_by(id=user_id, role='student').first() or abort(404)
    student.is_active = not student.is_active; db.session.commit()
    flash(f"{student.full_name}'s account is now {'active' if student.is_active else 'inactive'}.", 'success')
    return redirect(url_for('auth.admin_student_detail', user_id=student.id))

@bp.route('/admin/topics/new', methods=['GET','POST'])
def admin_topic_new():
    gate = admin_required()
    if gate: return gate
    topic = Topic.query.order_by(Topic.position.desc()).first() if False else None
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        position_raw = (request.form.get('position') or '').strip()
        if not title or not description:
            flash('Topic title and description are required.', 'danger')
            return render_template('admin/topic_form.html', topic=None, editing=False, next_position=(Topic.query.count() + 1))
        existing = Topic.query.filter(func.lower(Topic.title) == title.lower()).first()
        if existing:
            flash('A topic with this title already exists. Use a different topic title.', 'danger')
            return render_template('admin/topic_form.html', topic=None, editing=False, next_position=(Topic.query.count() + 1))
        try:
            position = int(position_raw) if position_raw else (Topic.query.count() + 1)
        except ValueError:
            position = Topic.query.count() + 1
        base_slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or 'topic'
        slug = base_slug
        suffix = 2
        while Topic.query.filter_by(slug=slug).first():
            slug = f'{base_slug}-{suffix}'; suffix += 1
        topic = Topic(title=title, slug=slug, description=description, position=max(1, position))
        db.session.add(topic); db.session.commit()
        flash('Topic added successfully.', 'success')
        return redirect(url_for('auth.admin_topic_detail', topic_id=topic.id))
    return render_template('admin/topic_form.html', topic=None, editing=False, next_position=Topic.query.count() + 1)

@bp.route('/admin/topics/<int:topic_id>/edit', methods=['GET','POST'])
def admin_topic_edit(topic_id):
    gate = admin_required()
    if gate: return gate
    topic = db.session.get(Topic, topic_id) or abort(404)
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        if not title or not description:
            flash('Topic title and description are required.', 'danger')
        else:
            existing = Topic.query.filter(func.lower(Topic.title) == title.lower(), Topic.id != topic.id).first()
            if existing:
                flash('Another topic already uses this title. Choose a different title.', 'danger')
            else:
                base_slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or f'topic-{topic.id}'
                slug = base_slug; suffix = 2
                while True:
                    conflict = Topic.query.filter(Topic.slug == slug, Topic.id != topic.id).first()
                    if not conflict: break
                    slug = f'{base_slug}-{suffix}'; suffix += 1
                try:
                    topic.position = max(1, int(request.form.get('position') or topic.position))
                except ValueError:
                    pass
                topic.title = title; topic.description = description; topic.slug = slug
                db.session.commit(); flash('Topic updated successfully.', 'success')
                return redirect(url_for('auth.admin_topic_detail', topic_id=topic.id))
    return render_template('admin/topic_form.html', topic=topic, editing=True, next_position=topic.position)

@bp.route('/admin/topics/<int:topic_id>/delete', methods=['POST'])
def admin_topic_delete(topic_id):
    gate = admin_required()
    if gate: return gate
    topic = db.session.get(Topic, topic_id) or abort(404)
    title = topic.title
    db.session.delete(topic); db.session.commit()
    flash(f'Topic "{title}" and its learning material were deleted.', 'success')
    return redirect(url_for('auth.admin_topics'))

@bp.route('/admin/topics')
def admin_topics():
    gate = admin_required()
    if gate: return gate
    return render_template('admin/topics.html', topics=Topic.query.order_by(Topic.position).all())

@bp.route('/admin/topics/<int:topic_id>')
def admin_topic_detail(topic_id):
    gate = admin_required()
    if gate: return gate
    topic = db.session.get(Topic, topic_id) or abort(404)
    return render_template('admin/topic_detail.html', topic=topic)

@bp.route('/admin/lessons/new', methods=['GET','POST'])
@bp.route('/admin/lessons/<int:lesson_id>/edit', methods=['GET','POST'])
def admin_lesson_edit(lesson_id=None):
    gate = admin_required()
    if gate: return gate
    lesson = db.session.get(Lesson, lesson_id) if lesson_id else Lesson(position=1, topic_id=int(request.args.get('topic_id') or 0))
    if lesson_id and not lesson: abort(404)
    topics = Topic.query.order_by(Topic.position).all()
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip(); topic_id = request.form.get('topic_id')
        if not title or not topic_id: flash('Topic and lesson title are required.', 'danger')
        else:
            if not lesson_id: db.session.add(lesson)
            lesson.topic_id = int(topic_id); lesson.title = title
            lesson.objectives = request.form.get('objectives','').strip(); lesson.content = request.form.get('content','').strip()
            lesson.examples = request.form.get('examples','').strip(); lesson.takeaways = request.form.get('takeaways','').strip()
            lesson.image_alt = request.form.get('image_alt','').strip(); lesson.position = int(request.form.get('position') or 1)
            image = request.files.get('image_file')
            if image and image.filename:
                try:
                    lesson.image_path = _save_content_image(image)
                except ValueError as exc:
                    flash(str(exc), 'danger'); return redirect(request.url)
            db.session.commit(); flash('Lesson saved.', 'success'); return redirect(url_for('auth.admin_topic_detail', topic_id=lesson.topic_id))
    return render_template('admin/lesson_form.html', lesson=lesson, topics=topics, editing=bool(lesson_id))

@bp.route('/admin/lessons/<int:lesson_id>/delete', methods=['POST'])
def admin_lesson_delete(lesson_id):
    gate = admin_required()
    if gate: return gate
    lesson = db.session.get(Lesson, lesson_id) or abort(404); topic_id = lesson.topic_id
    db.session.delete(lesson); db.session.commit(); flash('Lesson deleted.', 'success')
    return redirect(url_for('auth.admin_topic_detail', topic_id=topic_id))

@bp.route('/admin/questions/new', methods=['GET','POST'])
@bp.route('/admin/questions/<int:question_id>/edit', methods=['GET','POST'])
def admin_question_edit(question_id=None):
    gate = admin_required()
    if gate: return gate
    q = db.session.get(QuizQuestion, question_id) if question_id else QuizQuestion(lesson_id=int(request.args.get('lesson_id') or 0))
    if question_id and not q: abort(404)
    lessons = Lesson.query.order_by(Lesson.title).all()
    if request.method == 'POST':
        q.lesson_id = int(request.form.get('lesson_id')); q.question = request.form.get('question','').strip(); q.explanation = request.form.get('explanation','').strip()
        options = [request.form.get(f'option_{i}','').strip() for i in range(4)]
        if not q.question or any(not x for x in options): flash('Question and all four options are required.', 'danger')
        else:
            q.options = json.dumps(options); q.correct_index = int(request.form.get('correct_index','0'))
            if not question_id: db.session.add(q)
            db.session.commit(); flash('Question saved.', 'success'); return redirect(url_for('auth.admin_topic_detail', topic_id=q.lesson.topic_id))
    current_options = json.loads(q.options) if q.options else ['','','','']
    return render_template('admin/question_form.html', question=q, lessons=lessons, options=current_options)

@bp.route('/admin/questions/<int:question_id>/delete', methods=['POST'])
def admin_question_delete(question_id):
    gate = admin_required()
    if gate: return gate
    q = db.session.get(QuizQuestion, question_id) or abort(404); topic_id = q.lesson.topic_id
    db.session.delete(q); db.session.commit(); flash('Question deleted.', 'success')
    return redirect(url_for('auth.admin_topic_detail', topic_id=topic_id))

@bp.route('/admin/results')
def admin_results():
    gate = admin_required()
    if gate: return gate
    return render_template('admin/results.html', rows=QuizAttempt.query.order_by(QuizAttempt.created_at.desc()).all())
