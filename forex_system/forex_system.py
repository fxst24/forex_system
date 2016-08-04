# coding: utf-8

import argparse
import configparser
import importlib
import matplotlib.pyplot as plt
import numpy as np
import oandapy
import os
import pandas as pd
import shutil
import smtplib
import struct
import time

from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
from email.mime.text import MIMEText
from numba import float64, int64, jit
from scipy import optimize
from sklearn.externals import joblib

# Spyderのバグ（？）で警告が出るので無視する。
import warnings
warnings.simplefilter(action = 'ignore', category = RuntimeWarning)

# トレードで取得する足の数を設定する。
COUNT = 500
# 許容誤差を設定する。
EPS = 1.0e-5

class ForexSystem(object):
    def __init__(self, environment=None, account_id=None, access_token=None):
        '''初期化する。
          Args:
              environment: 環境。
              account_id: アカウントID。
              access_token: アクセストークン。
        '''

        # クラス変数を格納する。
        self.environment = environment
        self.account_id = account_id
        self.access_token = access_token
        self.path = os.path.dirname(__file__)

        # バックテストの場合（バックテストの場合は環境が空）、
        if environment is None:
            # 一時フォルダが残っていたら削除する。
            if os.path.exists(self.path + '/tmp') == True:
                shutil.rmtree(self.path + '/tmp')
    
            # 一時フォルダを作成する。
            os.mkdir(self.path + '/tmp')

        # トレードの場合、APIを格納する（トレードの場合は環境が空ではない）。
        if environment is not None:
            self.oanda = oandapy.API(
                environment=self.environment, access_token=self.access_token)
 
    def ask(self, instrument):
        '''買値を得る。
          Args:
              instrument: OANDA APIでの通貨ペア名。
          Returns:
              買値。
        '''

        instruments = self.oanda.get_prices(instruments=instrument)
        ask = instruments['prices'][0]['ask']

        return ask

    def backtest(self, parameter, calc_signal, symbol, timeframe, position,
                 rranges, spread, optimization, min_trade, start, end,
                 strategy):
        '''バックテストを行う。
          Args:
              parameter: 最適化するパラメータ。
              calc_signal: シグナルを計算する関数。
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              position: ポジションの設定。
              rranges: ブルートフォースで指定するパラメータの範囲。
              spread: スプレッド。
              optimization: 最適化の設定。
              min_trade: 最低トレード数。
              start: 開始日。
              end: 終了日。
              strategy: 戦略名。
        '''

        def calc_performance(parameter, fs, calc_signal, symbol, timeframe,
                             position, start, end, spread, optimization,
                             min_trade):
            '''パフォーマンスを計算する。
              Args:
                  parameter: 最適化するパラメータ。
                  fs: forex_systemクラスのインスタンス。
                  calc_signal: シグナルを計算する関数。
                  symbol: 通貨ペア名。
                  timeframe: タイムフレーム。
                  position: ポジションの設定。
                  start: 開始日。
                  end: 終了日。
                  spread: スプレッド。
                  optimization: 最適化の設定。
                  min_trade: 最低トレード数。
              Returns:
                  最適化の場合は適応度、そうでない場合はリターン, トレード数, 年率,
                  シャープレシオ, 最適レバレッジ, ドローダウン, ドローダウン期間。
            '''

            # パフォーマンスを計算する。
            signal = calc_signal(parameter, fs, symbol, timeframe, position,
                                 start, end, spread, optimization, min_trade)
            ret = fs.calc_ret(symbol, timeframe, signal, spread, start, end)
            trades = fs.calc_trades(signal, start, end)
            sharpe = fs.calc_sharpe(ret, start, end)

            # 最適化する場合、適応度の符号を逆にして返す（最適値=最小値のため）。
            if optimization == 1:
                years = (end - start).total_seconds() / 60 / 60 / 24 / 365
                # 1年当たりのトレード数が最低トレード数に満たない場合、
                # 適応度を0にする。
                if trades / years >= min_trade:
                    fitness = sharpe
                else:
                    fitness = 0.0

                return -fitness
        
            # 最適化しない場合、各パフォーマンスを返す。
            else:  #  optimization == 0
                apr = fs.calc_apr(ret, start, end)
                kelly = fs.calc_kelly(ret)
                drawdowns = fs.calc_drawdowns(ret)
                durations = fs.calc_durations(ret, timeframe)

                return ret, trades, apr, sharpe, kelly, drawdowns, durations

        # バックテストを行う。
        if optimization == 1:
            result = optimize.brute(
                calc_performance, rranges, args=(self, calc_signal, symbol,
                timeframe, position, start, end, spread, 1, min_trade),
                finish=None)
            parameter = result

        ret, trades, apr, sharpe, kelly, drawdowns, durations = (
            calc_performance(parameter, self, calc_signal, symbol, timeframe,
            position, start, end, spread, 0, min_trade))

        # グラフを作成する。
        cum_ret = ret.cumsum()
        graph = cum_ret.plot()
        graph.set_title(strategy + '(' + symbol + str(timeframe) + ')')
        graph.set_xlabel('date')
        graph.set_ylabel('cumulative return')

        # レポートを作成する。
        report =  pd.DataFrame(
            index=[0], columns=['start','end', 'trades', 'apr', 'sharpe',
            'kelly', 'drawdowns', 'durations', 'parameter'])
        report['start'] = start.strftime('%Y.%m.%d')
        report['end'] = end.strftime('%Y.%m.%d')
        report['trades'] = trades
        report['apr'] = apr
        report['sharpe'] = sharpe
        report['kelly'] = kelly
        report['drawdowns'] = drawdowns
        report['durations'] = durations
        report['parameter'] = str(parameter)

        # グラフを出力する。
        plt.show()
        plt.close()

        # レポートを出力する。
        pd.set_option('line_width', 1000)
        print('strategy = ', strategy)
        print('symbol = ', symbol)
        print('timeframe = ', str(timeframe))
        print(report)
         
    def bid(self, instrument):
        '''売値を得る。
          Args:
              instrument: OANDA APIでの通貨ペア名。
          Returns:
              売値。
        '''

        instruments = self.oanda.get_prices(instruments=instrument)
        bid = instruments['prices'][0]['bid']

        return bid
 
    def calc_apr(self, ret, start, end):
        '''年率を計算する。
          Args:
              ret: リターン。
              start: 開始年月日。
              end: 終了年月日。
          Returns:
              年率。
        '''

        rate = (ret + 1.0).prod() - 1.0
        years = (end - start).total_seconds() / 60.0 / 60.0 / 24.0 / 365.0
        apr = rate / years

        return apr
 
    def calc_drawdowns(self, ret):
        '''最大ドローダウン（％）を計算する。
          Args:
              ret: リターン。
          Returns:
              最大ドローダウン（％）。
        '''

        # 累積リターンを計算する。
        cum_ret = (ret + 1.0).cumprod() - 1.0
        cum_ret = np.array(cum_ret)
 
        # 最大ドローダウンを計算する。
        @jit(float64(float64[:]), nopython=True, cache=True)
        def func(cum_ret):
            length = len(cum_ret)
            high_watermark = np.zeros(length)
            drawdown = np.zeros(length)
            for i in range(length):
                if i == 0:
                    high_watermark[0] = cum_ret[0]
                else:
                    if high_watermark[i - 1] >= cum_ret[i]:
                        high_watermark[i] = high_watermark[i - 1]
                    else:
                        high_watermark[i] = cum_ret[i];
                if np.abs(1.0 + cum_ret[i]) < EPS:
                    drawdown[i] = drawdown[i - 1]
                else:
                    drawdown[i] = ((1.0 + high_watermark[i]) /
                    (1.0 + cum_ret[i]) - 1.0)
            for i in range(length):
                if i == 0:
                    drawdowns = drawdown[0];
                else:
                    if drawdown[i] > drawdowns:
                        drawdowns = drawdown[i];
            return drawdowns
        drawdowns = func(cum_ret)

        return drawdowns
 
    def calc_durations(self, ret, timeframe):
        '''最大ドローダウン期間を計算する。
          Args:
              ret: リターン。
              timeframe: タイムフレーム。
          Returns:
              最大ドローダウン期間。
        '''

        # 累積リターンを計算する。
        cum_ret = (ret + 1.0).cumprod() - 1.0
        cum_ret = np.array(cum_ret)
 
        # 最大ドローダウン期間を計算する。
        @jit(float64(float64[:]), nopython=True, cache=True)
        def func(cum_ret):
            length = len(cum_ret)
            high_watermark = np.zeros(length)
            drawdown = np.zeros(length)
            duration = np.zeros(length)
            for i in range(length):
                if i == 0:
                    high_watermark[0] = cum_ret[0]
                else:
                    if high_watermark[i - 1] >= cum_ret[i]:
                        high_watermark[i] = high_watermark[i - 1]
                    else:
                        high_watermark[i] = cum_ret[i];
                if np.abs(1.0 + cum_ret[i]) < EPS:
                    drawdown[i] = drawdown[i - 1]
                else:
                    drawdown[i] = ((1.0 + high_watermark[i]) /
                    (1.0 + cum_ret[i]) - 1.0)
            for i in range(length):
                if i == 0:
                    duration[0] = drawdown[0]
                else:
                    if drawdown[i] == 0.0:
                        duration[i] = 0
                    else:
                        duration[i] = duration[i - 1] + 1;
            for i in range(length):
                if i == 0:
                    durations = duration[0];
                else:
                    if duration[i] > durations:
                        durations = duration[i]
            durations = durations / (1440 / timeframe)  # 営業日単位に変換
            return durations
        durations = int(func(cum_ret))

        return durations
 
    def calc_kelly(self, ret):
        '''ケリー基準による最適レバレッジを計算する。
          Args:
              ret: リターン。
          Returns:
              ケリー基準による最適レバレッジ。
        '''

        mean = ret.mean()
        std = ret.std()

        # 標準偏差が0であった場合、とりあえず最適レバレッジは0ということにしておく。
        if np.abs(std) < EPS:  # 標準偏差がマイナスになるはずはないが一応。
            kelly = 0.0
        else:
            kelly = mean / (std * std)

        return kelly
 
    def calc_ret(self, symbol, timeframe, signal, spread, start, end):
        '''リターンを計算する。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              signal: シグナル。
              spread: スプレッド。
              start: 開始年月日。
              end: 終了年月日。
          Returns:
              年率。
        '''

        op = self.i_open(symbol, timeframe, 0)

        # コストを計算する。
        temp1 = (spread * ((signal > 0) & (signal > signal.shift(1))) *
            (signal - signal.shift(1)))
        temp2 = (spread * ((signal < 0) & (signal < signal.shift(1))) *
            (signal.shift(1) - signal))
        cost = temp1 + temp2

        # リターンを計算する。
        ret = ((op.shift(-1) - op) * signal - cost) / op
        ret = ret.fillna(0.0)
        ret[(ret==float('inf')) | (ret==float('-inf'))] = 0.0
        ret = ret[start:end]

        return ret
 
    def calc_sharpe(self, ret, start, end):
        '''シャープレシオを計算する。
          Args:
              ret: リターン。
              start: 開始年月日。
              end: 終了年月日。
          Returns:
              シャープレシオ。
        '''

        bars = len(ret)
        years = (end - start).total_seconds() / 60.0 / 60.0 / 24.0 / 365.0
        num_bar_per_year = bars / years
        mean = ret.mean()
        std = ret.std()

        # 標準偏差が0であった場合、とりあえずシャープレシオは0ということにしておく。
        if np.abs(std) < EPS:  # 標準偏差がマイナスになるはずはないが一応。
            sharpe = 0.0
        else:
            sharpe = np.sqrt(num_bar_per_year) * mean / std

        return sharpe
 
    def calc_trades(self, signal, start, end):
        '''トレード数を計算する。
          Args:
              signal: シグナル。
              start: 開始年月日。
              end: 終了年月日。
          Returns:
              トレード数。
        '''

        temp1 = (((signal > 0) & (signal > signal.shift(1))) *
            (signal - signal.shift(1)))
        temp2 = (((signal < 0) & (signal < signal.shift(1))) *
            (signal.shift(1) - signal))
        trade = temp1 + temp2
        trade = trade.fillna(0)
        trade = trade.astype(int)
        trades = trade[start:end].sum()

        return trades

    def convert_symbol2instrument(self, symbol):
        '''symbolをinstrumentに変換する。
          Args:
              symbol: 通貨ペア。
          Returns:
              instrument。
        '''

        if symbol == 'AUDCAD':
            instrument = 'AUD_CAD'
        elif symbol == 'AUDCHF':
            instrument = 'AUD_CHF'
        elif symbol == 'AUDJPY':
            instrument = 'AUD_JPY'
        elif symbol == 'AUDNZD':
            instrument = 'AUD_NZD'
        elif symbol == 'AUDUSD':
            instrument = 'AUD_USD'
        elif symbol == 'CADCHF':
            instrument = 'CAD_CHF'
        elif symbol == 'CADJPY':
            instrument = 'CAD_JPY'
        elif symbol == 'CHFJPY':
            instrument = 'CHF_JPY'
        elif symbol == 'EURAUD':
            instrument = 'EUR_AUD'
        elif symbol == 'EURCAD':
            instrument = 'EUR_CAD'
        elif symbol == 'EURCHF':
            instrument = 'EUR_CHF'
        elif symbol == 'EURGBP':
            instrument = 'EUR_GBP'
        elif symbol == 'EURJPY':
            instrument = 'EUR_JPY'
        elif symbol == 'EURNZD':
            instrument = 'EUR_NZD'
        elif symbol == 'EURUSD':
            instrument = 'EUR_USD' 
        elif symbol == 'GBPAUD':
            instrument = 'GBP_AUD'
        elif symbol == 'GBPCAD':
            instrument = 'GBP_CAD'
        elif symbol == 'GBPCHF':
            instrument = 'GBP_CHF'
        elif symbol == 'GBPJPY':
            instrument = 'GBP_JPY'
        elif symbol == 'GBPNZD':
            instrument = 'GBP_NZD'
        elif symbol == 'GBPUSD':
            instrument = 'GBP_USD'
        elif symbol == 'NZDCAD':
            instrument = 'NZD_CAD'
        elif symbol == 'NZDCHF':
            instrument = 'NZD_CHF'
        elif symbol == 'NZDJPY':
            instrument = 'NZD_JPY'
        elif symbol == 'NZDUSD':
            instrument = 'NZD_USD'
        elif symbol == 'USDCAD':
            instrument = 'USD_CAD'
        elif symbol == 'USDCHF':
            instrument = 'USD_CHF'
        else:  # symbol == 'USDJPY'
            instrument = 'USD_JPY'

        return instrument

    def convert_timeframe2granularity(self, timeframe):
        '''timeframeをgranularityに変換する。
          Args:
              timeframe: タイムフレーム。
          Returns:
              granularity。
        '''

        if timeframe == 1:
            granularity = 'M1'
        elif timeframe == 5:
            granularity = 'M5'
        elif timeframe == 15:
            granularity = 'M15'
        elif timeframe == 30:
            granularity = 'M30'
        elif timeframe == 60:
            granularity = 'H1'
        elif timeframe == 240:
            granularity = 'H4'
        else:  # timeframe == 1440
            granularity = 'D'

        return granularity

    def divide_symbol(self, symbol):
        '''通貨ペアをベース通貨とクウォート通貨に分ける。
          Args:
              symbol: 通貨ペア。
          Returns:
              ベース通貨、クウォート通貨。
        '''

        if symbol == 'AUDCAD':
            base = 'aud'
            quote = 'cad'
        elif symbol == 'AUDCHF':
            base = 'aud'
            quote = 'chf'
        elif symbol == 'AUDJPY':
            base = 'aud'
            quote = 'jpy'
        elif symbol == 'AUDNZD':
            base = 'aud'
            quote = 'nzd'
        elif symbol == 'AUDUSD':
            base = 'aud'
            quote = 'usd'
        elif symbol == 'CADCHF':
            base = 'cad'
            quote = 'chf'
        elif symbol == 'CADJPY':
            base = 'cad'
            quote = 'jpy'
        elif symbol == 'CHFJPY':
            base = 'chf'
            quote = 'jpy'
        elif symbol == 'EURAUD':
            base = 'eur'
            quote = 'aud'
        elif symbol == 'EURCAD':
            base = 'eur'
            quote = 'cad'
        elif symbol == 'EURCHF':
            base = 'eur'
            quote = 'chf'
        elif symbol == 'EURGBP':
            base = 'eur'
            quote = 'gbp'
        elif symbol == 'EURJPY':
            base = 'eur'
            quote = 'jpy'
        elif symbol == 'EURNZD':
            base = 'eur'
            quote = 'nzd'
        elif symbol == 'EURUSD':
            base = 'eur'
            quote = 'usd'
        elif symbol == 'GBPAUD':
            base = 'gbp'
            quote = 'aud'
        elif symbol == 'GBPCAD':
            base = 'gbp'
            quote = 'cad'
        elif symbol == 'GBPCHF':
            base = 'gbp'
            quote = 'chf'
        elif symbol == 'GBPJPY':
            base = 'gbp'
            quote = 'jpy'
        elif symbol == 'GBPNZD':
            base = 'gbp'
            quote = 'nzd'
        elif symbol == 'GBPUSD':
            base = 'gbp'
            quote = 'usd'
        elif symbol == 'NZDCAD':
            base = 'nzd'
            quote = 'cad'
        elif symbol == 'NZDCHF':
            base = 'nzd'
            quote = 'chf'
        elif symbol == 'NZDJPY':
            base = 'nzd'
            quote = 'jpy'
        elif symbol == 'NZDUSD':
            base = 'nzd'
            quote = 'usd'
        elif symbol == 'USDCAD':
            base = 'usd'
            quote = 'cad'
        elif symbol == 'USDCHF':
            base = 'usd'
            quote = 'chf'
        else:  # symbol == 'USDJPY'
            base = 'usd'
            quote = 'jpy'

        return base, quote

    def divide_symbol_time(self, symbol):
        '''通貨ペアをベース通貨とクウォート通貨それぞれの時間に分ける。
          Args:
              symbol: 通貨ペア。
          Returns:
              ベース通貨、クウォート通貨それぞれの時間。
        '''

        # AUD、JPY、NZDは東京時間、CHF、EUR、GBPはロンドン時間、CAD、USDはNY時間とする。
        if symbol == 'AUDCAD':
            base_time = 'tokyo'
            quote_time = 'ny'
        elif symbol == 'AUDCHF':
            base_time = 'tokyo'
            quote_time = 'ldn'
        elif symbol == 'AUDJPY':
            base_time = 'tokyo'
            quote_time = 'tokyo'
        elif symbol == 'AUDNZD':
            base_time = 'tokyo'
            quote_time = 'tokyo'
        elif symbol == 'AUDUSD':
            base_time = 'tokyo'
            quote_time = 'ny'
        elif symbol == 'CADCHF':
            base_time = 'ny'
            quote_time = 'ldn'
        elif symbol == 'CADJPY':
            base_time = 'ny'
            quote_time = 'tokyo'
        elif symbol == 'CHFJPY':
            base_time = 'ldn'
            quote_time = 'tokyo'
        elif symbol == 'EURAUD':
            base_time = 'ldn'
            quote_time = 'tokyo'
        elif symbol == 'EURCAD':
            base_time = 'ldn'
            quote_time = 'ny'
        elif symbol == 'EURCHF':
            base_time = 'ldn'
            quote_time = 'ldn'
        elif symbol == 'EURGBP':
            base_time = 'ldn'
            quote_time = 'ldn'
        elif symbol == 'EURJPY':
            base_time = 'ldn'
            quote_time = 'tokyo'
        elif symbol == 'EURNZD':
            base_time = 'ldn'
            quote_time = 'tokyo'
        elif symbol == 'EURUSD':
            base_time = 'ldn'
            quote_time = 'ny'
        elif symbol == 'GBPAUD':
            base_time = 'ldn'
            quote_time = 'tokyo'
        elif symbol == 'GBPCAD':
            base_time = 'ldn'
            quote_time = 'ny'
        elif symbol == 'GBPCHF':
            base_time = 'ldn'
            quote_time = 'ldn'
        elif symbol == 'GBPJPY':
            base_time = 'ldn'
            quote_time = 'tokyo'
        elif symbol == 'GBPNZD':
            base_time = 'ldn'
            quote_time = 'tokyo'
        elif symbol == 'GBPUSD':
            base_time = 'ldn'
            quote_time = 'ny'
        elif symbol == 'NZDCAD':
            base_time = 'tokyo'
            quote_time = 'ny'
        elif symbol == 'NZDCHF':
            base_time = 'tokyo'
            quote_time = 'ldn'
        elif symbol == 'NZDJPY':
            base_time = 'tokyo'
            quote_time = 'tokyo'
        elif symbol == 'NZDUSD':
            base_time = 'tokyo'
            quote_time = 'ny'
        elif symbol == 'USDCAD':
            base_time = 'ny'
            quote_time = 'ny'
        elif symbol == 'USDCHF':
            base_time = 'ny'
            quote_time = 'ldn'
        else:  # symbol == 'USDJPY'
            base_time = 'ny'
            quote_time = 'tokyo'

        return base_time, quote_time

    def i_bandwalk(self, symbol, timeframe, period, shift):
        '''バンドウォークを返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              period: 期間。
              shift: シフト。
          Returns:
              バンドウォーク。
        '''
 
        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_bandwalk_' + symbol + str(timeframe) +
            '_' + str(period) + '_' + str(shift) + '.pkl')

        # バックテストのとき、計算結果が保存されていれば復元する。
        if self.environment is None and os.path.exists(file_path) == True:
            bandwalk = joblib.load(file_path)
        # さもなければ計算する。
        else:
            # バンドウォークを計算する関数を定義する。
            @jit(float64[:](float64[:], float64[:], float64[:]),
                nopython=True, cache=True)
            def calc_bandwalk(high, low, median):
                up = 0
                down = 0
                length = len(median)
                bandwalk = np.empty(length)
                for i in range(length):
                    if (low[i] > median[i]):
                        up = up + 1
                    else:
                        up = 0
                    if (high[i] < median[i]):
                        down = down + 1
                    else:
                        down = 0
                    bandwalk[i] = up - down
                return bandwalk
    
            # 高値、安値、終値を格納する。
            high = self.i_high(symbol, timeframe, shift)
            low = self.i_low(symbol, timeframe, shift)
            close = self.i_close(symbol, timeframe, shift)
    
            # 中央値を計算する。
            median = close.rolling(window=period).median()
            index = median.index
    
            # 高値、安値、中央値をnumpy配列に変換する。
            high = np.array(high)
            low = np.array(low)
            median = np.array(median)

            # バンドウォークを計算する。
            bandwalk = calc_bandwalk(high, low, median)
            a = 0.903  # 指数（正規化するために経験的に導き出した数値）
            b = 0.393  # 切片（同上）
            bandwalk = bandwalk / (float(period) ** a + b)

            # Seriesに変換する。
            bandwalk = pd.Series(bandwalk, index=index)
            bandwalk = bandwalk.fillna(0)

            # バックテストのとき、保存する。
            if self.environment is None:
                joblib.dump(bandwalk, file_path)
 
        return bandwalk

    def i_close(self, symbol, timeframe, shift):
        '''終値を返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              shift: シフト。
          Returns:
              終値。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_close_' + symbol + str(timeframe) +
            '_' + str(shift) + '.pkl')

        # バックテストのとき、
        if self.environment is None:
            # 計算結果が保存されていれば復元する。
            if os.path.exists(file_path) == True:
                close = joblib.load(file_path)

            # さもなければ計算する。
            else:
                filename = ('~/historical_data/' + symbol + str(timeframe) +
                    '.csv')
                temp = pd.read_csv( filename, index_col=0, header=0)
                index = pd.to_datetime(temp.index)
                temp.index = index
                close = temp.iloc[:, 3]
                close = close.shift(shift)
                joblib.dump(close, file_path)

        # トレードのとき、
        else:  # self.environment is not None
            instrument = self.convert_symbol2instrument(symbol)
            granularity = self.convert_timeframe2granularity(timeframe)
            temp = self.oanda.get_history(
                instrument=instrument, granularity=granularity, count=COUNT)
            self.time = pd.to_datetime(temp['candles'][COUNT-1]['time'])
            index = pd.Series(np.zeros(COUNT))
            close = pd.Series(np.zeros(COUNT))
            for i in range(COUNT):
                index[i] = temp['candles'][i]['time']
                close[i] = temp['candles'][i]['closeBid']
                index = pd.to_datetime(index)
                close.index = index
            close = close.shift(shift)

        return close

    def i_diff(self, symbol, timeframe, shift):
        '''終値の階差を返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              shift: シフト。
          Returns:
              終値の階差。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_diff_' + symbol + str(timeframe) + 
            '_' + str(shift) + '.pkl')

        # バックテストのとき、計算結果が保存されていれば復元する。
        if self.environment is None and os.path.exists(file_path) == True:
            diff = joblib.load(file_path)

        # さもなければ計算する。
        else:
            close = self.i_close(symbol, timeframe, shift)
            diff = close - close.shift(1)
            diff = diff.fillna(0.0)
            diff[(diff==float('inf')) | (diff==float('-inf'))] = 0.0

            # バックテストのとき、保存する。
            if self.environment is None:
                joblib.dump(diff, file_path)

        return diff

    def i_high(self, symbol, timeframe, shift):
        '''高値を返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              shift: シフト。
          Returns:
              高値。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_high_' + symbol + str(timeframe) +
            '_' + str(shift) + '.pkl')

        # バックテストのとき、
        if self.environment is None:
            # 計算結果が保存されていれば復元する。
            if os.path.exists(file_path) == True:
                high = joblib.load(file_path)

            # さもなければ計算する。
            else:
                filename = ('~/historical_data/' + symbol + str(timeframe) +
                    '.csv')
                temp = pd.read_csv( filename, index_col=0, header=0)
                index = pd.to_datetime(temp.index)
                temp.index = index
                high = temp.iloc[:, 1]
                high = high.shift(shift)
                joblib.dump(high, file_path)

        # トレードのとき、
        else:  # self.environment is not None
            instrument = self.convert_symbol2instrument(symbol)
            granularity = self.convert_timeframe2granularity(timeframe)
            temp = self.oanda.get_history(
                instrument=instrument, granularity=granularity, count=COUNT)
            self.time = pd.to_datetime(temp['candles'][COUNT-1]['time'])
            index = pd.Series(np.zeros(COUNT))
            high = pd.Series(np.zeros(COUNT))
            for i in range(COUNT):
                index[i] = temp['candles'][i]['time']
                high[i] = temp['candles'][i]['highBid']
                index = pd.to_datetime(index)
                high.index = index
            high = high.shift(shift)

        return high

    def i_hl_band(self, symbol, timeframe, period, shift):
        '''直近の高値、安値を返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              period: 計算期間。
              shift: シフト。
          Returns:
              直近の高値、安値。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_hl_band_' + symbol + str(timeframe) +
        '_' + str(shift) + '.pkl')

        # バックテストのとき、計算結果が保存されていれば復元する。
        if self.environment is None and os.path.exists(file_path) == True:
            hl_band = joblib.load(file_path)

        # さもなければ計算する。
        else:
            close = self.i_close(symbol, timeframe, shift)
            hl_band = pd.DataFrame()
            hl_band['high'] = close.rolling(window=period).max()
            hl_band['low'] = close.rolling(window=period).min()

            # バックテストのとき、保存する。
            if self.environment is None:
                joblib.dump(hl_band, file_path)

        return hl_band

    def i_ku_bandwalk(self, timeframe, period, shift, aud=0.0, cad=0.0, chf=0.0,
                      eur=1.0, gbp=0.0, jpy=1.0, nzd=0.0, usd=1.0):
        '''Ku-Chartによるバンドウォークを返す。
          Args:
              timeframe: タイムフレーム。
              period: 期間。
              shift: シフト。
              aud: 豪ドル（デフォルト：不使用）。
              cad: カナダドル（デフォルト：不使用）。
              chf: スイスフラン（デフォルト：不使用）。
              eur: ユーロ（デフォルト：使用）。
              gbp: ポンド（デフォルト：不使用）。
              jpy: 円（デフォルト：使用）。
              nzd: NZドル（デフォルト：不使用）。
              usd: 米ドル（デフォルト：使用）。
          Returns:
              Ku-Chartによるバンドウォーク。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_ku_bandwalk_' + symbol + str(timeframe) +
            '_' + str(period) + '_' + str(shift) + '_' + str(aud) + str(cad) +
            str(chf) + str(eur) + str(gbp) + str(jpy) + str(nzd) + str(usd) +
            '.pkl')

        # バックテストのとき、計算結果が保存されていれば復元する。
        if self.environment is None and os.path.exists(file_path) == True:
            ku_bandwalk = joblib.load(file_path)
        # さもなければ計算する。
        else:
            # Ku-Chartによるバンドウォークを計算する関数を定義する。
            @jit(float64[:, :](float64[:, :], float64[:, :], int64),
                 nopython=True, cache=True)   
            def calc_ku_bandwalk(ku_close, median, n):
                length = len(ku_close)
                ku_bandwalk = np.empty((length, n))
                for j in range(n):
                    up = 0
                    down = 0
                    for i in range(length):
                        if (ku_close[i][j] > median[i][j]):
                            up = up + 1
                        else:
                            up = 0
                        if (ku_close[i][j] < median[i][j]):
                            down = down + 1
                        else:
                            down = 0
                        ku_bandwalk[i][j] = up - down
                return ku_bandwalk

            ku_close = self.i_ku_close(
                timeframe, shift, aud, cad, chf, eur, gbp, jpy, nzd, usd)
            index = ku_close.index
            columns = ku_close.columns
            n = ((aud > EPS) + (cad > EPS) + (chf > EPS) + (eur > EPS) +
                (gbp > EPS) + (jpy > EPS) + (nzd > EPS) + (usd > EPS))
            median = ku_close.rolling(window=period).median()
            ku_close = ku_close.as_matrix()
            median = median.as_matrix()
            ku_bandwalk = calc_ku_bandwalk(ku_close, median, n)
            ku_bandwalk = pd.DataFrame(
                ku_bandwalk, index=index, columns=columns)
            ku_bandwalk = ku_bandwalk.fillna(0)
            a = 0.903  # 指数（正規化するために経験的に導き出した数値）
            b = 0.393  # 切片（同上）
            ku_bandwalk = ku_bandwalk / (float(period) ** a + b)

            # バックテストのとき、保存する。
            if self.environment is None:
                joblib.dump(ku_bandwalk, file_path)

        return ku_bandwalk

    def i_ku_close(self, timeframe, shift, aud=0.0, cad=0.0, chf=0.0, eur=1.0,
                   gbp=0.0, jpy=1.0, nzd=0.0, usd=1.0):
        '''Ku-Chartによる終値を返す。
          Args:
              timeframe: タイムフレーム。
              shift: シフト。
              aud: 豪ドル（デフォルト：不使用）。
              cad: カナダドル（デフォルト：不使用）。
              chf: スイスフラン（デフォルト：不使用）。
              eur: ユーロ（デフォルト：使用）。
              gbp: ポンド（デフォルト：不使用）。
              jpy: 円（デフォルト：使用）。
              nzd: NZドル（デフォルト：不使用）。
              usd: 米ドル（デフォルト：使用）。
          Returns:
              Ku-Chartによる終値。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_ku_close_' + str(timeframe) + '_' +
            str(shift) + '_' + str(aud) + str(cad) + str(chf) + str(eur) +
            str(gbp) + str(jpy) + str(nzd) + str(usd) + '.pkl')

        # バックテストのとき、計算結果が保存されていれば復元する。
        if self.environment is None and os.path.exists(file_path) == True:
            ku_close = joblib.load(file_path)
        # さもなければ計算する。
        else:
            ku_close = pd.DataFrame()

            # 重みの合計を計算する。
            weight_sum = aud + cad + chf + eur + gbp + jpy + nzd + usd

            # 終値を格納する。
            audusd = 0.0
            cadusd = 0.0
            chfusd = 0.0
            eurusd = 0.0
            gbpusd = 0.0
            jpyusd = 0.0
            nzdusd = 0.0
            if aud > EPS:
                audusd = self.i_close('AUDUSD', timeframe, shift)
                audusd = audusd.apply(np.log)
            if cad > EPS:
                cadusd = 1 / self.i_close('USDCAD', timeframe, shift)
                cadusd = cadusd.apply(np.log)
            if chf > EPS:
                chfusd = 1 / self.i_close('USDCHF', timeframe, shift)
                chfusd = chfusd.apply(np.log)
            if eur > EPS:
                eurusd = self.i_close('EURUSD', timeframe, shift)
                eurusd = eurusd.apply(np.log)
            if gbp > EPS:
                gbpusd = self.i_close('GBPUSD', timeframe, shift)
                gbpusd = gbpusd.apply(np.log)
            if jpy > EPS:
                jpyusd = 1 / self.i_close('USDJPY', timeframe, shift)
                jpyusd = jpyusd.apply(np.log)
            if nzd > EPS:
                nzdusd = self.i_close('NZDUSD', timeframe, shift)
                nzdusd = nzdusd.apply(np.log)

            # KU-AUDを作成する。
            if aud > EPS:
                audcad = audusd - cadusd
                audchf = audusd - chfusd
                audeur = audusd - eurusd
                audgbp = audusd - gbpusd
                audjpy = audusd - jpyusd
                audnzd = audusd - nzdusd
                ku_close['aud'] = (((audcad * aud * cad) +
                    (audchf * aud * chf) + (audeur * aud * eur) +
                    (audgbp * aud * gbp) + (audjpy * aud * jpy) +
                    (audnzd * aud * nzd) + (audusd * aud * usd)) /
                    weight_sum * 10000.0)

            # KU-CADを作成する。
            if cad > EPS:
                cadaud = cadusd - audusd
                cadchf = cadusd - chfusd
                cadeur = cadusd - eurusd
                cadgbp = cadusd - gbpusd
                cadjpy = cadusd - jpyusd
                cadnzd = cadusd - nzdusd
                ku_close['cad'] = (((cadaud * cad * aud) +
                    (cadchf * cad * chf) + (cadeur * cad * eur) +
                    (cadgbp * cad * gbp) + (cadjpy * cad * jpy) +
                    (cadnzd * cad * nzd) + (cadusd * cad * usd)) /
                    weight_sum * 10000.0)

            # KU-CHFを作成する。
            if chf > EPS:
                chfaud = chfusd - audusd
                chfcad = chfusd - cadusd
                chfeur = chfusd - eurusd
                chfgbp = chfusd - gbpusd
                chfjpy = chfusd - jpyusd
                chfnzd = chfusd - nzdusd
                ku_close['chf'] = (((chfaud * chf * aud) +
                    (chfcad * chf * cad) + (chfeur * chf * eur) +
                    (chfgbp * chf * gbp) + (chfjpy * chf * jpy) +
                    (chfnzd * chf * nzd) + (chfusd * chf * usd)) /
                    weight_sum * 10000.0)

            # KU-EURを作成する。
            if eur > EPS:
                euraud = eurusd - audusd
                eurcad = eurusd - cadusd
                eurchf = eurusd - chfusd
                eurgbp = eurusd - gbpusd
                eurjpy = eurusd - jpyusd
                eurnzd = eurusd - nzdusd
                ku_close['eur'] = (((euraud * eur * aud) +
                    (eurcad * eur * cad) + (eurchf * eur * chf) +
                    (eurgbp * eur * gbp) + (eurjpy * eur * jpy) +
                    (eurnzd * eur * nzd) + (eurusd * eur * usd)) /
                    weight_sum * 10000.0)

            # KU-GBPを作成する。
            if gbp > EPS:
                gbpaud = gbpusd - audusd
                gbpcad = gbpusd - cadusd
                gbpchf = gbpusd - chfusd
                gbpeur = gbpusd - eurusd
                gbpjpy = gbpusd - jpyusd
                gbpnzd = gbpusd - nzdusd
                ku_close['gbp'] = (((gbpaud * gbp * aud) +
                    (gbpcad * gbp * cad) + (gbpchf * gbp * chf) +
                    (gbpeur * gbp * eur) + (gbpjpy * gbp * jpy) +
                    (gbpnzd * gbp * nzd) + (gbpusd * gbp * usd)) /
                    weight_sum * 10000.0)

            # KU-JPYを作成する。
            if jpy > EPS:
                jpyaud = jpyusd - audusd
                jpycad = jpyusd - cadusd
                jpychf = jpyusd - chfusd
                jpyeur = jpyusd - eurusd
                jpygbp = jpyusd - gbpusd
                jpynzd = jpyusd - nzdusd
                ku_close['jpy'] = (((jpyaud * jpy * aud) +
                    (jpycad * jpy * cad) + (jpychf * jpy * chf) +
                    (jpyeur * jpy * eur) + (jpygbp * jpy * gbp) +
                    (jpynzd * jpy * nzd) + (jpyusd * jpy * usd)) /
                    weight_sum * 10000.0)

            # KU-NZDを作成する。
            if nzd > EPS:
                nzdaud = nzdusd - audusd
                nzdcad = nzdusd - cadusd
                nzdchf = nzdusd - chfusd
                nzdeur = nzdusd - eurusd
                nzdgbp = nzdusd - gbpusd
                nzdjpy = nzdusd - jpyusd
                ku_close['nzd'] = (((nzdaud * nzd * aud) +
                    (nzdcad * nzd * cad) + (nzdchf * nzd * chf) +
                    (nzdeur * nzd * eur) + (nzdgbp * nzd * gbp) +
                    (nzdjpy * nzd * jpy) + (nzdusd * nzd * usd)) /
                    weight_sum * 10000.0)

            # KU-USDを作成する。
            if usd > EPS:
                usdaud = -audusd
                usdcad = -cadusd
                usdchf = -chfusd
                usdeur = -eurusd
                usdgbp = -gbpusd
                usdjpy = -jpyusd
                usdnzd = -nzdusd
                ku_close['usd'] = (((usdaud * usd * aud) +
                    (usdcad * usd * cad) + (usdchf * usd * chf) +
                    (usdeur * usd * eur) + (usdgbp * usd * gbp) +
                    (usdjpy * usd * jpy) + (usdnzd * usd * nzd)) /
                    weight_sum * 10000.0)

            ku_close = ku_close.fillna(method='ffill')
            ku_close = ku_close.fillna(method='bfill')

            # バックテストのとき、保存する。
            if self.environment is None:
                joblib.dump(ku_close, file_path)

        return ku_close

    def i_ku_z_score(self, timeframe, period, shift, aud=0.0, cad=0.0, chf=0.0,
                     eur=1.0, gbp=0.0, jpy=1.0, nzd=0.0, usd=1.0):
        '''Ku-Chartによるzスコアを返す。
          Args:
              timeframe: タイムフレーム。
              period: 期間。
              shift: シフト。
              aud: 豪ドル（デフォルト：不使用）。
              cad: カナダドル（デフォルト：不使用）。
              chf: スイスフラン（デフォルト：不使用）。
              eur: ユーロ（デフォルト：使用）。
              gbp: ポンド（デフォルト：不使用）。
              jpy: 円（デフォルト：使用）。
              nzd: NZドル（デフォルト：不使用）。
              usd: 米ドル（デフォルト：使用）。
          Returns:
              Ku-Chartによるzスコア。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_ku_z_score_' + symbol +
            str(timeframe) + '_' + str(period) + '_' + str(shift) + '_' +
            str(aud) + str(cad) + str(chf) + str(eur) + str(gbp) + str(jpy) +
            str(nzd) + str(usd) + '.pkl')

        # バックテストのとき、計算結果が保存されていれば復元する。
        if self.environment is None and os.path.exists(file_path) == True:
            ku_z_score = joblib.load(file_path)
        # さもなければ計算する。
        else:
            # zスコアを計算する関数を定義する。
            @jit(float64(float64[:]), nopython=True, cache=True)
            def calc_ku_z_score(ku_close):
                median = np.median(ku_close)
                period = len(ku_close)
                std = 0.0
                for i in range(period):
                    std = std + (ku_close[i] - median) * (ku_close[i] - median)
                std = std / period
                std = np.sqrt(std)
                if std < EPS:
                    ku_z_score = 0.0
                else:
                    ku_z_score = (ku_close[-1] - median) / std
                return ku_z_score

            ku_close = self.i_ku_close(timeframe, shift, aud, cad, chf, eur,
                                       gbp, jpy, nzd, usd)
            ku_z_score = ku_close.rolling(window=period).apply(calc_ku_z_score)
            ku_z_score = ku_z_score.fillna(0)
            ku_z_score[(ku_z_score==float('inf')) |
                (ku_z_score==float('-inf'))] = 0.0

            # バックテストのとき、保存する。
            if self.environment is None:
                joblib.dump(ku_z_score, file_path)

        return ku_z_score

    def i_low(self, symbol, timeframe, shift):
        '''安値を返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              shift: シフト。
          Returns:
              安値。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_low_' + symbol + str(timeframe) +
            '_' + str(shift) + '.pkl')

        # バックテストのとき、
        if self.environment is None:
            # 計算結果が保存されていれば復元する。
            if os.path.exists(file_path) == True:
                low = joblib.load(file_path)

            # さもなければ計算する。
            else:
                filename = ('~/historical_data/' + symbol + str(timeframe) +
                    '.csv')
                temp = pd.read_csv( filename, index_col=0, header=0)
                index = pd.to_datetime(temp.index)
                temp.index = index
                low = temp.iloc[:, 2]
                low = low.shift(shift)
                joblib.dump(low, file_path)

        # トレードのとき、
        else:  # self.environment is not None
            instrument = self.convert_symbol2instrument(symbol)
            granularity = self.convert_timeframe2granularity(timeframe)
            temp = self.oanda.get_history(
                instrument=instrument, granularity=granularity, count=COUNT)
            self.time = pd.to_datetime(temp['candles'][COUNT-1]['time'])
            index = pd.Series(np.zeros(COUNT))
            low = pd.Series(np.zeros(COUNT))
            for i in range(COUNT):
                index[i] = temp['candles'][i]['time']
                low[i] = temp['candles'][i]['lowBid']
                index = pd.to_datetime(index)
                low.index = index
            low = low.shift(shift)

        return low

    def i_open(self, symbol, timeframe, shift):
        '''始値を返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              shift: シフト。
          Returns:
              始値。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_open_' + symbol + str(timeframe) +
            '_' + str(shift) + '.pkl')

        # バックテストのとき、
        if self.environment is None:
            # 計算結果が保存されていれば復元する。
            if os.path.exists(file_path) == True:
                op = joblib.load(file_path)

            # さもなければ計算する。
            else:
                filename = ('~/historical_data/' + symbol + str(timeframe) +
                    '.csv')
                temp = pd.read_csv( filename, index_col=0, header=0)
                index = pd.to_datetime(temp.index)
                temp.index = index
                op = temp.iloc[:, 0]
                op = op.shift(shift)
                joblib.dump(op, file_path)

        # トレードのとき、
        else:  # self.environment is not None
            instrument = self.convert_symbol2instrument(symbol)
            granularity = self.convert_timeframe2granularity(timeframe)
            temp = self.oanda.get_history(
                instrument=instrument, granularity=granularity, count=COUNT)
            self.time = pd.to_datetime(temp['candles'][COUNT-1]['time'])
            index = pd.Series(np.zeros(COUNT))
            op = pd.Series(np.zeros(COUNT))
            for i in range(COUNT):
                index[i] = temp['candles'][i]['time']
                op[i] = temp['candles'][i]['openBid']
                index = pd.to_datetime(index)
                op.index = index
            op = op.shift(shift)

        return op

    def i_volume(self, symbol, timeframe, shift):
        '''出来高を返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              shift: シフト。
          Returns:
              出来高。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_volume_' + symbol + str(timeframe) +
            '_' + str(shift) + '.pkl')

        # バックテストのとき、
        if self.environment is None:
            # 計算結果が保存されていれば復元する。
            if os.path.exists(file_path) == True:
                volume = joblib.load(file_path)

            # さもなければ計算する。
            else:
                filename = ('~/historical_data/' + symbol + str(timeframe) +
                    '.csv')
                temp = pd.read_csv( filename, index_col=0, header=0)
                index = pd.to_datetime(temp.index)
                temp.index = index
                volume = temp.iloc[:, 4]
                volume = volume.shift(shift)
                joblib.dump(volume, file_path)

        # トレードのとき、
        else:  # self.environment is not None
            instrument = self.convert_symbol2instrument(symbol)
            granularity = self.convert_timeframe2granularity(timeframe)
            temp = self.oanda.get_history(
                instrument=instrument, granularity=granularity, count=COUNT)
            self.time = pd.to_datetime(temp['candles'][COUNT-1]['time'])
            index = pd.Series(np.zeros(COUNT))
            volume = pd.Series(np.zeros(COUNT))
            for i in range(COUNT):
                index[i] = temp['candles'][i]['time']
                volume[i] = temp['candles'][i]['volumeBid']
                index = pd.to_datetime(index)
                volume.index = index
            volume = volume.shift(shift)

        return volume

    def i_z_score(self, symbol, timeframe, period, shift):
        '''実測値とその予測値との誤差のzスコアを返す。
          Args:
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              period: 期間。
              shift: シフト。
          Returns:
              zスコア。
        '''

        # 計算結果の保存先のパスを格納する。
        file_path = (self.path + '/tmp/i_z_score_' + symbol + str(timeframe) +
            '_' + str(period) + '_' + str(shift) + '.pkl')

        # バックテストのとき、計算結果が保存されていれば復元する。
        if self.environment is None and os.path.exists(file_path) == True:
            z_score = joblib.load(file_path)

        # さもなければ計算する。
        else:
            # zスコアを計算する関数を定義する。
            @jit(float64(float64[:]), nopython=True, cache=True)
            def calc_z_score(close):
                median = np.median(close)
                period = len(close)
                std = 0.0
                for i in range(period):
                    std = std + (close[i] - median) * (close[i] - median)
                std = std / period
                std = np.sqrt(std)
                if std < EPS:
                    z_score = 0.0
                else:
                    z_score = (close[-1] - median) / std
                return z_score

            # 終値を格納する。
            close = self.i_close(symbol, timeframe, shift)

            # zスコアを計算する。
            z_score = close.rolling(window=period).apply(calc_z_score)
            z_score = z_score.fillna(0.0)
            z_score[(z_score==float('inf')) | (z_score==float('-inf'))] = (0.0)

            # バックテストのとき、計算結果を保存する。
            if self.environment is None:
                joblib.dump(z_score, file_path)

        return z_score

    def is_trading_hours(self, index, market):
        '''取引時間であるか否かを返す。
          Args:
              index: インデックス。
              market: 市場
          Returns:
              取引時間であるか否か。
        '''

        # 東京時間の場合。
        if market == 'tokyo':
            trading_hours = (index.hour>=0) & (index.hour<6)
            trading_hours = pd.Series(trading_hours, index=index)
            '''
            # 夏時間の大まかな調整。
            trading_hours[(trading_hours.index.month>=3)
                & (trading_hours.index.month<11)] = ((index.hour>=0)
                & (index.hour<6))
            '''

        # ロンドン時間の場合。
        elif market == 'ldn':
            trading_hours = (index.hour>=8) & (index.hour<16)
            trading_hours = pd.Series(trading_hours, index=index)
            trading_hours[(trading_hours.index.hour==16)
                & (trading_hours.index.minute<30)] = True

            # 夏時間の大まかな調整。
            trading_hours[(trading_hours.index.month>=3)
                & (trading_hours.index.month<11)] = ((index.hour>=7)
                & (index.hour<15))
            trading_hours[(trading_hours.index.month>=3)
                & (trading_hours.index.month<11)
                & (trading_hours.index.hour==15)
                & (trading_hours.index.minute<30)] = True

        # NY時間の場合。
        else:  # market == 'ny':
            trading_hours = (index.hour>=15) & (index.hour<21)
            trading_hours = pd.Series(trading_hours, index=index)
            trading_hours[(trading_hours.index.hour==14)
                & (trading_hours.index.minute>=30)] = True

            # 夏時間の大まかな調整。
            trading_hours[(trading_hours.index.month>=3)
                & (trading_hours.index.month<11)] = ((index.hour>=14)
                & (index.hour<20))
            trading_hours[(trading_hours.index.month>=3)
                & (trading_hours.index.month<11)
                & (trading_hours.index.hour==13)
                & (trading_hours.index.minute>=30)] = True

        return trading_hours

    def order_close(self, ticket):
        '''決済注文を送信する。
          Args:
              ticket: チケット番号。
        '''

        self.oanda.close_trade(self.account_id, ticket)
 
    def order_send(self, symbol, lots, side):
        '''新規注文を送信する。
          Args:
              symbol: 通貨ペア名。
              lots: ロット数。
              side: 売買の種別
          Returns:
              チケット番号。
        '''

        # 通貨ペアの名称を変換する。
        instrument = self.convert_symbol2instrument(symbol)
        response = self.oanda.create_order(account_id=self.account_id,
            instrument=instrument, units=int(lots*10000), side=side,
            type='market')
        ticket = response['tradeOpened']['id']

        return ticket

    def orders_total(self):
        '''オーダー総数を計算する。
          Returns:
              オーダー総数。
        '''

        positions = self.oanda.get_positions(self.account_id)
        total = len(positions['positions'])

        return total

    def time_day_of_week(self, index):
        '''曜日を返す。
          Args:
              index: インデックス。
          Returns:
              曜日。
        '''

        time_day_of_week = pd.Series(index.dayofweek, index=index)

        return time_day_of_week
 
    def time_hour(self, index):
        '''時を返す。
          Args:
              index: インデックス。
          Returns:
              時。
        '''

        time_hour = pd.Series(index.hour, index=index)

        return time_hour
 
    def time_minute(self, index):
        '''分を返す。
          Args:
              index: インデックス。
          Returns:
              分。
        '''

        time_minute = pd.Series(index.minute, index=index)

        return time_minute

    def trade(self, parameter, calc_signal, symbol, timeframe, position, spread,
              lots, ea, folder_ea, mail, fromaddr, password, toaddr, strategy):
        '''トレードを行う。
          Args:
              parameter: デフォルトのパラメータ。
              calc_signal: シグナルを計算する関数。
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              position: ポジションの設定。
              spread: スプレッド。
              lots: ロット数。
              ea: EAの設定。
              folder_ea: EAがアクセスするフォルダー名。
              mail: メールの設定。
              fromaddr: 送信元のメールアドレス。
              password: 送信元のメールアドレスのパスワード。
              toaddr: 送信先のメールアドレス。
              strategy: 戦略名。
        '''

        # 通貨ペアの名称を変換する。
        instrument = self.convert_symbol2instrument(symbol)

        # 足の名称を変換する。
        granularity = self.convert_timeframe2granularity(timeframe)

        # 単位調整のための乗数と桁数を設定する。
        if (symbol == 'AUDJPY' or symbol == 'CADJPY' or symbol == 'CHFJPY' or
            symbol == 'EURJPY' or symbol == 'GBPJPY' or symbol == 'NZDJPY' or
            symbol == 'USDJPY'):
            multiplier = 100
            digit = 3
        else:
        # symbol == 'AUDCAD', 'AUDCHF', 'AUDNZD', 'AUDUSD', 'CADCHF', 'EURAUD',
        #           'EURCAD', 'EURCHF', 'EURGBP', 'EURNZD', 'EURUSD', 'GBPAUD',
        #           'GBPCAD', 'GBPCHF', 'GBPNZD', 'GBPUSD', 'NZDCAD', 'NZDCHF',
        #           'NZDUSD', 'USDCAD', 'USDCHF'
            multiplier = 10000
            digit = 5

        pre_bid = 0.0
        pre_ask = 0.0
        count = COUNT
        pre_history_time = None
        ticket = 0
        pos = 0
        filename = folder_ea + '/' + strategy + '.csv'

        # EA用ファイルを初期化する。
        if ea == 1:
            f = open(filename, 'w')
            f.write(str(2))  # EA側で-2とするので2で初期化する。
            f.close()

        # メールを設定する。
        if mail == 1:
            host = 'smtp.mail.yahoo.co.jp'
            port = 465
            fromaddr = fromaddr
            toaddr = toaddr
            password = password
        while True:
            # 回線接続を確認してから実行する。
            try:
                # 回線が接続していないと約15分でエラーになる。
                bid = self.bid(instrument)
                ask = self.ask(instrument)
                # tickが動いたときのみ実行する。
                if np.abs(bid - pre_bid) >= EPS or np.abs(ask - pre_ask) >= EPS:
                    pre_bid = bid
                    pre_ask = ask
                    history = self.oanda.get_history(
                        instrument=instrument, granularity=granularity,
                        count=count)
                    history_time = history['candles'][count-1]['time']
                    # 過去のデータの更新が完了してから実行する。
                    # シグナルの計算は過去のデータを用いているので、過去のデータの
                    # 更新が完了してから実行しないと計算がおかしくなる。
                    if history_time != pre_history_time:
                        pre_history_time = history_time
                        signal = calc_signal(
                            parameter, self, symbol, timeframe, position)
                        end_row = len(signal) - 1
                        # 決済注文を送信する。
                        # 決済注文を新規注文の前に置かないとドテンができなくなる。
                        if pos == 1 and signal[end_row] != 1:
                            self.order_close(ticket)
 
                           # EAにシグナルを送信する場合
                            if ea == 1:
                                f = open(filename, 'w')
                                f.write(str(int(signal[end_row] + 2)))
                                f.close()

                            # メールにシグナルを送信する場合
                            if mail == 1:
                                msg = MIMEText(
                                    symbol + 'を' +  str(bid)
                                    + 'で買いエグジットです。')
                                msg['Subject'] = strategy
                                msg['From'] = fromaddr
                                msg['To'] = toaddr
                                s = smtplib.SMTP_SSL(host, port)
                                s.login(fromaddr, password)
                                s.send_message(msg)
                                s.quit()
                            ticket = 0
                            pos = 0
                        elif pos == -1 and signal[end_row] != -1:
                            self.order_close(ticket)

                            # EAにシグナルを送信する場合
                            if ea == 1:
                                f = open(filename, 'w')
                                f.write(str(int(signal[end_row] + 2)))
                                f.close()

                            # メールにシグナルを送信する場合
                            if mail == 1:
                                msg = MIMEText(
                                    symbol + 'を' + str(ask)
                                    + 'で売りエグジットです。')
                                msg['Subject'] = strategy
                                msg['From'] = fromaddr
                                msg['To'] = toaddr
                                s = smtplib.SMTP_SSL(host, port)
                                s.login(fromaddr, password)
                                s.send_message(msg)
                                s.quit()
                            ticket = 0
                            pos = 0

                        # 新規注文を送信する
                        if (pos == 0 and ask - bid <= spread):
                            if (signal[end_row] == 1):
                                ticket = self.order_send(symbol, lots, 'buy')
                                pos = 1

                                # EAにシグナルを送信する場合
                                if ea == 1:
                                    f = open(filename, 'w')
                                    f.write(str(int(signal[end_row] + 2)))
                                    f.close()

                                # メールにシグナルを送信する場合
                                if mail == 1:
                                    msg = MIMEText(
                                        symbol + 'を' + str(ask)
                                        + 'で買いエントリーです。')
                                    msg['Subject'] = strategy
                                    msg['From'] = fromaddr
                                    msg['To'] = toaddr
                                    s = smtplib.SMTP_SSL(host, port)
                                    s.login(fromaddr, password)
                                    s.send_message(msg)
                                    s.quit()

                            elif (signal[end_row] == -1):
                                ticket = self.order_send(symbol, lots, 'sell')
                                pos = -1

                                # EAにシグナルを送信する場合
                                if ea == 1:
                                    f = open(filename, 'w')
                                    f.write(str(int(signal[end_row] + 2)))
                                    f.close()

                                # メールにシグナルを送信する場合
                                if mail == 1:
                                    msg = MIMEText(
                                        symbol + 'を' + str(bid)
                                        + 'で売りエントリーです。')
                                    msg['Subject'] = strategy
                                    msg['From'] = fromaddr
                                    msg['To'] = toaddr
                                    s = smtplib.SMTP_SSL(host, port)
                                    s.login(fromaddr, password)
                                    s.send_message(msg)
                                    s.quit()

                    # ポジション情報を出力
                    now = datetime.now()
                    positions = self.oanda.get_positions(self.account_id)
                    total = self.orders_total()
                    total_symbol = 0
                    if total != 0:
                        for i in range(total):
                            if (positions['positions'][i]['instrument']
                                == instrument):
                                side = positions['positions'][i]['side']
                                avg_price = round(
                                    positions['positions'][i]['avgPrice'],
                                    digit)
                                total_symbol = total_symbol + 1
                                if side == 'buy':
                                    pnl = (bid - avg_price) * multiplier
                                    price = bid

                                else:
                                    pnl = (avg_price - ask) * multiplier
                                    price = ask
                                pnl = round(pnl, 1)
                                price = round(price, digit)
                    if total_symbol == 0:
                        side = 'None'
                        avg_price = 0.0
                        price = 0.0
                        pnl = 0.0
                    print(now.strftime('%Y.%m.%d %H:%M:%S'), symbol, lots, side,
                          avg_price, price, pnl)
            except:
                print('回線不通')
                time.sleep(1)  # 1秒おきに表示させる。
 
    def walk_forward_test(self, parameter, calc_signal, symbol, timeframe,
                          position, rranges, spread, optimization, min_trade,
                          in_sample_period, out_of_sample_period, fixed_window,
                          start, end, strategy):
        '''ウォークフォワードテストを行う。
          Args:
              parameter: 最適化するパラメータ。
              calc_signal: シグナルを計算する関数。
              symbol: 通貨ペア名。
              timeframe: タイムフレーム。
              position: ポジションの設定。
              rranges: ブルートフォースで指定するパラメータの範囲。
              spread: スプレッド。
              optimization: 最適化の設定。
              min_trade: 最低トレード数。
              in_sample_period: インサンプル期間
              out_of_sample_period: アウトオブサンプル期間
              fixed_window: ウィンドウ固定の設定。
              start: 開始日。
              end: 終了日。
              strategy: 戦略名。
        '''

        end_test = start
        report =  pd.DataFrame(
            index=range(1000),
            columns=['start_train','end_train', 'start_test', 'end_test',
                     'trades', 'apr', 'sharpe', 'kelly', 'drawdowns',
                     'durations', 'parameter'])

        def calc_performance(parameter, fs, calc_signal, symbol, timeframe,
                             position, start, end, spread, optimization,
                             min_trade):
            '''パフォーマンスを計算する。
              Args:
                  parameter: 最適化するパラメータ。
                  fs: forex_systemクラスのインスタンス。
                  calc_signal: シグナルを計算する関数。
                  symbol: 通貨ペア名。
                  timeframe: タイムフレーム。
                  position: ポジションの設定。
                  start: 開始日。
                  end: 終了日。
                  spread: スプレッド。
                  optimization: 最適化の設定。
                  min_trade: 最低トレード数。
              Returns:
                  最適化の場合は適応度、そうでない場合はリターン, トレード数, 年率,
                  シャープレシオ, 最適レバレッジ, ドローダウン, ドローダウン期間、
                  シグナル。
            '''

            # パフォーマンスを計算する。
            signal = calc_signal(parameter, fs, symbol, timeframe, position,
                                 start, end, spread, optimization, min_trade)
            ret = fs.calc_ret(symbol, timeframe, signal, spread, start, end)
            trades = fs.calc_trades(signal, start, end)
            sharpe = fs.calc_sharpe(ret, start, end)

            # 最適化する場合、適応度の符号を逆にして返す（最適値=最小値のため）。
            if optimization == 1:
                years = (end - start).total_seconds() / 60 / 60 / 24 / 365
                # 1年当たりのトレード数が最低トレード数に満たない場合、
                # 適応度を0にする。
                if trades / years >= min_trade:
                    fitness = sharpe
                else:
                    fitness = 0.0

                return -fitness
        
            # 最適化しない場合、各パフォーマンスを返す。
            else:  #  optimization == 0
                apr = fs.calc_apr(ret, start, end)
                kelly = fs.calc_kelly(ret)
                drawdowns = fs.calc_drawdowns(ret)
                durations = fs.calc_durations(ret, timeframe)

                return (ret, trades, apr, sharpe, kelly, drawdowns, durations,
                        signal)

        # ウォークフォワードテストを行う。
        i = 0
        while True:
            if fixed_window == 1:
                start_train = start + timedelta(days=out_of_sample_period*i)
                end_train = (start_train + timedelta(days=in_sample_period)
                    - timedelta(minutes=timeframe))
                start_test = end_train + timedelta(minutes=timeframe)
                end_test = (start_test + timedelta(days=out_of_sample_period)
                    - timedelta(minutes=timeframe))
            else:  # fixed_window == 0
                start_train = start
                end_train = (start_train
                    + timedelta(days=out_of_sample_period*i)
                    + timedelta(days=in_sample_period)
                    - timedelta(minutes=timeframe))
                start_test = end_train + timedelta(minutes=timeframe)
                end_test = (start_test + timedelta(days=out_of_sample_period)
                    - timedelta(minutes=timeframe))

            if end_test > end:
                break
            if optimization == 1:
                result = optimize.brute(
                    calc_performance, rranges, args=(self, calc_signal, symbol,
                    timeframe, position, start_train, end_train, spread, 1,
                    min_trade), finish=None)
                parameter = result
            ret, trades, apr, sharpe, kelly, drawdowns, durations, signal = (
                calc_performance(parameter, self, calc_signal, symbol,
                timeframe, position, start_test, end_test, spread, 0,
                min_trade))

            report.iloc[i][0] = start_train.strftime('%Y.%m.%d')
            report.iloc[i][1] = end_train.strftime('%Y.%m.%d')
            report.iloc[i][2] = start_test.strftime('%Y.%m.%d')
            report.iloc[i][3] = end_test.strftime('%Y.%m.%d')
            report.iloc[i][4] = trades
            report.iloc[i][5] = apr
            report.iloc[i][6] = sharpe
            report.iloc[i][7] = kelly
            report.iloc[i][8] = drawdowns
            report.iloc[i][9] = durations
            report.iloc[i][10] = str(parameter)

            if i == 0:
                signal_all = signal[start_test:end_test]
                start_all = start_test
            else:
                signal_all = signal_all.append(signal[start_test:end_test])
                end_all = end_test

            i = i + 1

        # 全体のパフォーマンスを計算する。
        ret_all = self.calc_ret(symbol, timeframe, signal_all, spread,
                                start_all, end_all)
        trades_all = self.calc_trades(signal_all, start_all, end_all)
        apr_all = self.calc_apr(ret_all, start_all, end_all)
        sharpe_all = self.calc_sharpe(ret_all, start_all, end_all)
        kelly_all = self.calc_kelly(ret_all)
        drawdowns_all = self.calc_drawdowns(ret_all)
        durations_all = self.calc_durations(ret_all, timeframe)

        # グラフを作成する。
        cum_ret = ret_all.cumsum()
        graph = cum_ret.plot()
        graph.set_title(strategy + '(' + symbol + str(timeframe) + ')')
        graph.set_xlabel('date')
        graph.set_ylabel('cumulative return')

        # レポートを作成する。
        report.iloc[i][0] = ''
        report.iloc[i][1] = ''
        report.iloc[i][2] = start_all.strftime('%Y.%m.%d')
        report.iloc[i][3] = end_all.strftime('%Y.%m.%d')
        report.iloc[i][4] = trades_all
        report.iloc[i][5] = apr_all
        report.iloc[i][6] = sharpe_all
        report.iloc[i][7] = kelly_all
        report.iloc[i][8] = drawdowns_all
        report.iloc[i][9] = int(durations_all)
        report.iloc[i][10] = ''

        # グラフを出力する。
        plt.show()
        plt.close()

        # レポートを出力する。
        pd.set_option('line_width', 1000)
        print('strategy = ', strategy)
        print('symbol = ', symbol)
        print('timeframe = ', str(timeframe))
        print(report.iloc[:i+1, ])

def convert_hst2csv(audcad=0, audchf=0, audjpy=0, audnzd=0, audusd=0, cadchf=0, 
                    cadjpy=0, chfjpy=0, euraud=0, eurcad=0, eurchf=0, eurgbp=0,
                    eurjpy=0, eurnzd=0, eurusd=0, gbpaud=0, gbpcad=0, gbpchf=0,
                    gbpjpy=0, gbpnzd=0, gbpusd=0, nzdcad=0, nzdchf=0, nzdjpy=0,
                    nzdusd=0, usdcad=0, usdchf=0, usdjpy=0):
    '''hstファイルをcsvファイルに変換する。
          Args:
              audcad: AUD/CAD。
              以下略。
    '''

    for i in range(28):
        if i == 0:
            if audcad == 0:
                continue
            symbol = 'AUDCAD'
        elif i == 1:
            if audchf == 0:
                continue
            symbol = 'AUDCHF'
        elif i == 2:
            if audjpy == 0:
                continue
            symbol = 'AUDJPY'
        elif i == 3:
            if audnzd == 0:
                continue
            symbol = 'AUDNZD'
        elif i == 4:
            if audusd == 0:
                continue
            symbol = 'AUDUSD'
        elif i == 5:
            if cadchf == 0:
                continue
            symbol = 'CADCHF'
        elif i == 6:
            if cadjpy == 0:
                continue
            symbol = 'CADJPY'
        elif i == 7:
            if chfjpy == 0:
                continue
            symbol = 'CHFJPY'
        elif i == 8:
            if euraud == 0:
                continue
            symbol = 'EURAUD'
        elif i == 9:
            if eurcad == 0:
                continue
            symbol = 'EURCAD'
        elif i == 10:
            if eurchf == 0:
                continue
            symbol = 'EURCHF'
        elif i == 11:
            if eurgbp == 0:
                continue
            symbol = 'EURGBP'
        elif i == 12:
            if eurjpy == 0:
                continue
            symbol = 'EURJPY'
        elif i == 13:
            if eurnzd == 0:
                continue
            symbol = 'EURNZD'
        elif i == 14:
            if eurusd == 0:
                continue 
            symbol = 'EURUSD'
        elif i == 15:
            if gbpaud == 0:
                continue
            symbol = 'GBPAUD'
        elif i == 16:
            if gbpcad == 0:
                continue
            symbol = 'GBPCAD'
        elif i == 17:
            if gbpchf == 0:
                continue
            symbol = 'GBPCHF'
        elif i == 18:
            if gbpjpy == 0:
                continue
            symbol = 'GBPJPY'
        elif i == 19:
            if gbpnzd == 0:
                continue
            symbol = 'GBPNZD'
        elif i == 20:
            if gbpusd == 0:
                continue
            symbol = 'GBPUSD'
        elif i == 21:
            if nzdcad == 0:
                continue
            symbol = 'NZDCAD'
        elif i == 22:
            if nzdchf == 0:
                continue
            symbol = 'NZDCHF'
        elif i == 23:
            if nzdjpy == 0:
                continue
            symbol = 'NZDJPY'
        elif i == 24:
            if nzdusd == 0:
                continue
            symbol = 'NZDUSD'
        elif i == 25:
            if usdcad == 0:
                continue
            symbol = 'USDCAD'
        elif i == 26:
            if usdchf == 0:
                continue
            symbol = 'USDCHF'
        elif i == 27:
            if usdjpy == 0:
                continue
            symbol = 'USDJPY'
        else:
            pass

        # 端末のカレントディレクトリが「~」で、そこからの相対パスであることに注意する。
        filename_hst = '../historical_data/' + symbol + '.hst'
        # 同上
        filename_csv = '../historical_data/' + symbol + '.csv'
        read = 0
        datetime = []
        open_price = []
        low_price = []
        high_price = []
        close_price = []
        volume = []
        with open(filename_hst, 'rb') as f:
            while True:
                if read >= 148:
                    buf = f.read(44)
                    read += 44
                    if not buf:
                        break
                    bar = struct.unpack('< iddddd', buf)
                    datetime.append(
                        time.strftime('%Y-%m-%d %H:%M:%S',
                        time.gmtime(bar[0])))
                    open_price.append(bar[1])
                    high_price.append(bar[3])  # 高値と安値の順序が違うようだ
                    low_price.append(bar[2])  # 同上
                    close_price.append(bar[4])
                    volume.append(bar[5])
                else:
                    buf = f.read(148)
                    read += 148
        data = {'0_datetime':datetime, '1_open_price':open_price,
            '2_high_price':high_price, '3_low_price':low_price,
            '4_close_price':close_price, '5_volume':volume}
        result = pd.DataFrame.from_dict(data)
        result = result.set_index('0_datetime')
        result.to_csv(filename_csv, header = False)

def make_historical_data(audcad=0, audchf=0, audjpy=0, audnzd=0, audusd=0,
                         cadchf=0, cadjpy=0, chfjpy=0, euraud=0, eurcad=0,
                         eurchf=0, eurgbp=0, eurjpy=0, eurnzd=0, eurusd=0,
                         gbpaud=0, gbpcad=0, gbpchf=0, gbpjpy=0, gbpnzd=0,
                         gbpusd=0, nzdcad=0, nzdchf=0, nzdjpy=0, nzdusd=0,
                         usdcad=0, usdchf=0, usdjpy=0):
    '''ヒストリカルデータを作成する。
          Args:
              audcad: AUD/CAD。
              以下略。
    '''

    data = pd.DataFrame()

    # csvファイルを読み込む。
    for i in range(28):
        if i == 0:
            if audcad == 0:
                continue
            symbol = 'AUDCAD'
        elif i == 1:
            if audchf == 0:
                continue
            symbol = 'AUDCHF'
        elif i == 2:
            if audjpy == 0:
                continue
            symbol = 'AUDJPY'
        elif i == 3:
            if audnzd == 0:
                continue
            symbol = 'AUDNZD'
        elif i == 4:
            if audusd == 0:
                continue
            symbol = 'AUDUSD'
        elif i == 5:
            if cadchf == 0:
                continue
            symbol = 'CADCHF'
        elif i == 6:
            if cadjpy == 0:
                continue
            symbol = 'CADJPY'
        elif i == 7:
            if chfjpy == 0:
                continue
            symbol = 'CHFJPY'
        elif i == 8:
            if euraud == 0:
                continue
            symbol = 'EURAUD'
        elif i == 9:
            if eurcad == 0:
                continue
            symbol = 'EURCAD'
        elif i == 10:
            if eurchf == 0:
                continue
            symbol = 'EURCHF'
        elif i == 11:
            if eurgbp == 0:
                continue
            symbol = 'EURGBP'
        elif i == 12:
            if eurjpy == 0:
                continue
            symbol = 'EURJPY'
        elif i == 13:
            if eurnzd == 0:
                continue
            symbol = 'EURNZD'
        elif i == 14:
            if eurusd == 0:
                continue 
            symbol = 'EURUSD'
        elif i == 15:
            if gbpaud == 0:
                continue
            symbol = 'GBPAUD'
        elif i == 16:
            if gbpcad == 0:
                continue
            symbol = 'GBPCAD'
        elif i == 17:
            if gbpchf == 0:
                continue
            symbol = 'GBPCHF'
        elif i == 18:
            if gbpjpy == 0:
                continue
            symbol = 'GBPJPY'
        elif i == 19:
            if gbpnzd == 0:
                continue
            symbol = 'GBPNZD'
        elif i == 20:
            if gbpusd == 0:
                continue
            symbol = 'GBPUSD'
        elif i == 21:
            if nzdcad == 0:
                continue
            symbol = 'NZDCAD'
        elif i == 22:
            if nzdchf == 0:
                continue
            symbol = 'NZDCHF'
        elif i == 23:
            if nzdjpy == 0:
                continue
            symbol = 'NZDJPY'
        elif i == 24:
            if nzdusd == 0:
                continue
            symbol = 'NZDUSD'
        elif i == 25:
            if usdcad == 0:
                continue
            symbol = 'USDCAD'
        elif i == 26:
            if usdchf == 0:
                continue
            symbol = 'USDCHF'
        elif i == 27:
            if usdjpy == 0:
                continue
            symbol = 'USDJPY'
        else:
            pass

        # 選択した通貨ペアの数を数える。
        n = (audcad + audchf + audjpy + audnzd + audusd + cadchf + cadjpy +
             chfjpy + euraud + eurcad + eurchf + eurgbp + eurjpy + eurnzd +
             eurusd + gbpaud + gbpcad + gbpchf + gbpjpy + gbpnzd + gbpusd +
             nzdcad + nzdchf + nzdjpy + nzdusd + usdcad + usdchf + usdjpy)

        # 1分足の作成
        filename = '~/historical_data/' + symbol + '.csv'
        if i == 0:
            data = pd.read_csv(filename, header=None, index_col=0)
            data.index = pd.to_datetime(data.index)
        else:
            temp = pd.read_csv(filename, header=None, index_col=0)
            temp.index = pd.to_datetime(temp.index)
            data = pd.merge(
                data, temp, left_index=True, right_index=True, how='outer')

    # 列名を変更する。
    label = ['open', 'high', 'low', 'close', 'volume']
    data.columns = label * n

    # リサンプリングの方法を設定する。
    ohlc_dict = OrderedDict()
    ohlc_dict['open'] = 'first'
    ohlc_dict['high'] = 'max'
    ohlc_dict['low'] = 'min'
    ohlc_dict['close'] = 'last'
    ohlc_dict['volume'] = 'sum'

    # 各足を作成する。
    count = 0
    for i in range(28):
        if i == 0:
            if audcad == 0:
                continue
            symbol = 'AUDCAD'
            count = count + 1
        elif i == 1:
            if audchf == 0:
                continue
            symbol = 'AUDCHF'
            count = count + 1
        elif i == 2:
            if audjpy == 0:
                continue
            symbol = 'AUDJPY'
            count = count + 1
        elif i == 3:
            if audnzd == 0:
                continue
            symbol = 'AUDNZD'
            count = count + 1
        elif i == 4:
            if audusd == 0:
                continue
            symbol = 'AUDUSD'
            count = count + 1
        elif i == 5:
            if cadchf == 0:
                continue
            symbol = 'CADCHF'
            count = count + 1
        elif i == 6:
            if cadjpy == 0:
                continue
            symbol = 'CADJPY'
            count = count + 1
        elif i == 7:
            if chfjpy == 0:
                continue
            symbol = 'CHFJPY'
            count = count + 1
        elif i == 8:
            if euraud == 0:
                continue
            symbol = 'EURAUD'
            count = count + 1
        elif i == 9:
            if eurcad == 0:
                continue
            symbol = 'EURCAD'
            count = count + 1
        elif i == 10:
            if eurchf == 0:
                continue
            symbol = 'EURCHF'
            count = count + 1
        elif i == 11:
            if eurgbp == 0:
                continue
            symbol = 'EURGBP'
            count = count + 1
        elif i == 12:
            if eurjpy == 0:
                continue
            symbol = 'EURJPY'
            count = count + 1
        elif i == 13:
            if eurnzd == 0:
                continue
            symbol = 'EURNZD'
            count = count + 1
        elif i == 14:
            if eurusd == 0:
                continue 
            symbol = 'EURUSD'
            count = count + 1
        elif i == 15:
            if gbpaud == 0:
                continue
            symbol = 'GBPAUD'
            count = count + 1
        elif i == 16:
            if gbpcad == 0:
                continue
            symbol = 'GBPCAD'
            count = count + 1
        elif i == 17:
            if gbpchf == 0:
                continue
            symbol = 'GBPCHF'
            count = count + 1
        elif i == 18:
            if gbpjpy == 0:
                continue
            symbol = 'GBPJPY'
            count = count + 1
        elif i == 19:
            if gbpnzd == 0:
                continue
            symbol = 'GBPNZD'
            count = count + 1
        elif i == 20:
            if gbpusd == 0:
                continue
            symbol = 'GBPUSD'
            count = count + 1
        elif i == 21:
            if nzdcad == 0:
                continue
            symbol = 'NZDCAD'
            count = count + 1
        elif i == 22:
            if nzdchf == 0:
                continue
            symbol = 'NZDCHF'
            count = count + 1
        elif i == 23:
            if nzdjpy == 0:
                continue
            symbol = 'NZDJPY'
            count = count + 1
        elif i == 24:
            if nzdusd == 0:
                continue
            symbol = 'NZDUSD'
            count = count + 1
        elif i == 25:
            if usdcad == 0:
                continue
            symbol = 'USDCAD'
            count = count + 1
        elif i == 26:
            if usdchf == 0:
                continue
            symbol = 'USDCHF'
            count = count + 1
        elif i == 27:
            if usdjpy == 0:
                continue
            symbol = 'USDJPY'
            count = count + 1
        else:
            pass
 
        data1 = data.iloc[:, 0+(5*(count-1)): 5+(5*(count-1))]

        # 欠損値を補間する。
        data1 = data1.fillna(method='ffill')
        data1 = data1.fillna(method='bfill')

        # 重複行を削除する。
        data1 = data1[~data1.index.duplicated()] 
 
        data5 = data1.resample(
            '5Min', label='left', closed='left').apply(ohlc_dict)
        data15 = data1.resample(
            '15Min', label='left', closed='left').apply(ohlc_dict)
        data30 = data1.resample(
            '30Min', label='left', closed='left').apply(ohlc_dict)
        data60 = data1.resample(
            '60Min', label='left', closed='left').apply(ohlc_dict)
        data240 = data1.resample(
            '240Min', label='left', closed='left').apply(ohlc_dict)
        data1440 = data1.resample(
            '1440Min', label='left', closed='left').apply(ohlc_dict)

        # 欠損値を削除する。
        data5 = data5.dropna()
        data15 = data15.dropna()
        data30 = data30.dropna()
        data60 = data60.dropna()
        data240 = data240.dropna()
        data1440 = data1440.dropna()

        # ファイルを出力する。
        filename1 =  '~/historical_data/' + symbol + '1.csv'
        filename5 =  '~/historical_data/' + symbol + '5.csv'
        filename15 =  '~/historical_data/' + symbol + '15.csv'
        filename30 =  '~/historical_data/' + symbol + '30.csv'
        filename60 =  '~/historical_data/' + symbol + '60.csv'
        filename240 =  '~/historical_data/' + symbol + '240.csv'
        filename1440 =  '~/historical_data/' + symbol + '1440.csv'
        data1.to_csv(filename1)
        data5.to_csv(filename5)
        data15.to_csv(filename15)
        data30.to_csv(filename30)
        data60.to_csv(filename60)
        data240.to_csv(filename240)
        data1440.to_csv(filename1440)

if __name__ == '__main__':
    # 設定を読み込む。
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default=None)
    parser.add_argument('--strategy', type=str, default=None)
    parser.add_argument('--symbol', type=str, default=None)
    parser.add_argument('--timeframe', type=int)
    parser.add_argument('--start', type=str, default=None)
    parser.add_argument('--end', type=str, default=None)
    parser.add_argument('--backtest', type=int, default=0)
    parser.add_argument('--position', type=int, default=2)
    parser.add_argument('--spread', type=int, default=0)
    parser.add_argument('--optimization', type=int, default=0)
    parser.add_argument('--min_trade', type=int, default=260)
    parser.add_argument('--in_sample_period', type=int, default=360)
    parser.add_argument('--out_of_sample_period', type=int, default=30)
    parser.add_argument('--lots', type=float, default=0.1)
    parser.add_argument('--mail', type=int, default=0)
    parser.add_argument('--ea', type=int, default=0)
    parser.add_argument('--func', type=str, default=None)
    args = parser.parse_args()

    strategy = args.strategy
    symbol = args.symbol
    timeframe = args.timeframe
    position = args.position
    spread = args.spread

    # スプレッドの単位の調整
    if (symbol == 'AUDJPY' or symbol == 'CADJPY' or symbol == 'CHFJPY' or
        symbol == 'EURJPY' or symbol == 'GBPJPY' or symbol == 'NZDJPY' or
        symbol == 'USDJPY'):
        spread = spread / 1000.0
    else:
    # symbol == 'AUDCAD', 'AUDCHF', 'AUDNZD', 'AUDUSD', 'CADCHF', 'EURAUD',
    #           'EURCAD', 'EURCHF', 'EURGBP', 'EURNZD', 'EURUSD', 'GBPAUD',
    #           'GBPCAD', 'GBPCHF', 'GBPNZD', 'GBPUSD', 'NZDCAD', 'NZDCHF',
    #           'NZDUSD', 'USDCAD', 'USDCHF'
        spread = spread / 100000.0

    # バックテスト（ウォークフォワードテストを含む）の場合
    if args.mode == 'backtest':
        backtest_start = time.time()

        mod = importlib.import_module(args.strategy)
        calc_signal = mod.calc_signal

        if hasattr(mod, "PARAMETER") == False:
            parameter = None
        else:
            parameter = mod.PARAMETER
        if hasattr(mod, "RRANGES") == False:
            rranges = None
        else:
            rranges = mod.RRANGES

        start = datetime.strptime(args.start, '%Y.%m.%d')
        end = datetime.strptime(args.end, '%Y.%m.%d')
        backtest = args.backtest
        optimization = args.optimization
        min_trade = args.min_trade
        in_sample_period = args.in_sample_period
        out_of_sample_period = args.out_of_sample_period

        fs = ForexSystem()

        # バックテストの場合
        if backtest == 0:
            fs.backtest(
                parameter, calc_signal, symbol, timeframe, position, rranges,
                spread, optimization, min_trade, start, end, strategy)
        # ウォークフォワードテスト（ウィンドウ固定）の場合
        elif backtest == 1:
            fs.walk_forward_test(
                parameter, calc_signal, symbol, timeframe, position, rranges,
                spread, optimization, min_trade, in_sample_period,
                out_of_sample_period, 1, start, end, strategy)
        # ウォークフォワードテスト（ウィンドウ非固定）の場合
        else:  # backtest == 2
            fs.walk_forward_test(
                parameter, calc_signal, symbol, timeframe, position, rranges,
                spread, optimization, min_trade, in_sample_period,
                out_of_sample_period, 0, start, end, strategy)
        backtest_end = time.time()
        # 結果を出力する。
        if backtest_end - backtest_start < 60.0:
            print(
                'バックテストの所要時間は',
                int(round(backtest_end - backtest_start)), '秒です。')
        else:
            print(
                'バックテストの所要時間は',
                int(round((backtest_end - backtest_start) / 60.0)), '分です。')

    # トレードの場合
    elif args.mode == 'trade':
        mod = importlib.import_module(args.strategy)
        calc_signal = mod.calc_signal

        if hasattr(mod, "PARAMETER") == False:
            parameter = None
        else:
            parameter = mod.PARAMETER

        path = os.path.dirname(__file__)
        mail = args.mail
        lots = args.lots
        ea = args.ea

        config = configparser.ConfigParser()
        config.read(path + '/settings.ini')
        environment = config['DEFAULT']['environment']
        account_id = int(config['DEFAULT']['account_id'])
        access_token = config['DEFAULT']['access_token']
        fromaddr = config['DEFAULT']['fromaddr']
        password = config['DEFAULT']['password']
        toaddr = config['DEFAULT']['toaddr']
        folder_ea = config['DEFAULT']['folder_ea']
        fs = ForexSystem(environment, account_id, access_token)
        fs.trade(parameter, calc_signal, symbol, timeframe, position, spread,
                 lots, ea, folder_ea, mail, fromaddr, password, toaddr,
                 strategy)

    # その他の場合
    else:
        def func(*args):
            '''入力した文字列を関数として実行する。
              Args:
                  *args: 可変長引数。
            '''
            exec(args[0])

        # 開始時間を格納する。
        start_time = time.time()
    
        # 作業ディレクトリのパスを格納する（このファイルは作業ディレクトリ内にある）。
        wd_path = os.path.dirname(__file__)
    
        # もし実行開始時に一時フォルダが残っていたら削除する。
        if os.path.exists(wd_path + '/tmp') == True:
            shutil.rmtree(wd_path + '/tmp')
    
        # 一時フォルダを作成する。
        os.mkdir(wd_path + '/tmp')
    
        # 引数を格納する。
        args = args.func
    
        # 実行する。
        func(args)
    
        # 一時フォルダを削除する。
        shutil.rmtree(wd_path + '/tmp')
    
        # 終了時間を格納する。
        end_time = time.time()
    
        # 実行時間を出力する。
        if end_time - start_time < 60.0:
            print(
                '実行時間は',
                int(round(end_time - start_time)), '秒です。')
        else:
            print(
                '実行時間は',
                int(round((end_time - start_time) / 60.0)), '分です。')