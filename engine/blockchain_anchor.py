"""
Blockchain Anchor — tamper-evident evidence sealing on Polygon Amoy
====================================================================

Anchors CIB engine reports and Narrative Tracker outputs on Polygon Amoy
by storing a keccak256 hash of the JSON report on-chain.

This makes documented campaigns tamper-evident:
  - The hash proves the report existed at a specific block timestamp
  - The report content can be verified against the on-chain hash at any time
  - No personal data is stored on-chain — only the hash

Contract: 0x1F04BCD4C6B97D201654F2Aa2a9F3cf91A35Ab33 (Polygon Amoy)
Interface: single function storeHash(bytes32 reportHash, string calldata reportId)

Fallback: if no wallet is configured, the anchor is recorded locally only
(hash + timestamp) with a note that on-chain anchoring is pending.

Author: Neuronium Engineers
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# web3 is optional — local fallback if not installed
try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    _WEB3_AVAILABLE = True
except ImportError:
    _WEB3_AVAILABLE = False


# ── Contract ABI (minimal — only storeHash) ───────────────────────────────

_CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "reportHash", "type": "bytes32"},
            {"internalType": "string",  "name": "reportId",   "type": "string"},
        ],
        "name": "storeHash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "reportHash", "type": "bytes32"}],
        "name": "getTimestamp",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

CONTRACT_ADDRESS = "0x1F04BCD4C6B97D201654F2Aa2a9F3cf91A35Ab33"
AMOY_RPC = "https://rpc-amoy.polygon.technology"


# ── Data model ────────────────────────────────────────────────────────────

@dataclass
class AnchorProof:
    report_id: str
    report_hash: str            # hex keccak256 of report JSON
    anchored_at: str            # ISO-8601 timestamp
    on_chain: bool
    tx_hash: Optional[str]      # None if local-only
    block_number: Optional[int]
    contract_address: str
    network: str                # "polygon_amoy" | "local"
    pending_reason: Optional[str] = None  # why on-chain anchoring skipped

    def as_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "report_hash": self.report_hash,
            "anchored_at": self.anchored_at,
            "on_chain": self.on_chain,
            "tx_hash": self.tx_hash,
            "block_number": self.block_number,
            "contract_address": self.contract_address,
            "network": self.network,
            "pending_reason": self.pending_reason,
        }


# ── Hash computation ──────────────────────────────────────────────────────

def _compute_hash(report: dict) -> str:
    """
    Deterministic keccak256 of the report.
    Keys sorted for consistency across serialisations.
    """
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=False, default=str)
    return "0x" + hashlib.sha3_256(canonical.encode()).hexdigest()


def _report_id(report: dict) -> str:
    """Derive a short human-readable report ID."""
    ts = report.get("generated_at", datetime.now(timezone.utc).isoformat())
    topic = report.get("topic", report.get("tlp", "cib"))[:8]
    h = hashlib.sha256(ts.encode()).hexdigest()[:8]
    return f"{topic}_{h}"


# ── On-chain anchoring ────────────────────────────────────────────────────

def _anchor_on_chain(report_hash: str, report_id: str,
                      private_key: str, rpc_url: str) -> tuple[str, int]:
    """
    Submit the hash to Polygon Amoy.
    Returns (tx_hash, block_number).
    Raises on failure — caller handles graceful fallback.
    """
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACT_ADDRESS),
        abi=_CONTRACT_ABI,
    )

    hash_bytes = bytes.fromhex(report_hash.removeprefix("0x"))
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    tx = contract.functions.storeHash(hash_bytes, report_id).build_transaction({
        "chainId": 80002,        # Polygon Amoy chain ID
        "gas": 80000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "from": account.address,
    })
    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    return tx_hash.hex(), receipt.block_number


# ── Main anchor function ──────────────────────────────────────────────────

class BlockchainAnchor:
    def __init__(self,
                 private_key: Optional[str] = None,
                 rpc_url: Optional[str] = None):
        self.private_key = private_key or os.getenv("WALLET_PRIVATE_KEY")
        self.rpc_url = rpc_url or os.getenv("POLYGON_RPC_URL", AMOY_RPC)

    def anchor(self, report: dict) -> AnchorProof:
        """
        Anchor a report. Attempts on-chain; falls back to local if wallet
        is not configured or chain call fails.
        """
        report_hash = _compute_hash(report)
        report_id = _report_id(report)
        now = datetime.now(timezone.utc).isoformat()

        # Attempt on-chain anchoring
        if _WEB3_AVAILABLE and self.private_key:
            try:
                tx_hash, block_num = _anchor_on_chain(
                    report_hash, report_id, self.private_key, self.rpc_url)
                return AnchorProof(
                    report_id=report_id,
                    report_hash=report_hash,
                    anchored_at=now,
                    on_chain=True,
                    tx_hash=tx_hash,
                    block_number=block_num,
                    contract_address=CONTRACT_ADDRESS,
                    network="polygon_amoy",
                )
            except Exception as exc:
                pending_reason = f"on-chain failed: {exc}"
        elif not _WEB3_AVAILABLE:
            pending_reason = "web3 library not installed"
        else:
            pending_reason = "WALLET_PRIVATE_KEY not configured"

        # Local fallback
        return AnchorProof(
            report_id=report_id,
            report_hash=report_hash,
            anchored_at=now,
            on_chain=False,
            tx_hash=None,
            block_number=None,
            contract_address=CONTRACT_ADDRESS,
            network="local",
            pending_reason=pending_reason,
        )

    def verify(self, report: dict, claimed_hash: str) -> bool:
        """Verify a report matches a previously anchored hash."""
        return _compute_hash(report) == claimed_hash
