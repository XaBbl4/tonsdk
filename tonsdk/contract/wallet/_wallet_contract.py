import decimal
from enum import Enum
from typing import Union, List, Dict
from dataclasses import dataclass

from .. import Contract
from ...boc import Cell
from ...utils import Address, sign_message


class SendModeEnum(int, Enum):
    carry_all_remaining_balance = 128
    carry_all_remaining_incoming_value = 64
    destroy_account_if_zero = 32
    ignore_errors = 2
    pay_gas_separately = 1

    def __str__(self) -> str:
        return super().__str__()

@dataclass
class WalletMessage():
    address: str
    amount: int
    send_mode: SendModeEnum = SendModeEnum.ignore_errors | SendModeEnum.pay_gas_separately
    payload: Union[Cell, str, bytes, None] = None
    state_init: Union[Cell, None] = None

    def to_dict(cls):
        d = {
            'address': cls.address,
            'amount': cls.amount,
            'send_mode': cls.send_mode,
        }
        if cls.payload is not None:
            d['payload'] = cls.payload
        if cls.state_init is not None:
            d['state_init'] = cls.state_init
        return d

    @staticmethod
    def from_dict(d: Dict):
        return WalletMessage(
            address=d.get('address'),
            amount=d.get('amount'),
            send_mode=d.get('send_mode', SendModeEnum.ignore_errors | SendModeEnum.pay_gas_separately),
            payload=d.get('payload', None),
            state_init=d.get('state_init', None),
        )

class WalletContract(Contract):
    def __init__(self, **kwargs):
        if (("public_key" not in kwargs or "private_key" not in kwargs) and "address" not in kwargs) and 'public_keys' not in kwargs:
            raise Exception(
                "WalletContract required publicKey or address in options")
        super().__init__(**kwargs)

    def create_data_cell(self):
        cell = Cell()
        cell.bits.write_uint(0, 32)
        cell.bits.write_bytes(self.options["public_key"])
        return cell

    def create_signing_message(self, seqno=None):
        seqno = seqno or 0
        cell = Cell()
        cell.bits.write_uint(seqno, 32)
        return cell

    def create_transfer_message(self,
                                to_addr: str = None,
                                amount: int = None,
                                seqno: int = None,
                                payload: Union[Cell, str, bytes, None] = None,
                                send_mode=SendModeEnum.ignore_errors | SendModeEnum.pay_gas_separately,
                                dummy_signature=False, state_init=None,
                                recipients_list: Union[List[Union[Dict, WalletMessage]], WalletMessage] = None):
        if recipients_list is None:
            recipients_list = [
                WalletMessage(
                    address=to_addr,
                    amount=amount,
                    send_mode=send_mode,
                    payload=payload,
                    state_init=state_init,
                ),
            ]
        elif isinstance(recipients_list, WalletMessage):
            recipients_list = [recipients_list,]

        if len(recipients_list) > 4:
            raise Exception("Many recipients for this contract")

        signing_message = self.create_signing_message(seqno)
        for recipient in recipients_list:
            if isinstance(recipient, dict):
                recipient = WalletMessage.from_dict(recipient)
            payload_cell = Cell()
            payload = recipient.payload
            if payload:
                if isinstance(payload, str):
                    payload_cell.bits.write_uint(0, 32)
                    payload_cell.bits.write_string(payload)
                elif isinstance(payload, Cell):
                    payload_cell = payload
                else:
                    payload_cell.bits.write_bytes(payload)

            order_header = Contract.create_internal_message_header(
                Address(recipient.address), decimal.Decimal(recipient.amount))
            order = Contract.create_common_msg_info(
                order_header, recipient.state_init, payload_cell)
            signing_message.bits.write_uint8(recipient.send_mode)
            signing_message.refs.append(order)

        return self.create_external_message(signing_message, seqno, dummy_signature)

    def create_external_message(self, signing_message, seqno, dummy_signature=False):
        signature = bytes(64) if dummy_signature else sign_message(
            bytes(signing_message.bytes_hash()), self.options['private_key']).signature

        body = Cell()
        body.bits.write_bytes(signature)
        body.write_cell(signing_message)

        state_init = code = data = None

        if seqno == 0:
            deploy = self.create_state_init()
            state_init = deploy["state_init"]
            code = deploy["code"]
            data = deploy["data"]

        self_address = self.address
        header = Contract.create_external_message_header(self_address)
        result_message = Contract.create_common_msg_info(
            header, state_init, body)

        return {
            "address": self_address,
            "message": result_message,
            "body": body,
            "signature": signature,
            "signing_message": signing_message,
            "state_init": state_init,
            "code": code,
            "data": data,
        }

    def create_init_external_message(self):
        create_state_init = self.create_state_init()
        state_init = create_state_init["state_init"]
        address = create_state_init["address"]
        code = create_state_init["code"]
        data = create_state_init["data"]

        signing_message = self.create_signing_message()
        signature = sign_message(
            bytes(signing_message.bytes_hash()), self.options['private_key']).signature

        body = Cell()
        body.bits.write_bytes(signature)
        body.write_cell(signing_message)

        header = Contract.create_external_message_header(address)
        external_message = Contract.create_common_msg_info(
            header, state_init, body)

        return {
            "address": address,
            "message": external_message,

            "body": body,
            "signing_message": signing_message,
            "state_init": state_init,
            "code": code,
            "data": data,
        }
