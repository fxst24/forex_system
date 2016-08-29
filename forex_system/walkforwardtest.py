# coding: utf-8

import argparse
import forex_system as fs
import os
import shutil
import time

if __name__ == '__main__':
    # 開始時間を記録する。
    start_time = time.time()

    # 一時フォルダが残っていたら削除する。
    path = os.path.dirname(__file__)
    if os.path.exists(path + '/tmp') == True:
        shutil.rmtree(path + '/tmp')

    # 一時フォルダを作成する。
    os.mkdir(path + '/tmp')

    parser = argparse.ArgumentParser()
    parser.add_argument('--ea1', nargs='*')
    parser.add_argument('--ea2', nargs='*')
    parser.add_argument('--ea3', nargs='*')
    args = parser.parse_args()

    ret_ea1, trades_ea1, timeframe, start, end = (
        fs.walkforwardtest(args.ea1))
    ret = ret_ea1
    trades = trades_ea1
    if args.ea2 is not None:
        ret_ea2, trades_ea2, timeframe, start, end = (
            fs.walkforwardtest(args.ea2))
        ret += ret_ea2
        trades += trades_ea2
    if args.ea3 is not None:
        ret_ea3, trades_ea3, timeframe, start, end = (
            fs.walkforwardtest(args.ea3))
        ret += ret_ea3
        trades += trades_ea3

    fs.show_walkforwardtest_result(ret, trades, timeframe, start, end)

    # 一時フォルダを削除する。
    path = os.path.dirname(__file__)
    if os.path.exists(path + '/tmp') == True:
        shutil.rmtree(path + '/tmp')

    # 終了時間を記録する。
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