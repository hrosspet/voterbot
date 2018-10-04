## Undo all votes of an author added to blacklist
import time
import pandas as pd
from datetime import datetime, timedelta

from steembase.exceptions import PostDoesNotExist
from steem.post import Post

from steevebase.io import steem_factory, mongo_factory
from steevebase.config import CONFIG

TIME_FORMAT = CONFIG['TIME_FORMAT']
CONFIG_DB = CONFIG['DATABASE']
DB_ADDRESS = CONFIG_DB['ADDRESS']


wif = input('Please provide your private active key. This information is stored locally and will not be transmitted elsewhere. ===> \n')

steem = steem_factory(wif=wif)
steemd = steem.steemd

db = mongo_factory(DB_ADDRESS)
raw_posts_col = db.get_collection("raw_posts")

query = {
    'author': 'steem-bot'
}

df_banned_posts = pd.DataFrame([x for x in raw_posts_col.find(query)])

print(df_banned_posts.shape)

# Refresh all posts, if hr1 in voters, unvote
counter = 0

for i in range(df_banned_posts.shape[0]):
    try:
        target = Post(df_banned_posts.iloc[i]['_id'], steemd_instance=steemd)
    except PostDoesNotExist:
        print('Doesnt exist:', df_banned_posts.iloc[i]['_id'])
        continue

    diff = datetime.utcnow() - target['created']
    voters = set()
    hr1_strength = [x['percent'] for x in target.active_votes if x['voter'] == 'hr1']

    if hr1_strength and hr1_strength[0] > 0 and diff < timedelta(days=7):
        target.upvote(-1, 'hr1')
        time.sleep(3)

        print(target['url'])
        counter += 1

print(counter)