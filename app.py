"""
导了吗签到系统 - 本地运行版
不需要任何云服务，直接在电脑上运行
"""
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
import sqlite3
from datetime import datetime, date
import hashlib
import os

# 创建Flask应用
app = Flask(__name__)
app.secret_key = 'nohand-local-2024-secret-key'  # 本地运行可以用固定密钥

# 数据库路径 - 使用当前目录
DB_FILE = 'nohand.db'

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库表"""
    print("🔄 正在初始化数据库...")
    
    db = get_db()
    cursor = db.cursor()
    
    # 用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 签到表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            checkin_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, checkin_date)
        )
    ''')
    
    db.commit()
    db.close()
    print(f"✅ 数据库初始化完成！文件: {DB_FILE}")

def hash_password(password):
    """密码哈希函数"""
    return hashlib.sha256(password.encode()).hexdigest()

@app.before_request
def load_logged_in_user():
    """在每个请求前加载用户信息"""
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        db.close()

@app.route('/')
def index():
    """首页"""
    if g.user is None:
        return redirect(url_for('login'))
    
    db = get_db()
    today = date.today().isoformat()
    
    # 检查今日是否已签到
    today_checkin = db.execute(
        'SELECT * FROM checkins WHERE user_id = ? AND checkin_date = ?',
        (g.user['id'], today)
    ).fetchone()
    
    # 计算连续没导天数
    streak = 0
    if today_checkin and today_checkin['status'] == '没导':
        # 获取用户的所有签到记录（按日期倒序）
        checkins = db.execute(
            '''SELECT status, checkin_date 
               FROM checkins 
               WHERE user_id = ? 
               ORDER BY checkin_date DESC''',
            (g.user['id'],)
        ).fetchall()
        
        # 计算连续天数
        last_date = None
        for checkin in checkins:
            if checkin['status'] == '没导':
                check_date = datetime.strptime(checkin['checkin_date'], '%Y-%m-%d').date()
                if last_date is None:
                    streak = 1
                    last_date = check_date
                elif (last_date - check_date).days == 1:
                    streak += 1
                    last_date = check_date
                else:
                    break
            else:
                break
    
    db.close()
    
    return render_template('index.html', 
                         user=g.user, 
                         today_checkin=today_checkin,
                         streak=streak)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        
        # 验证输入
        if not username:
            flash('用户名不能为空', 'error')
            return render_template('register.html')
        
        if not password:
            flash('密码不能为空', 'error')
            return render_template('register.html')
        
        if len(username) < 3:
            flash('用户名至少3个字符', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('密码至少需要6位', 'error')
            return render_template('register.html')
        
        db = get_db()
        
        try:
            # 检查用户名是否已存在
            existing = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if existing:
                flash('用户名已存在', 'error')
                return render_template('register.html')
            
            # 创建新用户
            hashed_pw = hash_password(password)
            db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_pw))
            db.commit()
            
            # 获取新用户ID并自动登录
            user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            session.clear()
            session['user_id'] = user['id']
            
            flash('注册成功！', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'注册失败: {str(e)}', 'error')
            return render_template('register.html')
        finally:
            db.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        db.close()
        
        if user and user['password'] == hash_password(password):
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('login'))

@app.route('/checkin', methods=['POST'])
def checkin():
    """签到处理"""
    if g.user is None:
        return redirect(url_for('login'))
    
    status = request.form.get('status')
    if status not in ['导了', '没导']:
        flash('无效的选择', 'error')
        return redirect(url_for('index'))
    
    db = get_db()
    today = date.today().isoformat()
    
    try:
        # 检查是否已签到
        existing = db.execute(
            'SELECT * FROM checkins WHERE user_id = ? AND checkin_date = ?',
            (g.user['id'], today)
        ).fetchone()
        
        if existing:
            flash('今日已签到', 'info')
            return redirect(url_for('index'))
        
        # 插入签到记录
        db.execute(
            'INSERT INTO checkins (user_id, status, checkin_date) VALUES (?, ?, ?)',
            (g.user['id'], status, today)
        )
        db.commit()
        
        flash('签到成功！', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'签到失败: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        db.close()

@app.route('/leaderboard')
def leaderboard():
    """排行榜页面"""
    if g.user is None:
        return redirect(url_for('login'))
    
    db = get_db()
    
    try:
        # 获取所有用户
        users = db.execute('SELECT id, username FROM users ORDER BY username').fetchall()
        leaderboard_data = []
        
        for user in users:
            # 获取用户的所有签到记录
            checkins = db.execute(
                '''SELECT checkin_date, status 
                   FROM checkins 
                   WHERE user_id = ? 
                   ORDER BY checkin_date DESC''',
                (user['id'],)
            ).fetchall()
            
            if checkins:
                latest = checkins[0]
                
                # 计算连续没导天数
                streak = 0
                for checkin in checkins:
                    if checkin['status'] == '没导':
                        streak += 1
                    else:
                        break
                
                leaderboard_data.append({
                    'username': user['username'],
                    'status': latest['status'],
                    'days': streak if latest['status'] == '没导' else 0,
                    'last_date': latest['checkin_date']
                })
            else:
                leaderboard_data.append({
                    'username': user['username'],
                    'status': '未签到',
                    'days': 0,
                    'last_date': None
                })
        
        # 排序规则：1.没导的在前 2.按天数降序 3.导了的在后 4.未签到的最后
        def sort_key(item):
            if item['status'] == '没导':
                return (0, -item['days'])
            elif item['status'] == '导了':
                return (1, 0)
            else:
                return (2, 0)
        
        leaderboard_data.sort(key=sort_key)
        
        return render_template('leaderboard.html', leaderboard=leaderboard_data)
        
    except Exception as e:
        flash(f'加载排行榜失败: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        db.close()

@app.route('/debug')
def debug_info():
    """调试信息页面"""
    info = {
        'database_file': DB_FILE,
        'database_size': '不存在',
        'user_count': 0,
        'checkin_count': 0,
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'current_user': g.user['username'] if g.user else '未登录'
    }
    
    if os.path.exists(DB_FILE):
        info['database_size'] = f"{os.path.getsize(DB_FILE) / 1024:.1f} KB"
        
        db = get_db()
        info['user_count'] = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        info['checkin_count'] = db.execute('SELECT COUNT(*) FROM checkins').fetchone()[0]
        db.close()
    
    return info

@app.route('/reset')
def reset_data():
    """重置数据（慎用！）"""
    if g.user and g.user['username'] == 'admin':  # 只有admin用户可以重置
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            flash('数据库已重置', 'info')
            init_db()
        return redirect(url_for('index'))
    else:
        flash('没有权限', 'error')
        return redirect(url_for('index'))

def create_admin_user():
    """创建默认管理员用户"""
    db = get_db()
    
    # 检查是否已有admin用户
    admin = db.execute('SELECT id FROM users WHERE username = ?', ('admin',)).fetchone()
    
    if not admin:
        hashed_pw = hash_password('admin123')
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', ('admin', hashed_pw))
        db.commit()
        print("👑 已创建管理员账号: admin / admin123")
    
    db.close()

# 初始化数据库
init_db()
create_admin_user()

print("=" * 50)
print("🚀 导了吗签到系统 - 本地运行版")
print("=" * 50)
print(f"📁 数据库文件: {DB_FILE}")
print("🌐 访问地址: http://localhost:5000")
print("👑 管理员账号: admin / admin123")
print("=" * 50)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)