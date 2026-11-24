import json
import os
from pathlib import Path
from typing import Any, Dict
from web3 import Web3

DVP_V2_ADDRESS = Web3.to_checksum_address(
    os.getenv("DVP_V2_ADDRESS", "0xB850729c96e7eC7e38bf188a6392F44602C96e4F")
)
DEFAULT_ABI_PATH = Path(__file__).with_name("NovaDvPSettlementV2.abi.json")


def order_id_to_bytes32(order_id: str | bytes) -> bytes:
    """Convert a string order ID (or 32-byte value) into a bytes32 digest."""
    if isinstance(order_id, bytes):
        if len(order_id) == 32:
            return order_id
        return Web3.keccak(order_id)
    raw = order_id.strip()
    if raw.startswith("0x") and len(raw) == 66:
        return bytes.fromhex(raw[2:])
    return Web3.keccak(text=raw)


class NovaDvPV2Client:
    def __init__(
        self,
        rpc_url: str | None = None,
        contract_address: str = DVP_V2_ADDRESS,
        abi_path: Path = DEFAULT_ABI_PATH,
        relayer_private_key: str | None = None,
    ):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or os.getenv("BASE_RPC_URL", "https://mainnet.base.org")))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Base RPC")

        self.address = Web3.to_checksum_address(contract_address)
        abi = json.loads(Path(abi_path).read_text())
        self.contract = self.w3.eth.contract(address=self.address, abi=abi)
        self.relayer_private_key = relayer_private_key or os.getenv("DVP_RELAYER_PRIVATE_KEY")

    def is_settled(self, order_id: str | bytes) -> bool:
        return bool(self.contract.functions.isSettled(order_id_to_bytes32(order_id)).call())

    def preview(
        self,
        order_id: str | bytes,
        buyer: str,
        seller: str,
        dkhyr_amount_wei: int,
        share_amount_wei: int,
    ) -> Dict[str, Any]:
        ok, reason, b_bal, b_allow, s_bal, s_allow = self.contract.functions.previewSettlement(
            order_id_to_bytes32(order_id),
            Web3.to_checksum_address(buyer),
            Web3.to_checksum_address(seller),
            int(dkhyr_amount_wei),
            int(share_amount_wei),
        ).call()
        return {
            "ok": bool(ok),
            "reason": reason,
            "buyer_dkhyr_balance": int(b_bal),
            "buyer_dkhyr_allowance": int(b_allow),
            "seller_nvp1_balance": int(s_bal),
            "seller_nvp1_allowance": int(s_allow),
        }

    def settle(
        self,
        order_id: str | bytes,
        buyer: str,
        seller: str,
        dkhyr_amount_wei: int,
        share_amount_wei: int,
        wait_receipt: bool = True,
    ) -> Dict[str, Any]:
        if not self.relayer_private_key:
            raise ValueError("Missing relayer private key (DVP_RELAYER_PRIVATE_KEY)")

        acct = self.w3.eth.account.from_key(self.relayer_private_key)
        order_b32 = order_id_to_bytes32(order_id)

        fn = self.contract.functions.settleDvP(
            order_b32,
            Web3.to_checksum_address(buyer),
            Web3.to_checksum_address(seller),
            int(dkhyr_amount_wei),
            int(share_amount_wei),
        )

        nonce = self.w3.eth.get_transaction_count(acct.address, "pending")
        tx = fn.build_transaction({
            "from": acct.address,
            "nonce": nonce,
            "chainId": self.w3.eth.chain_id,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        hex_tx = self.w3.to_hex(tx_hash)

        result: Dict[str, Any] = {
            "tx_hash": hex_tx,
            "order_id_bytes32": "0x" + order_b32.hex(),
        }

        if not wait_receipt:
            return result

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        events = self.contract.events.DvPSettled().process_receipt(receipt)
        result["status"] = int(receipt["status"])
        result["block_number"] = int(receipt["blockNumber"])

        if events:
            args = events[0]["args"]
            result["settlement_id"] = "0x" + args["settlementId"].hex()
            result["buyer"] = args["buyer"]
            result["seller"] = args["seller"]
            result["dkhyr_amount"] = int(args["dkhyrAmount"])
            result["share_amount"] = int(args["shareAmount"])
            result["timestamp"] = int(args["timestamp"])

        return result

