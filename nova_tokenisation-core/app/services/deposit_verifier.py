"""
Layer 3 deposit verifier.

Given a tx hash + a token contract, verify that the transaction
contains a Transfer event matching (from, to, amount).

Used by /fund to prove an on-chain deposit actually happened
before the escrow order advances state.
"""
import os
from typing import Optional
from web3 import Web3

BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")

ERC20_TRANSFER_EVENT_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]


class DepositVerifier:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))

    def verify_transfer(
        self,
        tx_hash: str,
        token_contract: str,
        expected_from: str,
        expected_to: str,
        expected_amount_whole: float,
    ) -> tuple[bool, Optional[str]]:
        """
        Returns (ok, reason). If ok, the receipt contains a matching
        ERC-20 Transfer event. If not, reason describes the failure.
        """
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        except Exception as e:
            return False, f"tx not found: {e}"

        if receipt is None:
            return False, "tx not found on chain"

        if receipt.status != 1:
            return False, "tx status is not success"

        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_contract),
            abi=ERC20_TRANSFER_EVENT_ABI,
        )

        expected_raw = int(round(expected_amount_whole * 10 ** 18))
        from_lower = expected_from.lower()
        to_lower = expected_to.lower()

        for log in contract.events.Transfer().process_receipt(receipt):
            if (
                log.args["from"].lower() == from_lower
                and log.args["to"].lower() == to_lower
                and int(log.args["value"]) == expected_raw
            ):
                return True, None

        # No matching transfer
        seen = [
            f"{l.args['from'][:10]}→{l.args['to'][:10]} {int(l.args['value']) / 10**18}"
            for l in contract.events.Transfer().process_receipt(receipt)
        ]
        return False, f"no matching transfer; events: {seen}"


deposit_verifier = DepositVerifier()
