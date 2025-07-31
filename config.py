#!/usr/bin/env python3
"""\
Pump / Open Interest / Liquidations Screener

Main config
"""

__project__	= "Pump / Open Interest / Liquidations Screener"
__part__	= "Main config"
__author__	= "Sergey V Musenko"
__email__	= "sergey@musenko.com"
__copyright__= "© 2025, musenko.com"
__license__	= "MIT"
__credits__	= ["Sergey Musenko"]
__date__	= "2025-05-31"
__version__	= "0.2"
__status__	= "dev"

Exchanges = [
#	'OKX',
	'Bybit',
	'BingX',
]

ScreenerEvents = [ # screen these events, comment out to block
	'OI',
	'Price',
	'Liquidation'
]

coinBlacklistManual = [ # manually added to ignore
	'ALCH', 'AVAAI', 'GORK', 'USELESS',
]

websocket_URLs = {
	'BingX':	'wss://open-api-swap.bingx.com/swap-market',
	'OKX':		'wss://ws.okx.com:8443/ws/v5/public',
	'Bybit':	'wss://stream.bybit.com/v5/public/linear'
}

longLogFile = 'logs/pump-oi-liquidations_history.log' # all time log
loggerFile  = 'logs/pump-oi-liquidations.log' # session log

marketCapTop = 3 # blacklist these coins by Capitalization
minTurnover24h = 1_500_000. # min 24h volume >$1000/мин (lower subscriptions number)
minLifeTime = 30*24*3600 # ignore too young coins

precisionPercent = 1 # show percents with this precision: "99.9%"

# Pump settings
longOnlyPrice = True # if False will monitor Higher and Lower
timeframePrice = 120 # 2min, track Price change in last N seconds (candle size)
alertPriceChange = 2.5 # 2. # percents ### 1 message in timeframe!
alertPriceCh4ShortX = 1.6 # x2 for SHORT, recommended: 10% in 20m
stepPrice = 0.3 # show if 2+ signal change >=

# OI settings
longOnlyOI = True # if False will monitor Higher and Lower
timeframeOI = 900 # 15min, track OI change in last N seconds (candle size)
alertOIchange = 8. # 5% min

# both OI/Price
timeframeMsgCntBingX = 3_600 # each N seconds reset the counter
timeframeMsgCntOKX = 3_600 # each N seconds reset the counter
timeframeMsgCntBybit = 3_600 # each N seconds reset the counter
maxMsgSameCoin = 10 # show only firts N messags on same coin at same exchange

# LIQ settings
minLIQsizeUSD = 30_000  # min liq sixe, 15k+, USD
sideLIQ = 'both' # 'short' / 'long' / 'long/short'

# notify via Telegram bot: Trading Monitor '@lightytrading_bot'
useTelegram = True
TMapiToken	= '' # '' means do not send
TMchatID	= '' # to user personally, '' means DO NOT SEND

# some layout
signalIcon = {
	'PR':		'📊', # 'PR'
	'OI':		'🔍', # 'OI'
	'LIQ':		'🔥', # 'LIQ'
}
exchangeMark = {
	'BingX':	'🔵',
	'OKX':		'⚫',
	'Bybit':	'🟠',
	'none':		'⚪'
}
sideMark = {
	'long':		'🟢', # '🔺', # '⚪',
	'short':	'🔴', # '🔻', # '⚫',
}


if __name__ == '__main__':
	print(globals()['__doc__'])

