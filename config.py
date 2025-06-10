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


ScreenerEvents = [ # screen these events, comment out to block
	'OI',
	'Price',
	'Liquidation'
]

coinBlacklistManual = [ # manually added to ignore
	'ALCH',
]

websocket_URLs = {
	'OKX':		'wss://ws.okx.com:8443/ws/v5/public',
	'Bybit':	'wss://stream.bybit.com/v5/public/linear'
}

longLogFile = 'logs/pump-oi-liquidations_history.log' # all time log
loggerFile  = 'logs/pump-oi-liquidations.log' # session log

marketCapTop = 30 # blacklist these coins by Capitalization
minTurnover24h = 1_500_000. # min 24h volume >$1000/мин (lower subscriptions number)
minLifeTime = 30*24*3600 # ignore too young coins

# Pump settings
longOnlyPrice = False # if False will monitor Higher and Lower
timeframePrice = 120 # 2min, track Price change in last N seconds (candle size)
alertPriceChange = 2.5 # 2. # percents ### 1 message in timeframe!
alertPriceCh4ShortX = 1.5 # x2 for SHORT, recommended: 10% in 20m

# OI settings
longOnlyOI = True # if False will monitor Higher and Lower
timeframeOI = 900 # 15min, track OI change in last N seconds (candle size)
alertOIchange = 6. # 5% min

# both OI/Price
timeframeMsgCntOKX = 3_600 # each N seconds reset the counter
timeframeMsgCntBybit = 3_600 # each N seconds reset the counter
maxMsgSameCoin = 10 # show only firts N messags on same coin at same exchange

# LIQ settings
minLIQsizeUSD = 20_000  # min liq sixe, 15k+, USD
sideLIQ = 'short' # 'short' / 'long' / 'long/short'

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
	'OKX':		'🔵',
	'Bybit':	'🟠',
	'none':		'⚫'
}
sideMark = {
	'long':		'🟢', # '🔺', # '⚪',
	'short':	'🔴', # '🔻', # '⚫',
}


if __name__ == '__main__':
	print(globals()['__doc__'])

