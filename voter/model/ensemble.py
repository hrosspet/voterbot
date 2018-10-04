
# coding: utf-8

# In[1]:


import logging

import numpy as np
np.random.seed(1337)  # for reproducibility, needs to be before importing keras

from keras.layers import (LSTM, AtrousConvolution1D, Convolution1D, Dropout,
                          Input, MaxPooling1D, concatenate, Dense)
from keras.models import Model
from keras.optimizers import Adam

def apply_shared(shared, inp):
    res = inp
    for layer in shared:
        res = layer(res)
    return res


# In[2]:


from steevebase.io import load_training_config
from steevebase.model import models

training_config = load_training_config('training_configs/default_training_setup.json')

ensemble_models = []
ensemble_model_weights = [
    'model_weights_2017_08_30.hdf5',
    'model_weights_2017_10_26.hdf5',
    'model_weights_2017_11_13.hdf5',
    'model_weights_2017_11_27.hdf5',
    'model_weights_2017_12_17.hdf5',
    'training_2018_01_04/second_part/model_weights_454.hdf5'
]

for load_model_name in ensemble_model_weights:
    m = models.create_cnn_class(training_config)
    m.load_weights(load_model_name)
    ensemble_models.append(m)


# In[5]:


DATA_CONFIG = training_config['DATA']

TR_CONFIG = training_config['TRAINING']
LR = TR_CONFIG['LR']
LOSS = TR_CONFIG['LOSS']

MAX_SEQ_LEN = DATA_CONFIG['MAX_SEQ_LEN']
EMBEDDING_SIZE = len(DATA_CONFIG['ALPHABET']) + 1

main_input = Input(shape=(MAX_SEQ_LEN, EMBEDDING_SIZE), name="main_input")
ensemble_model_outputs = []

for i, m in enumerate(ensemble_models):
#     for l in m.layers:
#         print(l)
    m.layers[-1].name += '_' + str(i)
    
    for layer in m.layers:
        layer.trainable = False

    ensemble_model_outputs.append(apply_shared(m.layers[1:], main_input))
    
merged_models = concatenate(ensemble_model_outputs)
classification = Dense(2, activation='sigmoid', name='classification')(merged_models)

model = Model(inputs=[main_input], outputs=[classification])

optim = Adam(lr=LR)

model.compile(loss=LOSS,
              optimizer=optim,
              metrics=['mean_absolute_error'])
model.summary()


# In[6]:


from steevebase.model.trainer import get_generators, get_callbacks, sort_test

# training_config = load_training_config('training_configs/default_training_setup.json')
# training_config['DATA']['INPUT_DATA_NAME'] = '../' + training_config['DATA']['INPUT_DATA_NAME']

save_model_name = 'model_weights'

STEPS_PER_EPOCH = TR_CONFIG['STEPS_PER_EPOCH']
EPOCHS = TR_CONFIG['EPOCHS']
CLASS_WEIGHT = TR_CONFIG['CLASS_WEIGHT']

train_generator, test_generator = get_generators(training_config)
test_set = sort_test(test_generator)

callbacks = get_callbacks(test_set, model, save_model_name, training_config)

# logger.info('Train...')
model.fit_generator(
    train_generator,
    steps_per_epoch=STEPS_PER_EPOCH,
    epochs=EPOCHS,
    callbacks=callbacks,
    validation_data=test_set if TR_CONFIG['SAVE_BEST_ONLY'] else None,
    class_weight=CLASS_WEIGHT,
    max_q_size=STEPS_PER_EPOCH,
    workers=4,
    pickle_safe=True)

