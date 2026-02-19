import sqlite3
from datetime import datetime
from pathlib import Path

from .bottle_messages import BottleMessagesDB
from .quotes import Quotes

# DB 文件路径：项目根目录下
_DB_PATH = Path(__file__).parent.parent.parent / "ichika.db"


class DB(BottleMessagesDB, Quotes):
    def __init__(self, db_path: str | Path = _DB_PATH):
        self.conn = sqlite3.connect(str(db_path))
        self.cursor = self.conn.cursor()
        self.create_table()

    def create_table(self):
        """初始化表结构"""
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS bottle_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            group_id INTEGER,
            group_name TEXT,
            text TEXT,
            imgs TEXT,
            time TEXT
        )''')
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_key TEXT,
            group_id INTEGER,
            img TEXT,
            time TEXT
        )''')
        self.conn.commit()

    def insert_data(self, table, **kwargs):
        self.cursor.execute(
            'INSERT INTO {} {} VALUES {}'.format(
                table, str(tuple(kwargs.keys())), str(tuple(kwargs.values()))
            )
        )
        self.conn.commit()

    def fetch_all(self, table):
        self.cursor.execute('SELECT * FROM {}'.format(table))
        return self.cursor.fetchall()

    def fetch_by_id(self, table, where):
        self.cursor.execute('SELECT * FROM {} WHERE {}'.format(table, where))
        return self.cursor.fetchone()

    def delete_data(self, table, where):
        self.cursor.execute('DELETE FROM {} WHERE {}'.format(table, where))
        self.conn.commit()

    @staticmethod
    def datetime2str(time: datetime) -> str:
        return datetime.strftime(time, '%Y-%m-%d %H:%M:%S')

    @staticmethod
    def str2datetime(datetime_str: str) -> datetime:
        return datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')


db = DB()
