from steem.account import Account
from pymongo import MongoClient
from datetime import datetime, timedelta

from voter.config import CONFIG
from steevebase.io import update_data_db
import steevebase.io as io

CURATOR = 'hr1'

def parse_op(op):
    op['timestamp'] = datetime.strptime(op['timestamp'], '%Y-%m-%dT%H:%M:%S')
    return op


DB_ADDRESS = CONFIG['DATABASE']['ADDRESS']
db = io.mongo_factory(DB_ADDRESS)
monitor_col = db.get_collection("monitor")

steem = io.steem_factory()
acc = Account(CURATOR, steemd_instance=io.steemd_instance)
ops = ['claim_reward_balance', 'transfer_to_vesting', 'fill_vesting_withdraw'] # 'curation_reward'
history = acc.history_reverse(filter_by=ops, batch_size=1000)

for op in history:
    op = parse_op(op)
    # monitor_col.insert_one(op)
    update_data_db(db, monitor_col, op)
