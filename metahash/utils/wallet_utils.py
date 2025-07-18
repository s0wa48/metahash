# ====================================================================== #
# metahash/utils/wallet_utils.py                                         #
# ====================================================================== #

from __future__ import annotations

import sys
from typing import Sequence, Union

from bittensor import AsyncSubtensor
from substrateinterface import Keypair, KeypairType
from metahash.base.utils.logging import ColoredLogger as clog
import bittensor as bt

# Import secure manager
from metahash.utils.secure_wallet import load_wallet_secure, load_wallet


def verify_coldkey(
    cold_ss58: str,
    message: Union[str, bytes],
    signature_hex: str,
) -> bool:
    if isinstance(message, str):
        message = message.encode()

    sig = bytes.fromhex(signature_hex)

    # SR25519 first, ED25519 as fallback
    for crypto in (KeypairType.SR25519, KeypairType.ED25519):
        try:
            kp = Keypair(ss58_address=cold_ss58, crypto_type=crypto)
            if kp.verify(message, sig):
                return True
        except Exception:
            pass
    return False


def check_coldkeys_and_signatures(
    entries: Sequence[dict],
    *,
    message: Union[str, bytes] | None = None,
) -> list[dict]:
    """
    Verify that each signature is valid.

    Parameters
    ----------
    entries
        Sequence of dicts with ``address`` (cold-key SS58) and ``signature`` (hex).
    message
        **New (optional)**. If provided, *all* signatures are verified against
        this message (e.g. the miner's hot-key).
        If left as ``None``, the cold-key's own address is used.
    """
    verified: list[dict] = []

    # Normalize the message once
    if message is not None and isinstance(message, str):
        message_bytes = message.encode()
    else:
        message_bytes = None  # will be calculated per entry

    for idx, item in enumerate(entries, 1):
        addr = item.get("address") or item.get("coldkey")
        sig_hex = item.get("signature")

        if not addr or not sig_hex:
            missing = "address" if not addr else "signature"
            clog.error(f"Entry #{idx}: missing {missing}", color="red")
            sys.exit(1)

        mbytes = message_bytes or addr.encode()
        if not verify_coldkey(addr, mbytes, sig_hex):
            clog.error(
                f"Entry #{idx}: INVALID signature for cold-key {addr}", color="red"
            )
            sys.exit(1)

        verified.append({"address": addr, "signature": sig_hex})

    clog.success(f"✓ All {len(verified)} cold-keys verified", color="green")
    return verified


async def transfer_alpha(
    *,
    subtensor: AsyncSubtensor,
    wallet,                      # bittensor.wallet (already unlocked)
    hotkey_ss58: str,
    origin_and_dest_netuid: int,
    dest_coldkey_ss58: str,
    amount,
    wait_for_inclusion: bool = True,
    wait_for_finalization: bool = False,
    period: int = 256,           # safer default on slow nodes
) -> bool:
    # The bittensor SDK seems to have a wrong check only allowing transfers of alpha staked to a hotkey owned by the coldkey. So random. 
    # Let's use directly the extrinsics

    try:
        bt.logging.info(
            f"Transferring stake from coldkey [blue]{wallet.coldkeypub.ss58_address}[/blue] to coldkey "
            f"[blue]{dest_coldkey_ss58}[/blue]\n"
            f"Amount: [green]{amount}[/green] from netuid [yellow]{origin_and_dest_netuid}[/yellow] to netuid "
            f"[yellow]{origin_and_dest_netuid}[/yellow]"
        )
        call = await subtensor.substrate.compose_call(
            call_module="SubtensorModule",
            call_function="transfer_stake",
            call_params={
                "destination_coldkey": dest_coldkey_ss58,
                "hotkey": hotkey_ss58,
                "origin_netuid": origin_and_dest_netuid,
                "destination_netuid": origin_and_dest_netuid,
                "alpha_amount": amount.rao,
            },
        )

        success, err_msg = await subtensor.sign_and_send_extrinsic(
            call=call,
            wallet=wallet,
            wait_for_inclusion=wait_for_inclusion,
            wait_for_finalization=wait_for_finalization,
            period=period,
        )

        if success:
            if not wait_for_finalization and not wait_for_inclusion:
                return True

            bt.logging.success(":white_heavy_check_mark: [green]Finalized[/green]")

            return True
        else:
            bt.logging.error(f":cross_mark: [red]Failed[/red]: {err_msg}")
            return False

    except Exception as e:
        bt.logging.error(f":cross_mark: [red]Failed[/red]: {str(e)}")
        return False


# Export both functions for compatibility
__all__ = [
    "load_wallet",
    "load_wallet_secure",
    "verify_coldkey",
    "check_coldkeys_and_signatures",
    "transfer_alpha",
]
