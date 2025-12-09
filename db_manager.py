import sqlite3
import datetime

class DatabaseManager:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.init_db()

    def init_db(self):
        self.cursor.execute("PRAGMA foreign_keys = ON;")
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS buildings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                building_id INTEGER NOT NULL,
                FOREIGN KEY (building_id) REFERENCES buildings(id) ON DELETE CASCADE
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS problem_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                room_id INTEGER NOT NULL,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp TEXT,
                building_id INTEGER,
                room_id INTEGER,
                problem_type_id INTEGER,
                problem_details TEXT,
                name TEXT,
                position TEXT,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (building_id) REFERENCES buildings(id),
                FOREIGN KEY (room_id) REFERENCES rooms(id),
                FOREIGN KEY (problem_type_id) REFERENCES problem_types(id)
            )
        ''')
        self.conn.commit()

    # --- Методы для управления структурой ---
    def add_item(self, table_name, **kwargs):
        keys = ', '.join(kwargs.keys())
        values = ', '.join(['?'] * len(kwargs))
        sql = f"INSERT INTO {table_name} ({keys}) VALUES ({values})"
        self.cursor.execute(sql, tuple(kwargs.values()))
        self.conn.commit()

    def get_items(self, table_name, order_by='name', **kwargs):
        sql = f"SELECT * FROM {table_name}"
        if kwargs:
            keys = ' AND '.join([f"{key} = ?" for key in kwargs.keys()])
            sql += f" WHERE {keys}"
        sql += f" ORDER BY {order_by}"
        self.cursor.execute(sql, tuple(kwargs.values()))
        return self.cursor.fetchall()
        
    def get_item_by_id(self, table_name, item_id):
        self.cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (item_id,))
        return self.cursor.fetchone()

    def delete_item_by_id(self, table_name, item_id):
        if table_name in ['buildings', 'rooms', 'problem_types']:
            self.cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (item_id,))
            self.conn.commit()
    
    # --- Методы для работы с заявками ---
    def add_request(self, data):
        sql = '''INSERT INTO requests (user_id, timestamp, building_id, room_id, problem_type_id, problem_details, name, position)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
        self.cursor.execute(sql, (
            data['user_id'], data['timestamp'], data['building_id'], data['room_id'],
            data['problem_type_id'], data['problem_details'], data['name'], data['position']
        ))
        self.conn.commit()

    def get_requests(self, status='active'):
        order = "ASC" if status == 'active' else "DESC"
        sql = f"""
            SELECT
                r.id, r.timestamp, r.problem_details, r.name, r.position, r.status,
                b.name as building_name,
                rm.name as room_name,
                pt.name as problem_type_name
            FROM requests r
            LEFT JOIN buildings b ON r.building_id = b.id
            LEFT JOIN rooms rm ON r.room_id = rm.id
            LEFT JOIN problem_types pt ON r.problem_type_id = pt.id
            WHERE r.status = ?
            ORDER BY r.id {order}
        """
        self.cursor.execute(sql, (status,))
        return self.cursor.fetchall()
    
    def archive_request_by_id(self, request_id):
        self.cursor.execute("UPDATE requests SET status='archived' WHERE id=?", (request_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def archive_all_active(self):
        self.cursor.execute("UPDATE requests SET status='archived' WHERE status='active'")
        count = self.cursor.rowcount
        self.conn.commit()
        return count

    def close(self):
        self.conn.close()