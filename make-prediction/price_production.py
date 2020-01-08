# -*- coding: utf-8 -*-
"""price_bayer.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1c-0G7-xSPi02wJNV-ELNULONsOlewfAw
"""

# -*- coding: utf-8 -*-
# region Import
# Data download
# Import basic
import csv
import math
import os
import warnings
# Init google drive
# from google.colab import drive
from datetime import datetime
from timeit import default_timer as timer

import numpy as np
import pandas as pd
# Plottool
import plotly.graph_objs as go
# Hyperopt bayesian optimization
from hyperopt import hp, Trials, tpe, fmin, STATUS_OK, partial
# Keras
import tensorflow as tf
import tensorflow 
from tensorflow.keras import Sequential
from tensorflow.keras import optimizers
from tensorflow.keras.activations import softmax
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint  
from tensorflow.keras.initializers import random_normal, Ones 
from tensorflow.keras.layers import LSTM, Dropout, Input, Dense
from tensorflow.keras.models import Model
from tensorflow.keras.models import load_model
import tensorflow.keras.backend as K
# SKLearn
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
# Yfinance
import yfinance as yf

import pandas_market_calendars as mcal

import joblib
# Hyperopt bayesian optimization
from hyperopt import hp, Trials, tpe, fmin, STATUS_OK, partial

import json

# endregion

# Region config config
try:
  from google.colab import drive
  IN_COLAB = True
except:
  IN_COLAB = False

config = {}
config['current_timestamp'] = datetime.now().strftime('%d%m%Y_%H%M%S')

config['root_dir'] = "./../result"


config['data_dir'] ="./../data"
config['model_dir'] = os.path.join(config['root_dir'], 'model')
config['plot_dir'] = os.path.join(config['root_dir'], 'plot')
config['prediction_dir'] = os.path.join(config['root_dir'], 'prediction')
config['test_dir'] = os.path.join(config['root_dir'], 'test')

config['input_col'] = ['<Close>', '<Open>', '<High>', '<Low>']
config['output_col'] = ['<Close>']
config['time_col'] = ['<DTYYYYMMDD>']
config['prediction_col'] = 'Prediction'
# Number of session to prediction as one time
config['prediction_size'] = 1
# For each time model is train, the first is display
config['sample_display_test_size'] = 5
# windows size
config['windows_size'] = 5
# split config
config['train_split'] = 0.8
config['validation_split'] = 0

config['test_method'] = 'number'
config['test_days'] = 90

config['test_method'] = 'split'
config['test_split'] = 0.1

# model config
config['lstm_neuron_count'] = 128
config['lstm_layer_count'] = 5
config['drop_rate'] = 0.1
config['stateful'] = False

# data normalize
config['scaler_feature_range'] = (-1, 1)

# train
config['epochs'] = 300
config['batch_size'] = 32
config['train_verbose'] = 1
config['start_time'] = datetime(2006, 1, 1, 0, 0)
config['end_time'] = datetime(2016, 11, 13, 0, 0) 
config['force_train'] = False

# bayesian
config['param_grid'] = {
        'windows_size': hp.quniform('windows_size', 1, 8, 1),
        'drop_rate': hp.lognormal('drop_rate', np.log(0.04), 1),
        'lstm_layer_count' : hp.quniform('lstm_layer_count', 3, 7, 1),
        'lstm_neuron_count' :  hp.quniform('lstm_neuron_count', 32, 512, 32)
    }
    
config['bayer_max_evals'] = 50

pd.options.display.max_columns = 12
pd.options.display.max_rows = 24

# disable warnings in Anaconda
warnings.filterwarnings('ignore')

# endregion

# region Data Loading

def get_all_stock_name_in_dir(dir):
    file_list = []
    for file in os.listdir(dir):
        if file.endswith(".csv"):
            file_list.append(file.partition('.')[0])

    return file_list

    
def get_data(config, stock_file_name = '000002.SS'):
    data_dir = config['data_dir']
    start_time = config['start_time']
    end_time = config['end_time']
    time_col = config['time_col']
    time_col = time_col[0]
    data_file_path = f'{data_dir}/{stock_file_name}.csv'

    if os.path.exists(data_file_path):
        df_org = pd.read_csv(data_file_path, parse_dates=[time_col])
        df_org = df_org.sort_values('<DTYYYYMMDD>')
        df_org = df_org.set_index('<DTYYYYMMDD>')
        df_org = df_org.tz_localize(None)

        # Do fill missing day
        stock_calendar = mcal.get_calendar('stock')
        stock_time = stock_calendar.valid_days(start_date=df_org.index.values[0], end_date=df_org.index.values[-1])
        stock_time.tz_localize(None)
        df_time = pd.DataFrame((stock_time), columns=['<DTYYYYMMDD>'])
        df_time = df_time.sort_values('<DTYYYYMMDD>')
        df_time = df_time.set_index('<DTYYYYMMDD>')
        df_time = df_time.tz_convert(None)

        df_org = df_org.join(df_time, how='right')
        df_org = df_org.fillna(method='backfill')
        # df_org = df_org[np.logical_and(df_org[time_col].dt.to_pydatetime() >= config['start_time'], df_org[time_col].dt.to_pydatetime() <= config['end_time'])]
    else:
        return None


    df_org = df_org.sort_values(time_col)
    df_org.reset_index(inplace=True)

    return df_org

def calculate_change(df, target_col_name = 'Close', change_col_name = 'Change'):
    df_change = df[target_col_name].copy()
    df_change = df_change.pct_change(periods=1, fill_method='ffill')
    df_change = df_change.fillna(0)

    df[change_col_name] = df_change

    return df

# region Data ploting
def plot_ohlc(df, stock_name):
    trace = go.Ohlc(x=df['<DTYYYYMMDD>'],
                    open=df['<Open>'],
                    high=df['<High>'],
                    low=df['<Low>'],
                    close=df['<Close>'],
                    increasing=dict(line=dict(color='#58FA58')),
                    decreasing=dict(line=dict(color='#FA5858')))

    layout = {
        'title': f'{stock_name} Historical Price',
        'xaxis': {'title': 'Date',
                  'rangeslider': {'visible': False}},
        'yaxis': {'title': f'Price'}
    }

    data = [trace]

    fig = go.Figure(data=data, layout=layout)
    fig.show()
    return fig

def get_df_intersect_col(df, col_list):
    return np.intersect1d(df.columns.values, col_list, assume_unique=True)

# endregion

# region Declare model
# declare model
def none_to_default(value, value_if_fall):
    try:
        return value_if_fall if value is None else value
    except:
        return value_if_fall

def softmax_axis1(x):
    return softmax(x, axis=1)


def get_model(config = config):
    input_dim = config['input_dim']
    windows_size = config['windows_size']
    output_dim = config['output_dim']
    lstm_neuron_count = none_to_default(config['lstm_neuron_count'], 128)
    lstm_layer_count = none_to_default(config['lstm_layer_count'], 5)
    drop_rate = none_to_default(config['drop_rate'], 0.2)
    stateful = none_to_default(config['stateful'], False)
    batch_size = config['batch_size']
    model = Sequential()
    
    if stateful:
      model.add(LSTM(units=lstm_neuron_count, batch_input_shape=(batch_size, windows_size, input_dim), activation='relu', return_sequences=True, stateful = stateful))
    else:
      model.add(LSTM(units=lstm_neuron_count, input_shape=(windows_size, input_dim), activation='relu', return_sequences=True, stateful = stateful))

    for i in range(lstm_layer_count - 2):
        model.add(LSTM(units=lstm_neuron_count, return_sequences=True, activation='relu', stateful = stateful))
     
    model.add(LSTM(units=lstm_neuron_count, return_sequences=False, activation='relu', stateful = stateful))
    model.add(Dropout(rate=drop_rate))
    model.add(Dense(output_dim, activation='linear'))
    softmax_activation = softmax_axis1
    model.compile(loss='MSE', optimizer='adam')
    
    return model


# endregion

# region Error metric
def mean_absolute_percentage_error(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)

    return np.mean(np.abs((y_true - y_pred) / y_true)) * 100

def root_mean_square_error(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)

    return np.mean((y_true - y_pred) / y_true)


def relative_root_mean_square_error(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    res = (y_true - y_pred) / y_true
    res = np.power(res, 2)
    res = np.mean(res)
    res = math.sqrt(res)

    return res


# endregion

# region Data preprocessing
# reprocessing data
def next_window(df, i, config = config):
    windows_size = config['windows_size']
    prediction_size = config['prediction_size']
    input_col = config['input_col']
    output_col = config['output_col']
    time_col = config['time_col']

    '''Generates the next data window from the given index location i'''
    window = df[i: i + windows_size + prediction_size]
    x = window[input_col][:-prediction_size]
    y = window[output_col][-prediction_size:]
    y_time = window[time_col][-prediction_size:]
    return x, y, y_time

def smooting_data(df, config = config):
    windows_size = config['windows_size']
    return df.ewm(span=windows_size).mean()

def preprocessing_data(df, config = config):
    '''
    Create x, y train data windows
    Warning: batch method, not generative, make sure you have enough memory 
    '''
    windows_size = config['windows_size']
    prediction_size = config['prediction_size']
    input_col = config['input_col']
    output_col = config['output_col']
    time_col = config['time_col']

    data_x = []
    data_y = []
    data_y_time = []
    for i in range(len(df) - windows_size - prediction_size):
        x, y, y_time = next_window(df, i, config)
        data_x.append(x.values)
        data_y.append(y.values)
        data_y_time.append(y_time)

    time = pd.concat(data_y_time)

    return np.array(data_x), np.array(data_y), time.values

# endregion

# region Model train
# Trainning model
def train_model(model, X_train, y_train, save_fname):
    model_save_checkpoint_fname = os.path.join(config['model_dir'], '%s-e{epoch:02d}.h5' % (save_fname))
    callbacks = [
        # EarlyStopping(monitor='loss', patience=100)
    ]
    epochs = none_to_default(config['epochs'], 1000)
    batch_size = none_to_default(config['batch_size'], 1000)
    train_split = none_to_default(config['train_split'], 0.7)
    validation_split = none_to_default(config['validation_split'], 0.1)
    save_model = config.get('save_model', True)
    train_verbose = config.get('train_verbose', 1)
    # if save_model:
        # callbacks.append(ModelCheckpoint(filepath=model_save_checkpoint_fname, monitor='loss', save_best_only=True))
        
    history = model.fit(
        X_train,
        y_train,
        epochs=epochs,
        batch_size=batch_size,
        validation_split= float(validation_split) / float(train_split),
        verbose=train_verbose,
        callbacks=callbacks,
        shuffle=False)

    if save_model:
        model_save_fname = os.path.join(config['model_dir'], '%s.h5' % (save_fname))
        model.save(model_save_fname)
    
    return history

def load_save_model(stock_name, config):
    model_save_fname = os.path.join(config['model_dir'], '%s.h5' % (stock_name))
    scaler_save_fname = os.path.join(config['model_dir'], '%s.scaler' % (stock_name))
    
    if os.path.exists(model_save_fname) and os.path.exists(scaler_save_fname):
        return {'model' : load_model(model_save_fname), 'scaler': joblib.load(scaler_save_fname)}
        
    return None

# endregion

def plot_test_result(df_test_result, stock_name, config):
    # Plotly
    output_col = config['output_col']
    prediction_col = config['prediction_col']
    time_col = config['time_col']
    trace0 = go.Scatter(
        x=df_test_result.index,
        y=df_test_result[output_col[0]],
        name='Thực tế',
        line=dict(
            color=('#5042f4'),
            width=2)
    )

    trace1 = go.Scatter(
        x=df_test_result.index,
        y=df_test_result[prediction_col],
        name='Dự đoán',
        line=dict(
            color=('#005b4e'),
            width=2,
            dash='dot'
        )  # dash options include 'dash', 'dot', and 'dashdot'
    )

    data = [trace0, trace1]

    # Edit the layout
    layout = dict(title='Biểu đồ dự đoán',
                  xaxis=dict(title='Date'),
                  yaxis=dict(title='Price'),
                  paper_bgcolor='#FFF9F5',
                  plot_bgcolor='#FFF9F5'
                  )

    fig = go.Figure(data=data, layout=layout)
    plot_dir = config['plot_dir']
    fig.write_html(os.path.join(plot_dir, '%s_test.html' % (stock_name)), auto_open=False)
# endregion

# Region do main thing
def do_train(stock_name, df, config = config): 
    result = {}
    
    df_train = df

    input_col = get_df_intersect_col(df, config['input_col'])
    output_col = get_df_intersect_col(df, config['output_col'])
    time_col = get_df_intersect_col(df, config['time_col'])
    
    config['input_col'] = input_col
    config['output_col'] = output_col
    config['time_col'] = time_col
    time_col = time_col[0]
    config['input_dim'] = len(input_col)
    config['output_dim'] = len(output_col)
    

    
    model = get_model(config=config)
    
    start = timer()

    # Handle data
    scaler_feature_range = config.get('scaler_feature_range', (0, 1))
    scaler = MinMaxScaler(feature_range=scaler_feature_range)
    scaled_cols = scaler.fit(df_train[input_col])

    # Save scaler
    scaler_save_fname = os.path.join(config['model_dir'], '%s.scaler' % (stock_name))
    joblib.dump(scaler, scaler_save_fname) 
    
    # Transform train data
    scaled_cols = scaler.transform(df_train[input_col])
    df_train[input_col] = scaled_cols

    X_train, y_train, time_train = preprocessing_data(df_train, config)

    # Reshape data
    y_train = y_train.reshape((y_train.shape[0], y_train.shape[1]))

    # Perform n_train
    history = train_model(model, X_train, y_train, stock_name)
    
    run_time = timer() - start

    # Save last train time
    last_train_time_path = os.path.join(config['model_dir'], '%s_last_train.txt' % (stock_name))
    joblib.dump(df_train[time_col][-1:].values[0], last_train_time_path)

    return {'scaler' : scaler, 'model' : model, 'history' : history, 'run_time' : run_time} 
    # %%
def do_test(stock_name, df, data, config = config):

    prediction_size = config['prediction_size']
    input_col =  config['input_col']
    output_col =  config['output_col']
    time_col =  config['time_col']
    batch_size =  config['batch_size']
    prediction_col = config['prediction_col']
    output_col = output_col[0]
    time_col =  time_col[0]
    
    df_org = df.copy()
    df_test = df
    scaler = data['scaler']
    scaled_cols = scaler.transform(df_test[input_col])
    df_test[input_col] = scaled_cols

    X_test, y_test, time_test = preprocessing_data(df_test, config)
    
    # Reshape data
    y_test = y_test.reshape((y_test.shape[0], y_test.shape[1]))

    # Test generated loss
    model = data['model']
    y_pred = model.predict(X_test)
    y_pred = np.repeat(y_pred, len(input_col), axis=1)
    y_pred = scaler.inverse_transform(y_pred)[:, [0]]
    y_pred = pd.Series(y_pred.flatten())

    df_test_result = pd.DataFrame(time_test, columns=[time_col])
    df_test_result[config['prediction_col']] = y_pred
    df_test_result.set_index(time_col, inplace=True)

    df_test_result = df_test_result.join(df_org.set_index(time_col))


    score = model.evaluate(X_test, y_test, batch_size, 1)
    mae = mean_absolute_error(df_test_result[output_col], df_test_result[prediction_col])
    mse = mean_squared_error(df_test_result[output_col], df_test_result[prediction_col])
    mape = mean_absolute_percentage_error(df_test_result[output_col], df_test_result[prediction_col])
    rrmse = relative_root_mean_square_error(df_test_result[output_col], df_test_result[prediction_col])

    # File to save first results\n
    result_dir = config['test_dir']
    result_save_fname = os.path.join(result_dir, 'result_%s.csv' % (stock_name))
    of_connection = open(result_save_fname, 'w')
    writer = csv.writer(of_connection)
    # Write the headers to the file\n
    writer.writerow(['stock_name', 'score', 'mae', 'mse', 'mape', 'rrmse', 'time_stamp'])
    writer.writerow([stock_name, score, mae, mse, mape, rrmse, datetime.now().strftime('%d%m%Y_%H%M%S')])
    of_connection.close()
    # write data
    return  {'score' : score, 'mae' : mae, 'df': df_test_result, 'mse' : mse, 'mape' : mape, 'rrmse' : rrmse}

def do_train_untrain(stock_name, df, data, config = config):

    prediction_size = config['prediction_size']
    input_col =  config['input_col']
    output_col =  config['output_col']
    time_col =  config['time_col']
    batch_size =  config['batch_size']
    output_col = output_col[0]
    time_col =  time_col[0]
    
    df_train = df
    scaler = data['scaler']
    scaled_cols = scaler.transform(df_train[input_col])
    df_train[input_col] = scaled_cols

    X_train, y_train, time_train = preprocessing_data(df_train, config)
    
    # Reshape data
    y_train = y_train.reshape((y_train.shape[0], y_train.shape[1]))

    # Perform n_train
    model = data['model']
    history = train_model(model, X_train, y_train, stock_name)
    
    # Save last train time
    last_train_time_path = os.path.join(config['model_dir'], '%s_last_train.txt' % (stock_name))
    joblib.dump(df_train[time_col][-1:].values[0], last_train_time_path)

  

def make_future_prediction(stock_name,  df, model, scaler, future_step, config):
    windows_size = config['windows_size']
    input_col = config['input_col']
    output_col = config['output_col']
    time_col = config['time_col']
    prediction_col = config['prediction_col']

    time_col = time_col[0]
    prediction_size = config['prediction_size']
    batch_size = config['batch_size']

    stock_calendar = mcal.get_calendar('stock')
    time = df[time_col][-1:].values[0]
    stock_time = stock_calendar.valid_days(start_date=time + np.timedelta64(1, 'D'), end_date=time + np.timedelta64(future_step * 2, 'D'))
    
    pred_res = df[input_col][-windows_size:].copy()
    pred_res[prediction_col] = pred_res[output_col]
    '''Generates the next data window from the given index location i'''
    for step in range(future_step):
        x = pred_res[input_col][-windows_size:].values
        x = scaler.transform(x)
        x = x.reshape(1, x.shape[0], x.shape[1])

        y_pred = model.predict(x)
        y_pred = np.repeat(y_pred, len(input_col), axis=1)
        y_pred = scaler.inverse_transform(y_pred)[:, [0]][0][0]

        data_row = {time_col : stock_time[step], prediction_col:y_pred}
        for input_col_name in input_col:
          data_row[input_col_name] = y_pred

        pred_res = pred_res.append(data_row, ignore_index=True )

    return pred_res[windows_size:]

def plot_furure_prediction(df, df_predict, stock_name, config):
    # Plotly
    df = df[-10:]
    output_col = config['output_col']
    prediction_col = config['prediction_col']
    time_col = config['time_col']
    time_col = time_col[0]
    trace0 = go.Scatter(
        x=df[time_col],
        y=df[output_col[0]],
        name='Thực tế',
        line=dict(
            color=('#5042f4'),
            width=2)
    )

    trace1 = go.Scatter(
        x=df_predict[time_col],
        y=df_predict[prediction_col],
        name='Dự đoán',
        line=dict(
            color=('#005b4e'),
            width=2,
            dash='dot'
        )  # dash options include 'dash', 'dot', and 'dashdot'
    )

    data = [trace0, trace1]

    # Edit the layout
    layout = dict(title='Biểu đồ dự đoán',
                  xaxis=dict(title='Date'),
                  yaxis=dict(title='Price'),
                  paper_bgcolor='#FFF9F5',
                  plot_bgcolor='#FFF9F5'
                  )

    fig = go.Figure(data=data, layout=layout)
    plot_dir = config["plot_dir"]
    fig.write_html(os.path.join(plot_dir, '%s_predict.html' % (stock_name)), auto_open=False)
# endregion

# Hyper parameter tuning
def objective(params, df):
    # Make sure windows_size is int
    config['windows_size'] = int(params['windows_size'])
    config['drop_rate'] = min((params['drop_rate'], 0.7))
    config['lstm_layer_count'] = int(params['lstm_layer_count'])
    config['lstm_neuron_count'] = int(params['lstm_neuron_count'])
    test_split = config.get('test_split')
    input_col = config['input_col']
    output_col = config['output_col']
    time_col = config['time_col']

    df_train, df_test = train_test_split(df, test_size=test_split, shuffle=False)
    model = get_model(config=config)
    
    start = timer()

    # Handle data
    scaler_feature_range = config.get('scaler_feature_range', (0, 1))
    scaler = MinMaxScaler(feature_range=scaler_feature_range)
    scaled_cols = scaler.fit(df_train[input_col])
    
    # Transform train data
    scaled_cols = scaler.transform(df_train[input_col])
    df_train[input_col] = scaled_cols

    X_train, y_train, time_train = preprocessing_data(df_train, config)

    # Reshape data
    y_train = y_train.reshape((y_train.shape[0], y_train.shape[1]))

    # Perform n_train
    history = train_model(model, X_train, y_train, 'none')
    
    run_time = timer() - start


    # Transform test data
    scaled_cols = scaler.transform(df_test[input_col])
    df_test[input_col] = scaled_cols

    X_test, y_test, time_train = preprocessing_data(df_test, config)

    # Reshape data
    y_test = y_test.reshape((y_test.shape[0], y_test.shape[1]))

    score = model.evaluate(X_test, y_test, 10000, 8)
    loss = score

    # Dictionary with information for evaluation
    return {'loss': loss, 'params': params,
            'train_time': run_time, 'status': STATUS_OK}

def config_column(df, config):
    input_col = get_df_intersect_col(df, config['input_col'])
    output_col = get_df_intersect_col(df, config['output_col'])
    time_col = get_df_intersect_col(df, config['time_col'])
    
    config['input_col'] = input_col
    config['output_col'] = output_col
    config['time_col'] = time_col
    config['input_dim'] = len(input_col)
    config['output_dim'] = len(output_col)

def load_hyper_parameter(stock_name, config):
    param_file_path = os.path.join(config['model_dir'], '%s_param.txt' % (stock_name))
    if os.path.exists(param_file_path):
        with open(param_file_path, 'r') as outfile:
            b = json.load(outfile)
            return b
    else:
        return None

def tune_hyper_parameter(stock_name, df, config):
    # Get last 365 day for tuning
    df=df[-365:]
    bayer_max_evals = config.get('bayer_max_evals', 1000)
    param_grid = config.get('param_grid')

    # Hyperparameter grid
    bayes_trials = Trials()

    # Create the algorithm
    bayes_algo = tpe.suggest

    fmin_objective = partial(objective, df=df)

    bayes_best = fmin(fn=fmin_objective, space=param_grid,
                      algo=bayes_algo, trials=bayes_trials,
                      max_evals=bayer_max_evals)

    param_file_path = os.path.join(config['model_dir'], '%s_param.txt' % (stock_name))
    with open(param_file_path, 'w') as outfile:
        json.dump(bayes_best, outfile)

# Make future frame For 6 year, 3 year, 1 year, 1 month.

# Hyperparameter Tuning
#   + Train / test split valdiation
#   + Droprate
#   + Activation
#   + Number of layer

# Agents 
# Stock List
def do_main(stock_name, config):
    print(f'{stock_name}')
    force_train = config.get('force_train', False)
    test_method = config.get('test_method', 'split')
    time_col = config.get('time_col')
    time_col = time_col[0]

    df = get_data(config, stock_name)
    if df is None:
        print(f'{stock_name} no data found. skipped')

    config_column(df, config)

    parameter = load_hyper_parameter(stock_name, config)
    if parameter is None:
        print(f'{stock_name} no parameter found. skipped')
        return

    print(f'{stock_name} load parameter')


    config['windows_size'] = int(parameter['windows_size'])
    config['drop_rate'] = min((parameter['drop_rate'], 0.7))
    config['lstm_layer_count'] = int(parameter['lstm_layer_count'])
    config['lstm_neuron_count'] = int(parameter['lstm_neuron_count'])


    config['save_model'] = True
    train_result = load_save_model(stock_name, config)
    if train_result is None or force_train:
        print(f'{stock_name} no model found. skipped')
    else:
        print(f'{stock_name} : load model')
        windows_size = config.get('windows_size')
        last_train_time_path = os.path.join(config['model_dir'], '%s_last_train.txt' % (stock_name))
        last_train_time = joblib.load(last_train_time_path)
        untrain_data = df[df[time_col] > last_train_time]
        if untrain_data.shape[0] > 0:
          print(f'{stock_name} : train new data')
          do_train_untrain(stock_name, untrain_data.copy(), train_result ,config)
        
        train_result = load_save_model(stock_name, config)
        
        print(f'{stock_name} :  make prediction')
        future_predict = make_future_prediction(stock_name, df.copy(), train_result['model'], train_result['scaler'] ,10, config)
        plot_furure_prediction(df, future_predict, stock_name, config)

        result_dir = config['prediction_dir']
        future_pred_file_path = f'{result_dir}/{stock_name}.csv'
        future_predict.to_csv(future_pred_file_path)
        
        print(f'{stock_name} :  save prediction')
        print(f'{stock_name} :  complete')
        K.clear_session()
        del df


stock_name_list = get_all_stock_name_in_dir(config['data_dir'])
for stock_name in stock_name_list:
  do_main(stock_name, config)