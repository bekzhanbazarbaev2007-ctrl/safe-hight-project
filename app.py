from flask import Flask, request, jsonify, render_template, send_from_directory
import sqlite3
import os
from datetime import datetime
import base64

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/violations'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# --- ЖАҢА: Жүйе күйін сақтау ---
system_status = {
    "mode": "auto",
    "trigger_capture": False
}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def init_db():
    conn = sqlite3.connect('database.db')
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

init_db()

@app.route('/')
def index():
    return render_template('incident_log.html')

# --- ЖАҢА: Режимді ауыстыру API ---
@app.route('/api/set_mode', methods=['POST'])
def set_mode():
    data = request.json
    system_status["mode"] = data.get('mode', 'auto')
    return jsonify({"status": "success", "current_mode": system_status["mode"]})

# --- ЖАҢА: Суретке түсіру командасын беру ---
@app.route('/api/trigger_capture', methods=['POST'])
def trigger_capture():
    system_status["trigger_capture"] = True
    return jsonify({"status": "command_sent"})

@app.route('/api/add_violation', methods=['POST'])
def add_violation():
    try:
        data = request.json
        # Боттан келетін деректер
        violation_type = data.get('violation_type', 'No Helmet')
        image_path = data.get('image_path') # Мысалы: violations/alert_123.jpg
        timestamp = data.get('timestamp')
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        # Деректерді базаға енгізу
        cursor.execute('''
            INSERT INTO violations (timestamp, violation_type, image_path, object_name)
            VALUES (?, ?, ?, ?)
        ''', (timestamp, violation_type, image_path, "Жұмысшы"))
        
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
# --- ЖАҢА: Бот үшін статус тексеру ---
@app.route('/api/get_system_status', methods=['GET'])
def get_status():
    status = system_status.copy()
    system_status["trigger_capture"] = False # Команда бір рет орындалуы үшін
    return jsonify(status)

# Сенің ескі add_violation функцияң (өзгеріссіз)
@app.route('/api/add_violation', methods=['POST'])
def add_violation():
    try:
        data = request.json
        timestamp = data.get('timestamp', datetime.now().strftime("%H:%M:%S"))
        violation_type = data.get('violation_type', 'Unknown')
        image_data = data.get('image')
        object_name = data.get('object_name', 'Worker')
        
        filename = f"violation_{int(datetime.now().timestamp())}.jpg"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        with open(filepath, "wb") as fh:
            fh.write(base64.b64decode(image_data))
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO violations (timestamp, violation_type, image_path, object_name)
            VALUES (?, ?, ?, ?)
        ''', (timestamp, violation_type, f"violations/{filename}", object_name))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'id': cursor.lastrowid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Сенің ескі api/violations функцияң (өзгеріссіз)
@app.route('/api/violations', methods=['GET'])
def get_violations():
    try:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM violations ORDER BY created_at DESC')
        rows = cursor.fetchall()
        violations = [dict(row) for row in rows]
        conn.close()
        return jsonify({'violations': violations, 'total': len(violations)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/violations/<int:violation_id>', methods=['DELETE'])
def delete_violation(violation_id):
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT image_path FROM violations WHERE id = ?', (violation_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute('DELETE FROM violations WHERE id = ?', (violation_id,))
            conn.commit()
            full_path = os.path.join('static', row[0])
            if os.path.exists(full_path):
                os.remove(full_path)
            conn.close()
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)

