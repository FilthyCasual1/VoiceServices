"""Persistent identities and preferences. No Cisco credentials are stored here."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path


class Store:
    def __init__(self, path, accounts=None):
        self.accounts = accounts
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE,
              password TEXT NOT NULL, role TEXT NOT NULL, preferences TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
              csrf TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, owner INTEGER REFERENCES users(id),
              name TEXT NOT NULL, number TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS phones(device TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
              token TEXT UNIQUE NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at INTEGER, user_id INTEGER, action TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_user(self, username, password, role='user'):
        if not username or len(username) > 64 or len(password) < 12 or role not in ('user', 'admin'):
            raise ValueError('Username required; password must contain at least 12 characters.')
        if self.accounts:
            with self.connect() as db:
                if db.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone(): raise sqlite3.IntegrityError('Username already exists')
            self.accounts.call('create',username,password)
            with self.connect() as db: db.execute("INSERT INTO users(username,password,role) VALUES(?,'system',?)",(username,role))
            return
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 310000).hex()
        with self.connect() as db:
            db.execute('INSERT INTO users(username,password,role) VALUES(?,?,?)',
                       (username, salt + ':' + digest, role))

    def login(self, username, password):
        with self.connect() as db:
            user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            if self.accounts:
                try: self.accounts.call('authenticate',username,password)
                except ValueError: return None
                if not user:
                    db.execute("INSERT INTO users(username,password,role) VALUES(?,'system','user')",(username,))
                    user = db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            salt, expected = user['password'].split(':') if user and not self.accounts else ('0'*32, '0'*64)
            actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 310000).hex()
            if (not self.accounts and not hmac.compare_digest(actual, expected)) or not user:
                return None
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token, user['id'], csrf, int(time.time())+28800))
            return token

    def change_password(self, user, current, new):
        if len(new)<12 or len(new)>1024: raise ValueError('Use a password of 12–1024 characters.')
        if self.accounts:
            self.accounts.call('change',user['username'],current,new)
        else:
            proof=self.login(user['username'],current)
            if not proof: raise ValueError('Current password is incorrect.')
            self.logout(proof)
            salt=secrets.token_hex(16)
            digest=hashlib.pbkdf2_hmac('sha256',new.encode(),salt.encode(),310000).hex()
            with self.connect() as db: db.execute('UPDATE users SET password=? WHERE id=?',(salt+':'+digest,user['id']))
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            db.execute('DELETE FROM phones WHERE user_id=?',(user['id'],))

    def session(self, token):
        with self.connect() as db:
            return db.execute('SELECT users.id,username,role,preferences,csrf FROM sessions JOIN users '
                              'ON users.id=sessions.user_id WHERE token=? AND expires>?',
                              (token, int(time.time()))).fetchone()

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (token,))

    def contacts(self, user_id, query=''):
        with self.connect() as db:
            return db.execute('SELECT * FROM contacts WHERE (owner=? OR owner IS NULL) '
                              'AND (name LIKE ? OR number LIKE ?) ORDER BY name',
                              (user_id, '%'+query+'%', '%'+query+'%')).fetchall()

    def add_contact(self, user, name, number, shared=False):
        name, number = name.strip(), number.strip()
        if not name or len(name)>100 or not number or len(number)>40 or any(c not in '+0123456789*#(), -' for c in number):
            raise ValueError('Enter a name and valid dial string.')
        if shared and user['role'] != 'admin':
            raise PermissionError('Shared directory changes require administrator access.')
        with self.connect() as db:
            db.execute('INSERT INTO contacts(owner,name,number) VALUES(?,?,?)',
                       (None if shared else user['id'], name, number))
            db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',
                       (int(time.time()), user['id'], 'Added shared contact' if shared else 'Added personal contact'))

    def preferences(self, user_id, values):
        with self.connect() as db:
            db.execute('UPDATE users SET preferences=? WHERE id=?', (json.dumps(values), user_id))

    def bind_phone(self, user, device):
        if not device.startswith('SEP') or len(device) != 15 or any(c not in '0123456789ABCDEF' for c in device[3:]):
            raise ValueError('Use a device name such as SEP001122AABBCC.')
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            # One active application terminal per user; never preserve the old token.
            db.execute('DELETE FROM phones WHERE user_id=? OR device=?', (user['id'], device))
            db.execute('INSERT INTO phones VALUES(?,?,?,?)', (device, user['id'], token, int(time.time())+28800))
        return token

    def phone_user(self, token):
        with self.connect() as db:
            return db.execute('SELECT users.id,username,role,preferences FROM phones JOIN users '
                              'ON users.id=phones.user_id WHERE token=? AND expires>?',
                              (token, int(time.time()))).fetchone()

    def unbind_phone(self, user_id):
        with self.connect() as db:
            db.execute('DELETE FROM phones WHERE user_id=?', (user_id,))


def calculate(left, operation, right):
    if len(left)>60 or len(right)>60:
        raise ValueError('Number too long.')
    try:
        a, b = Decimal(left), Decimal(right)
        if not a.is_finite() or not b.is_finite() or abs(a.as_tuple().exponent)>100 or abs(b.as_tuple().exponent)>100 or abs(a)>Decimal('1e30') or abs(b)>Decimal('1e30'):
            raise ValueError('Use finite numbers up to 1e30.')
        with localcontext() as ctx:
            ctx.prec = 32
            if operation == 'add': result = a+b
            elif operation == 'subtract': result = a-b
            elif operation == 'multiply': result = a*b
            elif operation == 'divide':
                if b == 0: raise ValueError('Cannot divide by zero.')
                result = a/b
            else: raise ValueError('Unknown operation.')
        return format(result, 'g')
    except InvalidOperation as exc:
        raise ValueError('Enter valid numbers.') from exc
