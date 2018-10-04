import logging
import pandas as pd
np = pd.np
from datetime import datetime, timedelta

from steevebase.io import mongo_factory

logger = logging.getLogger(__name__)

class SpamCheck():
    def __init__(self, db_address, col_name=None, init_time_interval_hrs=24, granularity=24):
        self.data_last_updated = datetime.utcnow()

        # fetch posts for init from db
        # init_posts = self._get_init_posts(db_address, col_name, init_time_interval_hrs)
        logger.info('\n\n!!! skipped fetching of posts from last 24hrs for SpamCheck !!!\n')
        init_posts = pd.DataFrame()
        
        # init index and table
        if init_posts.empty:
            logger.info('0 posts in the db in the last 24hrs')
            authors = []
        else:
            authors = init_posts['author'].unique()

        self.spam_index = dict(zip(authors, np.arange(len(authors))))
        self.spam_reverse_index = dict(zip(np.arange(len(authors)), authors))
        self.spam_table = np.zeros((len(authors), granularity))

        if not init_posts.empty:
            # fill table from init posts
            for grp in init_posts.groupby('author'):
                author = grp[0]

                # grp[1] is df
                buckets = grp[1]['created'].apply(lambda x: x.hour).value_counts().to_dict()

                for k,v in buckets.items():
                    self.spam_table[self.spam_index[author], k] = v
    
    def _get_init_posts(self, db_address, col_name, init_time_interval_hrs=24):
        start_time = datetime.utcnow() - timedelta(hours=init_time_interval_hrs)
        time_query = {'$gte': start_time}
        query = {'created': time_query}
        projection = {
            'author': True,
            'created': True
        }

        db = mongo_factory(db_address)
        history_col = db.get_collection(col_name)
        
        init_posts = pd.DataFrame([x for x in history_col.find(query, projection)])
        return init_posts

    def _data_maintenance(self):
        now = datetime.utcnow()
        seconds = now.minute * 60 + now.second
        seconds_since_updated = (now - self.data_last_updated).total_seconds()
        
        if seconds < seconds_since_updated:
            self.data_last_updated = now

            # zero-out the current bucket
            self.spam_table[:, now.hour] = 0

            # delete authors with 0 posts in the last 24hrs
            post_counts = self.spam_table.sum(axis=1)
            self.spam_table = self.spam_table[post_counts > 0, :]

            # delete indexes from reverse index
            filtered_indexes = np.arange(len(self.spam_index))[post_counts > 0]
            # reconstruct authors from filtered indexes
            filtered_authors = [self.spam_reverse_index[x] for x in filtered_indexes]

            # reindex both
            self.spam_index = dict(zip(filtered_authors, np.arange(len(filtered_authors))))
            self.spam_reverse_index = dict(zip(np.arange(len(filtered_authors)), filtered_authors))
        
    def update_author(self, author):
        self._data_maintenance()
        
        if author not in self.spam_index:
            # add to index
            ind = self.spam_table.shape[0]
            self.spam_index[author] = ind
            self.spam_reverse_index[ind] = author
            
            # add new row to table
            self.spam_table = np.concatenate([
                self.spam_table,
                np.zeros((1, self.spam_table.shape[1]))
            ])

        bucket = datetime.utcnow().hour
        self.spam_table[self.spam_index[author], bucket] += 1

    def get_count_24hrs(self, author):
        if author in self.spam_index:
            return self.spam_table[self.spam_index[author]].sum()
        else:
            return 0
