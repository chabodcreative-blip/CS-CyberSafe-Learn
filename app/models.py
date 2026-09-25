from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    profile_photo = db.Column(db.String(255), nullable=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Topic(db.Model):
    __tablename__ = 'cyber_topic'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False, unique=True)
    slug = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)
    lessons = db.relationship('Lesson', backref='topic', cascade='all, delete-orphan', order_by='Lesson.position')

class Lesson(db.Model):
    __tablename__ = 'cyber_lesson'
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('cyber_topic.id'), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    objectives = db.Column(db.Text, nullable=False)
    content = db.Column(db.Text, nullable=False)
    examples = db.Column(db.Text, nullable=False)
    takeaways = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    image_alt = db.Column(db.String(255), nullable=True)
    position = db.Column(db.Integer, default=1, nullable=False)
    questions = db.relationship('QuizQuestion', backref='lesson', cascade='all, delete-orphan', order_by='QuizQuestion.id')

class QuizQuestion(db.Model):
    __tablename__ = 'cyber_quiz_question'
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('cyber_lesson.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text, nullable=False)
    correct_index = db.Column(db.Integer, nullable=False)
    explanation = db.Column(db.Text, nullable=False)

class LessonProgress(db.Model):
    __tablename__ = 'cyber_lesson_progress'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('cyber_lesson.id'), nullable=False)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime)
    __table_args__ = (db.UniqueConstraint('user_id', 'lesson_id', name='uq_cyber_lesson_progress'),)

class QuizAttempt(db.Model):
    __tablename__ = 'cyber_quiz_attempt'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('cyber_lesson.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='cyber_quiz_attempts')
    lesson = db.relationship('Lesson', backref='cyber_quiz_attempts')

class LearningActivity(db.Model):
    __tablename__ = 'cyber_learning_activity'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='cyber_learning_activities')
