from datetime import datetime, timedelta
from voter.config import CONFIG
from steevebase.io import mongo_factory

DAYS_KEEP_POSTS = CONFIG['DATA']['LIMITS']['NR_DAYS_KEEP_POST']

CONFIG_DB = CONFIG['DATABASE']
DB_ADDRESS = CONFIG_DB['ADDRESS']
POST_RECO_COL_NAME = CONFIG_DB['POST_RECO_COLLECTION_NAME']


def drop_old_posts(post_recos_col):
    start_time = datetime.utcnow() - timedelta(days=DAYS_KEEP_POSTS)
    post_recos_col.remove({"created": {"$lt": start_time}})


db = mongo_factory(DB_ADDRESS)
post_recos_col = db.get_collection(POST_RECO_COL_NAME)

drop_old_posts(post_recos_col)

