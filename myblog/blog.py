import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import requests
from flask import jsonify
from datetime import datetime, timezone

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '123456')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)

    email = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class BlogPost(db.Model):
    __tablename__ = 'blog_post'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='published')  # 'published', 'draft'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship('User', backref='posts')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)   # 消息内容
    role = db.Column(db.String(10), nullable=False)  # 'user' 或 'assistant'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='messages')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def call_ai(user_msg):
    API_KEY = os.getenv('API_KEY')
    URL = os.getenv('URL')
    headers = {
        'Authorization' : f'Bearer {API_KEY}' ,
        'Content-Type' : 'application/json'
    }
    data = {
        'model' : 'qwen-turbo',
        'messages' : [{'role':'user','content':user_msg}]
    }

    try:
        resp = requests.post(URL , headers = headers , json = data , timeout = 30)
        resp.raise_for_status() #坚持返回的状态码是否是200
        result = resp.json()
        ai_messages = result['choices'][0]['message']['content']
        print ('AI回复:' ,ai_messages , '时间为:',datetime.now(timezone.utc))
        return ai_messages
    except requests.exceptions.RequestException as e:
        print('请求出错:',e)
        return None
    except KeyError as e:
        print('返回出错',e)
        print(resp.text)
        return None




@app.route('/')
def home():
    contents = BlogPost.query.filter_by(status='published').order_by(BlogPost.created_at.desc()).all()
    return render_template('home.html', contents=contents)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            return "用户名或密码错误", 401
    return render_template('login.html')

@app.route('/ai_chat' , methods = ['GET','POST'])
@login_required
def ai_chat():
    if request.method == 'POST':
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message'}), 400
        user_msg = data['message'].strip()
        if not user_msg:
            return jsonify({'error': 'Empty message'}), 400
        user_msg_record = Message(content=user_msg, role='user', user_id=current_user.id)
        db.session.add(user_msg_record)

        ai_reply = call_ai(user_msg)
        if not ai_reply:
            ai_reply = '当前AI暂时不可用'
        ai_msg_record = Message(content=ai_reply, role='assistant', user_id=current_user.id)
        db.session.add(ai_msg_record)
        db.session.commit()
        return jsonify({'reply': ai_reply})


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            return "用户名已存在", 400
        if User.query.filter_by(email=email).first():
            return "邮箱已注册", 400
        if not password:
            return "密码不能为空", 400
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        title = request.form.get('title')
        content_text = request.form.get('content')
        if not title:
            return "标题不能为空", 400
        if not content_text:
            return "内容不能为空", 400
        new_content = BlogPost(title=title, content=content_text, user_id=current_user.id)
        db.session.add(new_content)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('create.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)