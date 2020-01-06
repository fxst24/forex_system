#property library

#include <MyLib.mqh>

//決済注文のチェック
void CheckForClose(CTrade *ExtTrade, int BuyExit, int SellExit) export //"export"を忘れないこと。
{
   //買いポジションが選択され、かつ買いエグジットが成立している場合
   if( PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY && BuyExit)
      //決済注文を送信する。
      ExtTrade.PositionClose(Symbol(), 3);  //売り買い問わず、決済注文送信の形式は同じ。
   //売りポジションが選択され、かつ売りエグジットが成立している場合
   if( PositionGetInteger(POSITION_TYPE )== POSITION_TYPE_SELL && SellExit)
   //決済注文を送信する。
      ExtTrade.PositionClose(Symbol(), 3);  //同上。
}

//新規注文のチェック
void CheckForOpen(CTrade *ExtTrade, int BuyEntry, int SellEntry, double lot) export //"export"を忘れないこと。
{
   //買いエントリーが成立している場合
   if(BuyEntry)
   {
      //買い新規注文を送信する。
      ExtTrade.PositionOpen(Symbol(), ORDER_TYPE_BUY, lot, SymbolInfoDouble(Symbol(), SYMBOL_ASK), 0, 0);
   }
   //売りエントリーが成立している場合
   if(SellEntry)
   {
      //売り新規注文を送信する。
      ExtTrade.PositionOpen(Symbol(), ORDER_TYPE_SELL, lot, SymbolInfoDouble(Symbol(), SYMBOL_BID), 0, 0);
   }
}

//MQL4のiMA()関数と同等
double iMyMA(string symbol, int timeframe, int period, int ma_shift, int ma_methid, int applied_price, int shift) export //"export"を忘れないこと。
{
   double ma_arr[1], ret;
   int  ExtHandle;
   ExtHandle = iMA(symbol, (ENUM_TIMEFRAMES)timeframe, period, ma_shift, (ENUM_MA_METHOD)ma_methid, (ENUM_APPLIED_PRICE)applied_price);
   if(CopyBuffer( ExtHandle, 0, shift, 1, ma_arr) != 1) return 0.0;
   ret = ma_arr[0];
   return ret;
}

// トレンド期間の計算
double iTrendDuration(string symbol, int timeframe, int period, int shift) export //"export"を忘れないこと。
{
   double high, low, ma, ma_arr[1], ret;
   int  ExtHandle, i;
   double down = 0.0;
   double up = 0.0;
   ExtHandle = iMA(symbol, (ENUM_TIMEFRAMES)timeframe, period, 0, MODE_SMA, PRICE_CLOSE);
   for (i=period*2+shift-1; i>=shift; i--) {
      if(CopyBuffer( ExtHandle, 0, shift, 1, ma_arr) != 1) return 0.0;
      ma = ma_arr[0];
      high = iHigh(symbol,  (ENUM_TIMEFRAMES)timeframe, i);
      low = iLow(symbol,  (ENUM_TIMEFRAMES)timeframe, i);
      if (low > ma) up += 1.0;
      else up = 0.0;
      if (high < ma) down += 1.0;
      else down = 0.0;
   }
   ret = (up-down) / double(period);
   return ret;
}

//ZScoreの計算
double iZScore(string symbol, int timeframe, int period, int shift) export //"export"を忘れないこと。
{
   double close, ma, ma_arr[1], ret, std, std_arr[1];
   int  ExtHandle;
   close = iClose(symbol,  (ENUM_TIMEFRAMES)timeframe, shift);
   ExtHandle = iMA(symbol, (ENUM_TIMEFRAMES)timeframe, period, 0, MODE_SMA, PRICE_CLOSE);
      if(CopyBuffer( ExtHandle, 0, shift, 1, ma_arr) != 1) return 0.0;
      ma = ma_arr[0];
   ExtHandle = iStdDev(symbol, (ENUM_TIMEFRAMES)timeframe, period, 0, MODE_SMA, PRICE_CLOSE);
      if(CopyBuffer( ExtHandle, 0, shift, 1, std_arr) != 1) return 0.0;
      std = std_arr[0];
   if (std == 0) ret = 0.0;
   else ret = (close-ma) / std;
   return ret;
}

// 分を足に変換
int MinuteToPeriod(int minute) export //"export"を忘れないこと。
{
   int ret;
   ret = int(minute / Period());
   return ret;
}

//ポジションの選択
bool SelectPosition(int magic) export //"export"を忘れないこと。
{
   bool res;
   uint i, total;
   //ポジションを選択する。
   res = false;
   total = PositionsTotal();  //口座のポジション数を求める。
   for(i=0; i<total; i++)
   {
      if(Symbol() == PositionGetSymbol(i) && magic == PositionGetInteger(POSITION_MAGIC))
      {
         res = true;
         break;
      }
   }
   return res;
}