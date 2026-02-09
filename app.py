from flask import Flask, request, jsonify, render_template, send_from_directory
import sqlite3
import os
from datetime import datetime
import base64

app = Flask(__name__)

# --- ОСЫ БӨЛІМ Render ҮШІН ӨТЕ МАҢЫЗДЫ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'violations')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Папкалар жоқ болса, автоматты түрде жасау
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
# ---------------------------------------

# Initialize database
def init_db():
    # Базаға толық жол (DB_PATH) арқылы қосылу
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            violation_type TEXT NOT NULL,
            image_path TEXT NOT NULL,
            object_name TEXT DEFAULT 'Worker',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Сервер қосылғанда базаны бірден дайындау
init_db()

@app.route('/')
def index():
    # Ең басты қате осы жерде болды. Енді ол DB_PATH-ты көреді.
    try:
        return render_template('incident_log.html')
    except Exception as e:
        return f"Template Error: {str(e)}", 500

@app.route('/api/add_violation', methods=['POST'])
def add_violation():
    """Receive violation data from Telegram bot"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        timestamp = data.get('timestamp', datetime.now().strftime('%H:%M:%S %d.%m.%Y'))
        violation_type = data.get('violation_type', 'No Helmet')
        object_name = data.get('object_name', 'Worker')
        
        image_path = None
        if 'image_base64' in data:
            image_data = base64.b64decode(data['image_base64'])
            filename = f"violation_{int(datetime.now().timestamp())}.jpg"
            
            # Рендерде файлды сақтау үшін толық жол керек
            full_save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            with open(full_save_path, 'wb') as f:
                f.write(image_data)
            
            image_path = f"violations/{filename}"
        
        elif 'image_path' in data:
            image_path = data['image_path']
        
        if not image_path:
            return jsonify({'error': 'No image provided'}), 400
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO violations (timestamp, violation_type, image_path, object_name)
            VALUES (?, ?, ?, ?)
        ''', (timestamp, violation_type, image_path, object_name))
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'Violation recorded',
            'id': last_id
        }), 201
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/violations', methods=['GET'])
def get_violations():
    """Get all violations"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        cursor.execute('''
            SELECT id, timestamp, violation_type, image_path, object_name, created_at
            FROM violations
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        violations = []
        for row in cursor.fetchall():
            violations.append({
                'id': row['id'],
                'timestamp': row['timestamp'],
                'violation_type': row['violation_type'],
                'image_path': row['image_path'],
                'object_name': row['object_name'],
                'created_at': row['created_at']
            })
        
        cursor.execute('SELECT COUNT(*) as count FROM violations')
        total = cursor.fetchone()['count']
        conn.close()
        
        return jsonify({
            'violations': violations,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/violations/<int:violation_id>', methods=['DELETE'])
def delete_violation(violation_id):
    """Delete a specific violation"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT image_path FROM violations WHERE id = ?', (violation_id,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute('DELETE FROM violations WHERE id = ?', (violation_id,))
            conn.commit()
            
            image_path = row[0]
            full_path = os.path.join(BASE_DIR, 'static', image_path)
            if os.path.exists(full_path):
                os.remove(full_path)
            
            conn.close()
            return jsonify({'status': 'success', 'message': 'Violation deleted'})
        else:
            conn.close()
            return jsonify({'error': 'Violation not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
