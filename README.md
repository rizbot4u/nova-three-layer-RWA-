# Nova Three-Layer RWA Settlement Architecture

**Live on Base Mainnet (Chain ID: 8453)**

This repository contains the full stack for the Nova Global Keys institutional RWA platform.

## Architecture
- **Layer 1 (Identity & Compliance):** FastAPI + PostgreSQL + Telegram Bot
- **Layer 2 (Tokenization):** Permissioned ERC-20 (NVP-1) with on-chain whitelisting
- **Layer 3 (Atomic Settlement):** Single-transaction DvP Settlement Engine

## Live Proof
- **Atomic Settlement Tx:** [0x7017224fb1fcfe285844aed13dcfe0dc50d7226f3303df2f268fa77700143ede](https://basescan.org/tx/0x7017224fb1fcfe285844aed13dcfe0dc50d7226f3303df2f268fa77700143ede)
- **Settlement Contract:** [0xB850729c96e7eC7e38bf188a6392F44602C96e4F](https://basescan.org/address/0xB850729c96e7eC7e38bf188a6392F44602C96e4F)
