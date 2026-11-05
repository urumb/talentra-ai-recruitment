"""Create users: python -m app.manage create-user EMAIL ROLE ORG   (ROLE: RECRUITER | CLIENT | DELIVERY_HEAD). Password is read from the TALENTRA_PASSWORD env var or prompted."""
import os, sys, uuid, getpass
from app.main import SessionLocal, User, hash_password

def main(argv):
    if len(argv) != 5 or argv[1] != 'create-user' or argv[3] not in ('RECRUITER', 'CLIENT', 'DELIVERY_HEAD'):
        print(__doc__); return 2
    pw = os.getenv('TALENTRA_PASSWORD') or getpass.getpass('Password (min 10 chars): ')
    if len(pw) < 10: print('Password too short'); return 1
    d = SessionLocal()
    if d.query(User).filter_by(email=argv[2].lower()).first(): print('User already exists'); return 1
    d.add(User(id=str(uuid.uuid4()), email=argv[2].lower(), role=argv[3], org=argv[4], password_hash=hash_password(pw))); d.commit(); print('Created', argv[2]); return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
