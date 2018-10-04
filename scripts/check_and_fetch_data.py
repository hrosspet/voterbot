from steevebase.model.trainer import check_and_fetch_data
from steevebase.io import load_training_config

training_config = load_training_config('training_configs/default_training_setup.json')
check_and_fetch_data(training_config)
