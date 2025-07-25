#!/usr/bin/env python3
"""\
Pump / Open Interest / Liquidations Screener

Лови все ПАМПЫ раньше 95% трейдеров, Щукин:
	https://www.youtube.com/watch?v=etxktQKHee4
	Pump присылает сигнал раньше чем OI, после накачки идет коррекция - открываем short,
	сигнал может дублироваться с OI.
	Мониторим:
		изменеие OI 5% за 15мин
		изменеие Price 2% за 2мин (LONG) и 10% за 10мин (SHORT)
	В какие сделки входить в LONG:
		Рост цены + рост OI + рост объемов + рост CVD = сильное движение.
		желательно первый сигнал за сутки. ЖДАТЬ хороший сигнал,
		лучше если движение началось из боковика
		CVD может падать во время роста цены
		заходить частями 2+3+5 поскольку движение может не подтвердиться
	В какие НЕ входить:
		цена вышла за сопротивление

Как работает индиактор CVD (Coinglass): https://www.youtube.com/watch?v=t5ek1x9ajHc
	это анализ рыночных объемов, не лимитных, рост индикатора говорит о накоплении покупок, иначе - продаж;
	в здоровом тренде кривые цены и CVD подобны, при расхождении надо входить/выходить из позиции;
	2 варианта - раскорелляция кривых или раскорелляция минимумов/максимумов, во втором случае, например,
	CVD ставит новые минимумы, когда цена продолжает расти, когда продавец истощится, цена уйдет выше

Торговля от ликвидаций: https://www.youtube.com/watch?v=u2sS_N7xQZE
	Послеприхода сигнала цена какое-то время продолжает двигаться в том же направлении,
	за тем разворот, ==если пробит значимый уровень==, не интересны ликвидации в начале тренда.
	Жди, открывай сделку там, где начинает падать OI и МВ.
	Не открывай если OI продолжает рост! Приближение разворота: объем LIQ растет, за тем убывает.

Check pair in realtime:
	https://www.coinglass.com/tv/ru/OKX_ETH-USDT-SWAP
	5min timeframe, indicators:
		Объем
		<CoinGlass> Совокупный открытый интерес (Свечи) Coins open
		<CoinGlass> Cumulative Volume Delta (CVD)
		<CoinGlass> Совокупные ликвидации
Docs:
	Bybit:	https://bybit-exchange.github.io/docs/v5/market/tickers - turnover24h
			https://bybit-exchange.github.io/docs/v5/market/instrument - launchTime
			https://bybit-exchange.github.io/docs/v5/websocket/public/ticker
			https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation
	OKX:	https://www.okx.com/docs-v5/en/#public-data-rest-api-get-index-tickers
			https://www.okx.com/api/v5/public/instruments?instType=SWAP
		 	https://www.okx.com/docs-v5/en/#public-data-websocket-index-tickers-channel
			https://www.okx.com/docs-v5/en/#public-data-websocket-open-interest-channel
			https://www.okx.com/docs-v5/en/#public-data-websocket-liquidation-orders-channel

Telegram:
	📊 price, 🔍 open interest, 🔥 liquidation
	use Ctrl+LMK to open link immediately
"""

__project__	= "Pump / Open Interest / Liquidations Screener"
__part__	= "Main"
__author__	= "Sergey V Musenko"
__email__	= "sergey@musenko.com"
__copyright__= "© 2025, musenko.com"
__license__	= "MIT"
__credits__	= ["Sergey Musenko"]
__date__	= "2025-05-31"
__version__	= "0.2"
__status__	= "dev"


import os, re
import requests
import websockets
import asyncio
import aiohttp
import json
import logging
import time
from typing import Dict, List

from lib.simple_telegram import *
from config import *

# get my secret LOCAL_CONFIG:
from socket import gethostname
if gethostname() in ['sereno', 'vostro']:
	from config_local import *


coinBlacklist = [] # will get it from coingecko.com
#buffers OKX
pairsOKX = []
pairsOKXcontract = {}
tickerBaseOKX = {} # compare changes with this
tickerSnapshotOKX = {} # same structure as tickerBaseOKX
lastWarningOKX = {} # symbol:timestamp
time2resetOKX = {'OI':0, 'price':0, 'counter':0} # next time to reset candle
pairsMaxPriceOKX = {} # show signal only if change is better then already saved here, max is valid only for time2reset*
pairsMaxOIOKX = {} # show signal only if change is better then already saved here, max is valid only for time2reset*
msgCountOKX = {} # symbol:N coin message counter since reset, see below
subscribedOKX = 0
#buffers Bybit
pairsBybit = []
tickerBaseBybit = {} # compare changes with this
tickerSnapshotBybit = {} # same structure as tickerBaseBybit
lastWarningBybit = {} # symbol:timestamp
time2resetBybit = {'OI':0, 'price':0, 'counter':0} # next time to reset candle
pairsMaxPriceBybit = {} # show signal only if change is better then already saved here, max is valid only for time2reset*
pairsMaxOIBybit = {} # show signal only if change is better then already saved here, max is valid only for time2reset*
msgCountBybit = {} # symbol:N coin message counter since reset, see below
subscribedBybit = 0
#buffers LIQ
lastPriceLIQ = {}


class PumpOIliquidationScreener:
	def __init__(self):
		False

	async def start(self):
		"""Start monitoring"""
		global pairsOKX, pairsOKXcontract, pairsBybit
		# get symbols
		await self.getSymbolsOKX()
		await self.getSymbolsOKXcontracts()
		await self.getSymbolsBybit()
		# subscribe and listen
		await asyncio.gather(
			self._run_exchange_websocket('OKX'),
			self._run_exchange_websocket('Bybit'),
		)

	async def _run_exchange_websocket(self, exchange: str):
		"""Exchanges Websocket connection/reconnection"""
		while True: # reconnect loop
			try:
				async with websockets.connect(websocket_URLs[exchange], ping_timeout=50) as ws: # , ping_interval=None
					await self._subscribe_to_channel(ws, exchange)
			except Exception as e:
				logger.error(f"{exchange}: Reconnect in 5s, {e}")
				await asyncio.sleep(5)

	async def _subscribe_to_channel(self, ws, exchange: str):
		"""Subscribe to a websocket"""
		global pairsOKX, pairsBybit
		if exchange == 'OKX': # note: for OKX it's 2 different channels for Price and OI
			# open interes, if not blocked
			if 'OI' in ScreenerEvents:
				await ws.send(json.dumps({ 
					"op": "subscribe",
					"args": [{"channel": "open-interest", "instType": "SWAP", "instId": symbol} for symbol in pairsOKX]
				}))
			# prices, if not blocked
			if 'Price' in ScreenerEvents:
				await ws.send(json.dumps({
					"op": "subscribe",
					"args": [{"channel": "index-tickers", "instId": symbol[:-5]} for symbol in pairsOKX] # no need -SWAP here!
				}))
			# liquidations, if not blocked
			if 'Liquidation' in ScreenerEvents:
				await ws.send(json.dumps({
					"op": "subscribe",
					"args": [{"channel": "liquidation-orders", "instType": "SWAP"}]
				}))
			await self._handle_messages_OKX(ws, exchange) # set up a message handler

		elif exchange == 'Bybit': # for Bybit
			# prices + open interes combined, if not blocked
			if 'OI' in ScreenerEvents or 'Price' in ScreenerEvents:
				await ws.send(json.dumps({ # Price and OI in same channel
					"op": "subscribe",
					"args": [f"tickers.{symbol}" for symbol in pairsBybit]
				}))
			# liquidations, if not blocked
			if 'Liquidation' in ScreenerEvents:
				await ws.send(json.dumps({ # Liquidations channel
					"op": "subscribe",
					"args": [f"allLiquidation.{symbol}" for symbol in pairsBybit]
				}))
			await self._handle_messages_Bybit(ws, exchange) # set up a message handler

# OKX section ----------------------------------------------------------------------------------
	async def getSymbolsOKX(self): # must run first!
		"""OKX: get only USDT pairs, not from blacklist, volume24 filtered"""
		global pairsOKX
		async with aiohttp.ClientSession() as session:
			async with session.get("https://www.okx.com/api/v5/market/tickers?instType=SWAP") as resp:
				data = await resp.json()
				pairsOKX = []
				for item in data["data"]:
					symbol = item["instId"].upper()
					volume_24h = float(item["volCcy24h"]) * float(item["last"]) # in USDT
					if not symbol.endswith('-USDT-SWAP') \
						or symbol[:-10] in coinBlacklist \
						or symbol[:-10] in coinBlacklistManual \
						or volume_24h<minTurnover24h:
						continue
					pairsOKX.append(symbol)

	async def getSymbolsOKXcontracts(self): # run after self.getSymbolsOKX; liquidations amount passing in contracts
		"""Get contract prices at OKX, USDT pairs, not in  coinBlacklist"""
		global pairsOKX, pairsOKXcontract
		async with aiohttp.ClientSession() as session:
			async with session.get("https://www.okx.com/api/v5/public/instruments?instType=SWAP") as resp:
				data = await resp.json()
				for item in data["data"]: # get only USDT pairs and not from blacklist
					symbol = item["instId"].upper()
					if not symbol.endswith('-USDT-SWAP') \
						or symbol not in pairsOKX: # pairsOKX counted a blackList already
						continue
					pairsOKXcontract[symbol] = (float(item["ctVal"]), item["ctValCcy"].upper())
					# then get it: ct_val, ct_ccy = pairsOKXcontract[inst_id]

	async def _handle_messages_OKX(self, ws, exchange: str):
		"""OKX websocket message handler"""
		global pairsOKX, pairsOKXcontract, msgCountOKX, subscribedOKX, tickerBaseOKX, tickerSnapshotOKX, \
			lastWarningOKX, time2resetOKX, lastPriceLIQ, pairsMaxPriceOKX, pairsMaxOIOKX, sideLIQ, \
			alertPriceCh4ShortX, stepPrice, precisionPercent
		async for message in ws:
			TGmessage = False
			msg = json.loads(message)

			if msg.get('event', '') == 'subscribe' and msg.get('connId', 0):
				if subscribedOKX==0: # show only 1 time
					logger.info(f"{exchange}: subscribed, monitoring {len(pairsOKX)} pairs")
				subscribedOKX += 1 # count message for each pair

			elif msg.get('arg', {}).get('channel') == 'liquidation-orders':
				usd_size = 0
				n = 0
				for data in msg.get('data', {}):
					symbol = data['instFamily']
					instId = data['instId']
					if instId not in pairsOKXcontract: # not supported pair
						continue
					ct_val, ct_ccy = pairsOKXcontract[instId]
					for liq in data.get('details', {}):
						side = 'long' if liq['posSide'].lower() == 'buy' else 'short'
						if (sideLIQ == 'short' and side != 'short') or (sideLIQ == 'long' and side != 'long'):
							continue # ignore wrong side
						price = float(liq['bkPx'])
						size = float(liq['sz']) # 'sz' amount in contracts
						if ct_ccy == 'USDT': # contract price in USDT - 'size' to coins
							size *= ct_val / price
						else: # contract price in coins
							size *= ct_val # now 'size' in coins
						lastPriceLIQ[symbol] = price
						# summ size in USDT
						usd_size += size * price
						n += 1
					# fire a message
					if usd_size >= minLIQsizeUSD:
						URL = f"https://www.okx.com/ru/trade-swap/{symbol.lower()}-swap"
						cgURL = f"https://www.coinglass.com/tv/ru/OKX_{symbol.upper()}-SWAP"
						precision = 0 if price>=10000 else 1 if price>=1000 else 6 if price<0.0001 else 4
						sideR = 'short' if side == 'long' else 'long' # reverse mark color
						linkText = f"{sideMark[sideR]}{symbol[:-5]}"
						price_str = f"{price:.{precision}f}"
						nMark = f" 🧍{n}" if n > 1 else ''
						TGmessage = self._format_telegram_message('LIQ', exchange, URL, cgURL, linkText, price_str, megaKilo(usd_size), '$', nMark, '', '')

			elif msg.get('arg', {}).get('channel') == 'index-tickers':
				for data in msg.get('data', {}):
					symbol = data.get('instId', '') # note: THERE IS NO "-SWAP" tail here!
					price = data.get('idxPx', '')
					ts = int(int(data.get("ts", 0))/1000) # now in seconds

					# init tickerSnapshotOKX and lastWarningOKX
					if symbol not in tickerSnapshotOKX:
						tickerSnapshotOKX[symbol] = {}
						lastWarningOKX[symbol] = {'OI':0, 'price':0}
					tickerSnapshotOKX[symbol]['lastPrice'] = price

					# init tickerBase on 1st run
					if symbol not in tickerBaseOKX:
						tickerBaseOKX[symbol] = dict(tickerSnapshotOKX[symbol])

					# init pairsMax
					if symbol not in pairsMaxPriceOKX:
						pairsMaxPriceOKX[symbol] = -1.

					# IS IT TIME TO RENEW counters and candles (each screener can has its own timeframe!)
					#	for counter
					if ts>=time2resetOKX['counter']:
						msgCountOKX = {} # reset counter
						pairsMaxPriceOKX = {}
						time2resetOKX['counter'] = int(ts - (ts % timeframeMsgCntOKX) + timeframeMsgCntOKX) # next reset
					#	for Price
					if ts>=time2resetOKX['price']:
						tickerBaseOKX[symbol]['lastPrice'] = str(tickerSnapshotOKX[symbol]['lastPrice'])
						time2resetOKX['price'] = int(ts - (ts % timeframePrice) + timeframePrice) # next reset

					# check Price changes:
					priceBase = float(tickerBaseOKX[symbol]["lastPrice"])
					price = float(tickerSnapshotOKX[symbol]["lastPrice"])
					precision = 0 if price>=10000 else 1 if price>=1000 else 6 if price<0.0001 else 4
					priceChange = round(100 * (price - priceBase) / priceBase, precisionPercent)
#					priceChange = 100 * (price - priceBase) / priceBase
					priceChangeSign = sideMark['long'] if priceChange>0 else sideMark['short']
					priceChangeSignTxt = '+' if priceChange>0 else '-'
					x = 1. if priceChange >= 0 else alertPriceCh4ShortX # implement different settings for SHORT
					if not longOnlyPrice: # both sides
						priceChange = abs(priceChange)
					if priceChange >= x * alertPriceChange \
						and ts - lastWarningOKX[symbol]['price'] >= timeframePrice \
						and priceChange > pairsMaxPriceOKX[symbol]:
						if symbol not in msgCountOKX:
							msgCountOKX[symbol] = 0
						elif priceChange < pairsMaxPriceOKX[symbol] + stepPrice:
							continue # not big enough
						counter = msgCountOKX[symbol] = msgCountOKX[symbol] + 1
						pairsMaxPriceOKX[symbol] = priceChange # may be abs
						lastWarningOKX[symbol]['price'] = ts # omly 1 messsage in timeframePrice
						# fire notification message
						if counter <= maxMsgSameCoin:
							URL = f"https://www.okx.com/ru/trade-swap/{symbol.lower()}-swap"
							cgURL = f"https://www.coinglass.com/tv/ru/OKX_{symbol.upper()}-SWAP"
							linkText = f"{sideMark['long'] if priceChangeSignTxt == '+' else sideMark['short']}{symbol[:-5]}"
							price_str = f"{price:.{precision}f}"
							TGmessage = self._format_telegram_message('PR', exchange, URL, cgURL, linkText, price_str, f"{priceChange:.{precisionPercent}f}", priceChangeSignTxt, counter)

			elif msg.get('arg', {}).get('channel') == 'open-interest':
				for data in msg.get('data', {}):
					symbol = data.get('instId', '') # "-USDT-SWAP" tail here
					oi = data.get('oi', '')
					ts = int(int(data.get("ts", 0))/1000) # now in seconds

					# init tickerSnapshotOKX and lastWarningOKX
					if symbol not in tickerSnapshotOKX:
						tickerSnapshotOKX[symbol] = {}
						lastWarningOKX[symbol] = {'OI':0, 'price':0}
					tickerSnapshotOKX[symbol]['openInterest'] = oi

					# init tickerBase on 1st run
					if symbol not in tickerBaseOKX:
						tickerBaseOKX[symbol] = dict(tickerSnapshotOKX[symbol])

					# init pairsMax
					if symbol not in pairsMaxOIOKX:
						pairsMaxOIOKX[symbol] = -1.

					# IS IT TIME TO RENEW counters and candles (each screener can has its own timeframe!)
					#	for counter
					if ts>=time2resetOKX['counter']:
						msgCountOKX = {} # reset counter
						pairsMaxOIOKX = {}
						time2resetOKX['counter'] = int(ts - (ts % timeframeMsgCntOKX) + timeframeMsgCntOKX) # next reset
					#	for Open Interest
					if ts>=time2resetOKX['OI']:
						tickerBaseOKX[symbol]['openInterest'] = str(tickerSnapshotOKX[symbol]['openInterest'])
						time2resetOKX['OI'] = int(ts - (ts % timeframeOI) + timeframeOI) # next reset

					# check OI changes:
					oiBase = float(tickerBaseOKX[symbol]['openInterest'])
					oi = float(tickerSnapshotOKX[symbol]['openInterest'])
					precision = 1
					oiChange = round(100 * (oi - oiBase) / oiBase, precisionPercent)
#					oiChange = 100 * (oi - oiBase) / oiBase
					oiChangeSign = sideMark['long'] if oiChange>0 else sideMark['short']
					oiChangeSignTxt = '+' if oiChange>0 else '-'
					if not longOnlyOI:
						oiChange = abs(oiChange)
					if oiChange >= alertOIchange \
						and ts - lastWarningOKX[symbol]['OI'] >= timeframeOI \
						and oiChange > pairsMaxOIOKX[symbol]:
						if symbol not in msgCountOKX:
							msgCountOKX[symbol] = 0
						counter = msgCountOKX[symbol] = msgCountOKX[symbol] + 1
						pairsMaxOIOKX[symbol] = oiChange
						lastWarningOKX[symbol]['OI'] = ts
						# fire notification message
						if counter <= maxMsgSameCoin:
							URL = f"https://www.okx.com/ru/trade-swap/{symbol.lower()}"
							cgURL = f"https://www.coinglass.com/tv/ru/OKX_{symbol.upper()}"
							linkText = f"{sideMark['long'] if oiChangeSignTxt == '+' else sideMark['short']}{symbol[:-10]}"
							oi_str = megaKilo(oi)
							TGmessage = self._format_telegram_message('OI', exchange, URL, cgURL, linkText, oi_str, f"{oiChange:.{precisionPercent}f}", oiChangeSignTxt, counter)

			# send a notification (if not empty)
			await self._notify(TGmessage)


# Bybit section --------------------------------------------------------------------------------
	async def getSymbolsBybit(self):
		"""Bybit: get only USDT pairs, not from blacklist and volume24 filtered"""
		global pairsBybit
		async with aiohttp.ClientSession() as session:
			async with session.get("https://api.bybit.com/v5/market/tickers?category=linear") as resp:
				data = await resp.json()
				pairsBybit = []
				for item in data["result"]["list"]:
					symbol = item["symbol"].upper()
					volume_24h = float(item["turnover24h"]) # in USDT
					if not symbol.endswith('USDT') \
						or symbol[:-4] in coinBlacklist \
						or symbol[:-4] in coinBlacklistManual \
						or volume_24h<minTurnover24h:
						continue
					pairsBybit.append(symbol)


	async def _handle_messages_Bybit(self, ws, exchange: str):
		"""Bybit websocket message handler"""
		global pairsBybit, msgCountBybit, subscribedBybit, tickerBaseBybit, tickerSnapshotBybit, \
			lastWarningBybit, time2resetBybit, lastPriceLIQ, minLIQsizeUSD, sideLIQ, pairsMaxPriceBybit, \
			pairsMaxOIBybit, alertPriceCh4ShortX, stepPrice, precisionPercent
		async for message in ws:
			TGmessage = False
			msg = json.loads(message)

			if msg.get('op', '') == 'subscribe':
				if subscribedBybit==0: # show only 1 time
					logger.info(f"{exchange}: subscribed, monitoring {len(pairsBybit)} pairs")
				subscribedBybit += 1 # for each pair

			elif msg.get('topic', '').startswith('allLiquidation'):
				ts = int(int(msg.get("ts", 0))/1000) # now in seconds
				data = msg.get("data", [])
				usd_size = 0
				n = 0
				for liq in data:
					symbol = liq['s']
					side = 'long' if liq['S'].lower() == 'buy' else 'short'
					if (sideLIQ == 'short' and side != 'short') or (sideLIQ == 'long' and side != 'long'):
						continue # ignore wrong side
					size = float(liq['v'])
					price = float(liq['p'])
					lastPriceLIQ[symbol] = price
					# summ volume in USDT
					usd_size += size * price
					n += 1
				# fire a message
				if usd_size >= minLIQsizeUSD:
					URL = f"https://www.bybit.com/trade/usdt/{symbol}"
					cgURL = f"https://www.coinglass.com/tv/ru/Bybit_{symbol.upper()}"
					precision = 0 if price>=10000 else 1 if price>=1000 else 6 if price<0.0001 else 4
					#sideR = 'short' if side == 'long' else 'long' # reverse mark color
					linkText = f"{sideMark[side]}{symbol[:-4]}"
					price_str = f"{price:.{precision}f}"
					nMark = f" 🧍{n}" if n > 1 else ''
					TGmessage = self._format_telegram_message('LIQ', exchange, URL, cgURL, linkText, price_str, megaKilo(usd_size), '$', nMark, '', '')

			elif msg.get('topic', '').startswith('tickers.'):
				# note: This topic utilises the snapshot field and delta field,
				# if a response param is not found in the message, then its value has not changed.
				ts = int(int(msg.get("ts", 0))/1000) # in seconds
				data = msg.get("data", [])

				if data and msg.get('type', '') in ['snapshot', 'delta']:
					symbol = data['symbol']

					# init tickerSnapshot and lastWarning
					if symbol not in tickerSnapshotBybit:
						tickerSnapshotBybit[symbol] = {}
						lastWarningBybit[symbol] = {'OI':0, 'price':0}
					# update parms in tickerSnapshot
					for parm in [ 'lastPrice', 'openInterestValue']: # 'nextFundingTime','fundingRate'
						if parm in data:
							tickerSnapshotBybit[symbol][parm] = data[parm]

					# init tickerBase on 1st run
					if symbol not in tickerBaseBybit:
						tickerBaseBybit[symbol] = dict(tickerSnapshotBybit[symbol])

					# init pairsMax
					if symbol not in pairsMaxPriceBybit:
						pairsMaxPriceBybit[symbol] = -1.

					# init pairsMax
					if symbol not in pairsMaxOIBybit:
						pairsMaxOIBybit[symbol] = -1.

					# IS IT TIME TO RENEW counters and candles (each screener can has its own timeframe!)
					#	for counter
					if ts>=time2resetBybit['counter']:
						msgCountBybit = {} # reset counter
						pairsMaxPriceBybit = {}
						pairsMaxOIBybit = {}
						time2resetBybit['counter'] = int(ts - (ts % timeframeMsgCntBybit) + timeframeMsgCntBybit) # next reset
					#	for Price
					if ts>=time2resetBybit['price']:
						tickerBaseBybit[symbol]['lastPrice'] = str(tickerSnapshotBybit[symbol]['lastPrice'])
						time2resetBybit['price'] = int(ts - (ts % timeframePrice) + timeframePrice) # next reset
					#	for Open Interest
					if ts>=time2resetBybit['OI']:
						tickerBaseBybit[symbol]['openInterestValue'] = str(tickerSnapshotBybit[symbol]['openInterestValue'])
						time2resetBybit['OI'] = int(ts - (ts % timeframeOI) + timeframeOI) # next reset

					# check Price changes:
					if 'Price' in ScreenerEvents:
						priceBase = float(tickerBaseBybit[symbol]["lastPrice"])
						price = float(tickerSnapshotBybit[symbol]["lastPrice"])
						precision = 0 if price>=10000 else 1 if price>=1000 else 6 if price<0.0001 else 4
						priceChange = round(100 * (price - priceBase) / priceBase, precisionPercent) # fixed precision
#						priceChange = 100 * (price - priceBase) / priceBase
						priceChangeSign = sideMark['long'] if priceChange>0 else sideMark['short']
						priceChangeSignTxt = '+' if priceChange>0 else '-'
						x = 1. if priceChange >= 0 else alertPriceCh4ShortX # implement different settings for SHORT
						if not longOnlyPrice:
							priceChange = abs(priceChange)
						if priceChange >= x * alertPriceChange \
							and ts - lastWarningBybit[symbol]['price'] >= timeframePrice \
							and priceChange > pairsMaxPriceBybit[symbol]:
							if symbol not in msgCountBybit:
								msgCountBybit[symbol] = 0
							elif priceChange < pairsMaxPriceBybit[symbol] + stepPrice:
								continue # not big enough
							counter = msgCountBybit[symbol] = msgCountBybit[symbol] + 1
							pairsMaxPriceBybit[symbol] = priceChange # may be abs
							lastWarningBybit[symbol]['price'] = ts
							# fire notification message
							if counter <= maxMsgSameCoin:
								URL = f"https://www.bybit.com/trade/usdt/{symbol}"
								cgURL = f"https://www.coinglass.com/tv/ru/Bybit_{symbol.upper()}"
								linkText = f"{sideMark['long'] if priceChangeSignTxt == '+' else sideMark['short']}{symbol[:-4]}"
								price_str = f"{price:.{precision}f}"
								TGmessage = self._format_telegram_message('PR', exchange, URL, cgURL, linkText, price_str, f"{priceChange:.{precisionPercent}f}", priceChangeSignTxt, counter)

					# check OI changes:
					if 'OI' in ScreenerEvents:
						oiBase = float(tickerBaseBybit[symbol]["openInterestValue"])
						oi = float(tickerSnapshotBybit[symbol]["openInterestValue"])
						oiChange = round(100 * (oi - oiBase) / oiBase, precisionPercent)
#						oiChange = 100 * (oi - oiBase) / oiBase
						oiChangeSign = sideMark['long'] if oiChange>0 else sideMark['short']
						oiChangeSignTxt = '+' if oiChange>0 else '-'
						if not longOnlyOI:
							oiChange = abs(oiChange)
						if oiChange >= alertOIchange \
							and ts - lastWarningBybit[symbol]['OI'] >= timeframeOI \
							and oiChange > pairsMaxOIBybit[symbol]:
							if symbol not in msgCountBybit:
								msgCountBybit[symbol] = 0
							counter = msgCountBybit[symbol] = msgCountBybit[symbol] + 1
							pairsMaxOIBybit[symbol] = oiChange
							lastWarningBybit[symbol]['OI'] = ts
							# fire notification message
							if counter <= maxMsgSameCoin:
								URL = f"https://www.bybit.com/trade/usdt/{symbol}"
								cgURL = f"https://www.coinglass.com/tv/ru/Bybit_{symbol.upper()}"
								linkText = f"{sideMark['long'] if oiChangeSignTxt == '+' else sideMark['short']}{symbol[:-4]}"
								oi_str = megaKilo(oi)
								TGmessage = self._format_telegram_message('OI', exchange, URL, cgURL, linkText, oi_str, f"{oiChange:.{precisionPercent}f}", oiChangeSignTxt, counter)

			# send notification if not empty
			await self._notify(TGmessage)


# notification section --------------------------------------------------------------------------------
	def _format_telegram_message(self, mode, exchange, URL, cgURL, linkText, val, change, changeSign, counter, counterMark=' #', changeMark='%'):
		"""Telegram message template"""
		mode = signalIcon.get(mode, mode) # icon look
		# return f"<b>{mode}</b><a href='{URL}'>{exchangeMark[exchange] if exchange in exchangeMark else exchangeMark['none']}{exchange}</a> " + \
		return f"<a href='{URL}'>{mode}{exchange}</a> " + \
			f"<a href='{cgURL}'>{linkText}</a><code>:{val}</code> " + \
			f"<b>{changeSign}{change}{changeMark}</b><code>{counterMark}{counter}</code>"

	async def _notify(self, TGmessage:str):
		"""Send Telegram message"""
		if TGmessage:
			# telegram
			if useTelegram and TMchatID:
				send_to_telegram(TMapiToken, TMchatID, TGmessage.strip(), preview=False)
			# записать для истории
			stripTGmessage = re.sub(re.compile('<.*?>'), '', TGmessage).strip()
			curtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
			with open(longLogFile, "a", encoding='utf-8') as _logfile:
				_logfile.write(f"\n{curtime} - {stripTGmessage}")
			# logger
			logger.warn(stripTGmessage) # see custom method in main


async def main():
	monitor = PumpOIliquidationScreener()
	await monitor.start()


def get_topcap_cryptos(n=100):
	"""Get TopCap-N from Coingecko"""
	# note: a list will include stables: USDT USDC USDS USDE DAI etc
	url = "https://api.coingecko.com/api/v3/coins/markets"
	params = {
		"vs_currency": "usd",
		"order": "market_cap_desc",
		"per_page": n+5,
		"page": 1,
		"sparkline": "false"
	}
	response = requests.get(url, params=params)
	if response.status_code != 200:
		raise Exception(f"Error fetching data from coingecko.com: {response.status_code}")
	data = response.json()
	symbols = []
	for i, coin in enumerate(data, 1):
		symbols.append(coin['symbol'].upper())
	return symbols

def tooYoungSymbolsBybit(minLifeTime):
	"""Get too young coins from Bybit, OKX has no similar"""
	maxLaunchTime = int(time.time()) - minLifeTime
	url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
	response = requests.get(url)
	if response.status_code != 200:
		raise Exception(f"Error fetching instruments data from bybit.com: {response.status_code}")
	data = response.json()
	for item in data['result']['list']:
		symbol = item["symbol"].upper()[:-4] # no USDT tail
		if int(item["launchTime"])/1000 > maxLaunchTime and symbol not in coinBlacklist:
			coinBlacklist.append(symbol)


def thousands(n):
	"""Format number 1222333.2 to string 1'222'333"""
	if n >= 1000.:
		return f"{n:,.0f}".replace(',', "'")
	else:
		return f"{n}"

def megaKilo(n):
	"""Format number 1_222_333 to string 1.22M"""
	if n >= 1_000_000_000.:
		return f"{round(n/1_000_000_000., 2)}B"
	elif n >= 10_000_000.:
		return f"{round(n/1_000_000., 1)}M"
	elif n >= 1_000_000.:
		return f"{round(n/1_000_000., 2)}M"
	elif n >= 10_000.:
		return f"{round(n/1000., 1)}k"
	elif n >= 1000.:
		return f"{round(n/1000., 2)}k"
	else:
		return f"{n}"


if __name__ == "__main__":
	try:
		# we can start as cron script or application link - change to current dir
		os.chdir(os.path.dirname(os.path.abspath(__file__)))

		# clear screen
		os.system('clear')

		# setup logger
		if os.path.exists(loggerFile):
			os.remove(loggerFile)
		# upgrade logger: WARN instead of WARNING
		LOGGER_WARN_LEVEL = 31 # higher than WARNING=30
		logging.addLevelName(LOGGER_WARN_LEVEL, 'WARN')
		def logging_warn(self, message, *args, **kwargs):
			if self.isEnabledFor(LOGGER_WARN_LEVEL):
				self._log(LOGGER_WARN_LEVEL, message, args, **kwargs)
		logging.Logger.warn = logging_warn
		logging.basicConfig(
			level=logging.INFO,
			format='%(asctime)s - %(levelname)s - %(message)s',
			datefmt="%Y-%m-%d %H:%M:%S",
			handlers=[
				logging.FileHandler(loggerFile),
				logging.StreamHandler()
			]
		)
		logger = logging.getLogger(__name__)

		# print start message
		logger.info(f"START Pump/OI/LIQ Screener, Ignore Top{marketCapTop} Cap")
		if 'Price' in ScreenerEvents:
			logger.info(f"Setting Pump: {alertPriceChange:.1f}% / {timeframePrice}s, Mode: {'LONG only' if longOnlyPrice else 'LONG/SHORT'}")
		if 'OI' in ScreenerEvents:
			logger.info(f"Setting OI: {alertOIchange:.1f}% / {timeframeOI}s")
		if 'Liquidation' in ScreenerEvents:
			logger.info(f"Setting Min Liquidation: ${megaKilo(minLIQsizeUSD)}, Mode: {sideLIQ.upper()}")

		# get top50-cap to blacklist
		coinBlacklist = get_topcap_cryptos(marketCapTop)
		# add too young coins to blacklist
		tooYoungSymbolsBybit(minLifeTime)

		# ...and show time!
		asyncio.get_event_loop().run_until_complete(main())

	except KeyboardInterrupt:
		print('\r', end='')
		logger.info("STOP")

# that's all folks!