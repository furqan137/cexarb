# Crypto Arbitrage Trading Bot

A Python-based cryptocurrency arbitrage trading bot that identifies and executes profitable trades across multiple exchanges.

## Features

- **Exchange Arbitrage**: Trade between different exchanges (Kraken ↔ Binance)
- **Triangular Arbitrage**: Trade within a single exchange using three currency pairs
- **Mock Mode**: Test strategies without real trades

## Prerequisites

- Python >2.7 (Note: This project uses Python 2.7 syntax)
- pip (Python package manager)

## Installation

### 1. Clone or Extract the Project

\`\`\`bash
cd cex_arb_bot
\`\`\`

### 2. Install Python Dependencies

\`\`\`bash
python3.10 -m venv .venv
. .venv/bin/activate
pip install -r requirments.txt
\`\`\`

### 3. Configure API Keys

Create API key files for each exchange you want to use in the `keys/` directory (already created!):

**For Kraken** (`keys/kraken.key`):
\`\`\`json

{
    "exchange": "kraken",
    "public": "YOUR_KRAKEN_API_KEY+LuUHwehhMuJT45",
    "private": "YOUR_KRAKEN_API_SECRET"
}

\`\`\`

**For Binance** (`keys/binance.key`):
\`\`\`json
{
    "exchange": "binance",
    "public": "YOUR_BINANCE_API_KEY",
    "private": "YOUR_BINANCE_API_SECRET"
}
\`\`\`

**Important Security Notes:**
- Never commit API keys to version control
- Use API keys with trading permissions only if you plan to execute real trades
- For testing, use mock mode (no API keys needed)
- Consider using API keys with IP restrictions and withdrawal disabled

### 4. Configure Trading Parameters

Edit `arbitrage_config.json` to set your trading parameters:

\`\`\`json
{
    "exchange": {
        "exchangeA": {
            "exchange": "kraken",
            "keyFile": "keys/kraken.key",
            "tickerPair": "XRPUSDT",
            "tickerA": "USDT",
            "tickerB": "XXRP"
        },
        "exchangeB": {
            "exchange": "binance",
            "keyFile": "keys/binance.key",
            "tickerPair": "XRPUSDT",
            "tickerA": "USDT",
            "tickerB": "XRP"
        }
    }
}
\`\`\`

## Usage

### Running Exchange Arbitrage (Kraken ↔ Binance)

**Production Mode (Real Trading):**
\`\`\`bash
python main.py --mode exchange --production
\`\`\`


**Mock Mode (Recommended for Testing):**
\`\`\`bash
python main.py --mode exchange
\`\`\`

### Running Triangular Arbitrage

**Mock Mode:**
\`\`\`bash
python main.py --mode triangular
\`\`\`

**Production Mode:**
\`\`\`bash
python main.py --mode triangular --production
\`\`\`

### Testing Directly from exchange_arbitrage.py

You can also test the XRP/USDT arbitrage directly:

\`\`\`bash
cd engines
python exchange_arbitrage.py
\`\`\`

This will run the bot in mock mode with the configuration specified in the `__main__` section.

## Command Line Arguments

- `-m, --mode`: Arbitrage mode (`exchange` or `triangular`) - **Required**
- `-p, --production`: Enable production mode (real trading) - **Optional**

## Project Structure

\`\`\`
cryptoarbitrage/
├── main.py                          # Entry point
├── arbitrage_config.json            # Configuration file
├── engines/
│   ├── exchange_arbitrage.py        # Exchange arbitrage engine
│   ├── triangular_arbitrage.py      # Triangular arbitrage engine
│   └── exchanges/
│       ├── base.py                  # Base exchange class
│       ├── kraken.py                # Kraken implementation
│       ├── binance.py               # Binance implementation
│       ├── bitfinex.py              # Bitfinex implementation
│       ├── bitstamp.py              # Bitstamp implementation
│       ├── bittrex.py               # Bittrex implementation
│       ├── gatecoin.py              # Gatecoin implementation
│       └── loader.py                # Exchange loader
└── keys/
    ├── kraken.key                   # Kraken API credentials
    ├── binance.key                  # Binance API credentials
    └── *.key_sample                 # Sample key files
\`\`\`

## Safety Features

- **Mock Mode**: Test strategies without executing real trades
- **Balance Checks**: Ensures sufficient funds before placing orders
- **Open Order Monitoring**: Tracks and manages open orders
- **Exception Handling**: Gracefully handles API errors
- **Minimum Balance**: Prevents trading with insufficient funds (< 0.05)

### API Connection Issues
- Verify API keys are correct
- Check if your IP is whitelisted (if required)
- Ensure API keys have necessary permissions

### Balance Issues
- Ensure you have sufficient balance on both exchanges
- Check minimum balance requirements (> 0.05)

## Disclaimer

**USE AT YOUR OWN RISK**

Cryptocurrency trading carries significant risk. This software is provided as-is without any guarantees. The authors are not responsible for any financial losses incurred through the use of this software. Always test thoroughly in mock mode and start with small amounts.

## License

See LICENSE file for details.
