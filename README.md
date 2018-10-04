# Non python requirements
Mongodb as a database is needed. On a modern linux just install it and use `systemctl start mongodb`.

# Development

0. `git clone https://github.com/hrosspet/voterbot.git`
1. `cd voterbot`
2. `pip install -r requirements.txt`
3. `pip install -e .`

## Running
If installed as above (using `-e` switch), then it is executable under `voterbot` command.

* Getting help: `voterbot <subcommand> --help`, where subcommand is e.g. `downloader` etc.
Leave `<subcommand>` empty to get general help.

## Logging
Logs are saved in the logs/ directory under a unique run id based on the starting time of the run and the current github commit hash:

- `voterbot --loglevel [level]` - where level is the logging level {DEBUG,INFO,WARNING,ERROR,CRITICAL}

### Downloading data
`voterbot downloader` has 4 exclusive options:

- `--stream` - use for streamlined download of newly created posts
- `--post-count [count]` - download last `[count]` main posts (minus `DELAY` defined in config)
- `--block-count [count]` - download all main posts from the last `[count]` blocks (minus `DELAY` defined in config)
- `--days [days]` - to download posts from the last `days` (float) days

Additional parameters:

- `--delay [count]` - set how many blocks the download should be shifted into the past
- `--steem-address [address]` - set the download source. If not specified public nodes will be used
- `--output [name]` - set where the downloaded posts will be stored. If `[name]` has the form of `mongodb://address` the posts are stored to the mongo db on the given address. Otherwise they are appended to the given json lines file.

Examples:
```
voterbot downloader --stream -o mongodb://107.155.87.82:26999
voterbot downloader --block-count 10 -o mongodb://107.155.87.82:26999
voterbot downloader --post-count 10 -o mongodb://107.155.87.82:26999
voterbot downloader --post-count 10 -o new_posts.jsonl
```


### Data wrangling
Data wrangling serves for cleaning of the downloaded posts.

- `--input [filepath/db_address]` - either a jsonl file or a database address. When database used it is possible to specify which posts to wrangle by setting the time interval using either:
    - `--start-time [time]` and/or `--end-time [time]` - the values for these parameters can be found in the `downloader` log.
or:
    - `--days [days]` - to wrangle posts from the last `days` (float) days
- `--keyword [db_column]` - what keyword should the interval query use: {created, last_payout, ...}
- `--black-list [db_address]` - when wrangling posts from input file it is necessary to set the address for the black-list db
- `--output [filepath/db_address]` - json lines file or mongo db address to store the clean posts.

Examples:
```
voterbot wrangler -i new_posts.jsonl --black-list mongodb://107.155.87.82:26999 -o data/data.jsonl
voterbot wrangler -i mongodb://107.155.87.82:26999 --start-time '2017-09-06 08:21:39' --end-time '2017-09-06 08:22:03' -o mongodb://107.155.87.82:26999
voterbot wrangler -i mongodb://107.155.87.82:26999 --start-time '2017-09-06 08:21:39' --keyword last_payout -o data/data.jsonl
voterbot --loglevel INFO wrangler -i mongodb://localhost:26999 --days 1.7 --keyword 'created' -o mongodb://localhost:26999
```
### Data labeling
It is necessary to create the training labels for the posts before you can train a model. Use the following jupyter notebook: `nbs/labeling.ipynb`

### Model training
With downloaded, clean and labeled data it is possible to train a model.

- `--load-model-name [name]` - set if you want to continue training an existing model
- `--save-model-name [name]` - after each training epoch the model is saved under this name
- `--training-config-name [name]` - you can specify your own training config in a xml file

Examples:
```
voterbot trainer
voterbot trainer --training-config-name training_configs/mini_config.json
voterbot --logfile INFO trainer -l model_weights.hdf5
```

### Model selection
`voterbot trainer` produces one model each epoch. You can select the best one using the following jupyter notebook: `nbs/model_selection.ipynb`

### Voter bot
Having selected the best model from all the trained models you can use it for voting.

- `--load-model-name [hdf5_name]` - specify the path to the best model
- `--model-config-name [xml_name]` - specify the properties of the model. Usually it is desirable to use the same settings as in training.
- `--steem-address [address]` - specify the address for communicating with the blockchain. If unspecified the public nodes will be used.
- `--db-address [db_address]` - voting strategy requires tracking of past votes and dynamically reading and updating blacklist in mongo db.

Examples:
```
voterbot voter -l model_weights_001.hdf5
voterbot voter -l model_weights_001.hdf5 -c training_configs/mini_config.json
voterbot voter -l model_weights_001.hdf5 -c training_configs/mini_config.json -p past_vote_times.jsonl
```

# Dockerization
1. build the container `docker build -t steemai .`
2. spin up development environment `docker-compose -f docker-compose.yml -f docker-compose-development.yml up`
3. spin up production environment `docker-compose -f docker-compose.yml -f docker-compose-production.yml up`