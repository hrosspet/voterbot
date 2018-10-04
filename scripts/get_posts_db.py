import pandas as pd
from datetime import datetime, timedelta
from steevebase.io import save_sequence, mongo_factory

db = mongo_factory(DB_ADDRESS)
raw_posts_col = db.get_collection("raw_posts")

current_irr = 14876926
call_irr = 14829113
start_irr = call_irr - int(1.5 * 24 * 3600 / 3)
end_irr = start_irr - 389 * 1200

now = datetime(2017, 8, 25, 6, 59, 42, 842684)
start_time = now - timedelta(seconds=(current_irr-end_irr)*3)
end_time = now - timedelta(seconds=(current_irr-start_irr)*3)

query = {'created': {'$gt': start_time, '$lt': end_time}}
posts = [x for x in raw_posts_col.find(query)]

save_sequence('posts_2017_25_08.jsonl', posts)
