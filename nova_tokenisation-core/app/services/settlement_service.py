"""
Layer 3 settlement service.

Signs + broadcasts ERC-20 transfers from the treasury wallet on
Base Mainnet, and waits for the receipt before returning a hash.

Environment:
  BASE_RPC_URL              — Base Mainnet RPC (defaults to public)
  TREASURY_PRIVATE_KEY      — 0x-prefixed hex signing key
  TREASURY_WALLET_ADDRESS   — optional; derived from the key if unset
"""
import os
from web3 import Web3

BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
CHAIN_ID = 8453  # Base Mainnet

ERC20_TRANSFER_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    }
]


class SettlementService:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
        self.private_key = os.getenv("TREASURY_PRIVATE_KEY", "")
        if self.private_key:
            if not self.private_key.startswith("0x"):
                self.private_key = "0x" + self.private_key
            self.treasury = self.w3.eth.account.from_key(self.private_key).address
        else:
            self.treasury = os.getenv("TREASURY_WALLET_ADDRESS", "")

    def is_configured(self) -> bool:
        return bool(self.private_key) and bool(self.treasury)

    def send_token(
        self,
        token_contract: str,
        to_wallet: str,
        amount_whole_tokens: float,
    ) -> str:
        """
        Send `amount_whole_tokens` of the ERC-20 at `token_contract`
        from the treasury to `to_wallet`. Scales to 18 decimals
        internally. Waits for receipt. Raises on revert.

        Returns the tx hash (hex).
        """
        if not self.is_configured():
            raise RuntimeError("Treasury key not configured")

        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_contract),
            abi=ERC20_TRANSFER_ABI,
        )

        raw_amount = int(round(float(amount_whole_tokens) * 10 ** 18))

        nonce = self.w3.eth.get_transaction_count(self.treasury)
        gas_price = self.w3.eth.gas_price

        txn = contract.functions.transfer(
            Web3.to_checksum_address(to_wallet),
            raw_amount,
        ).build_transaction({
            "chainId": CHAIN_ID,
            "gas": 150_000,
            "gasPrice": gas_price,
            "nonce": nonce,
        })

        signed = self.w3.eth.account.sign_transaction(
            txn, private_key=self.private_key
        )
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        # Only declare success after the chain confirms.
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError(
                f"Token transfer reverted on-chain: {self.w3.to_hex(tx_hash)}"
            )

        return self.w3.to_hex(tx_hash)


settlement_service = SettlementService()
