"""Run from the project root: python tools/import_pila_hotlines.py --actor-id ID."""
from pathlib import Path
import sys,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.extensions import db
from app.models import User
from app.incidents.pila_contacts import import_pila_contacts

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--actor-id',required=True,type=int);args=parser.parse_args()
    app=create_app()
    with app.app_context():
        actor=db.session.get(User,args.actor_id)
        if not actor: parser.error('Administrator account does not exist.')
        changed=import_pila_contacts(actor);db.session.commit()
        print(f'Published {changed} Pila directory contacts; existing entries retained. No calls placed.')
