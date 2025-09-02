import binascii
import sys
import asyncio
import argparse
from enum import IntEnum


class InterrogatorAPI:
    pass


class InterrogatorCommand:
    pass


class MemBank(IntEnum):
    RES = 0b00
    EPC_UII = 0b01
    TID = 0b10
    USER = 0b11


class LockBank(IntEnum):
    KILL_PWD = 0
    ACCESS_PWD = 1
    EPC = 2
    TID = 3
    USER = 4


class LockMode(IntEnum):
    UNLOCKED = 0b00
    PERMAUNLOCKED = 0b01
    LOCKED = 0b10
    PERMALOCKED = 0b11


class TagError(IntEnum):
    OTHER = 0b0000
    NOT_SUPPORTED = 0b0001
    INSUFFICIENT_PRIVILEGES = 0b0010
    MEMORY_OVERRUN = 0b0011
    MEMORY_LOCKED = 0b0100
    CRYPTO_SUITE_ERROR = 0b0101
    COMMAND_NOT_ENCAPSULATED = 0b0110
    RESPONSE_BUFFER_OVERFLOW = 0b0111
    SECURITY_TIMEOUT = 0b1000
    INSUFFICIENT_POWER = 0b1011
    NON_SPECIFIC = 0b1111


class LockCommandPayload:
    def __init__(self, lockbank=LockBank.EPC, lockmode=LockMode.LOCKED):
        """
        generate 20-bit Lock-Command Payload
        :type lockmode: LockMode
        :type lockbank: LockBank
        """
        self.lock_command = 0x000000
        self.setlock(lockbank, lockmode)

    def setlock(self, lockbank=LockBank.EPC, lockmode=LockMode.LOCKED):
        """
        add lock state for another memory bank to exisitng lock command
        :type lockmode: LockMode
        :type lockbank: LockBank
        """
        if lockbank > 0b11:  # in future Python versions: if lockbank not in LockBank:
            raise ValueError('invalid LockBank given')
        if lockmode > 0b11:  # in future Python versions: if lockmode not in LockMode:
            raise ValueError('invalid LockMode given')

        if lockmode in (LockMode.PERMAUNLOCKED, LockMode.PERMALOCKED):
            action_mask = 0b11  # todo: add UI warning / confirm dialog before permanently locking tag
        else:
            action_mask = 0b10

        # set mask for given lock bank
        self.lock_command |= (action_mask << (10 + (2 * (4 - lockbank))))  # todo: reset bits to zero if previously set?

        # set action field for given lock mode
        self.lock_command |= (action_mask << (2 * (4 - lockmode)))

    def __bytes__(self):
        return int.to_bytes(self.lock_command, 3, 'big')


class SelectParams:
    """
    encapsulates abstract select parameters to be passed to
    individual device support implementations
    :param mask_compare: bytes-like object representing mask data for comparison
    :param mask_len: length in bits (not words) of mask; defaults to compare data length
    :param mask_offset: start position in bits (not words) of mask; default 0x20 (start of EPC)
    :type membank: MemBank
    """
    def __init__(self, mask_compare, mask_len=None, mask_offset=0x20,
                 membank=MemBank.EPC_UII, target=0b000, action=0b000, truncate=False):
        self.mask_compare = mask_compare
        if mask_compare is None or len(mask_compare) == 0:
            raise ValueError("no select mask given")
        if mask_len is None:
            mask_len = len(mask_compare) * 8  # assume multiple of 8 bits when len implicitly inferred from input
        self.mask_len = mask_len
        self.mask_offset = mask_offset  # todo: only default to 0x20 for EPC (and TID?), enforce 00 for RES; 0 for USER?
        if membank > MemBank.USER:
            raise ValueError("membank must be one of 00 (RES), 01 (EPC_UII), 10 (TID) or 11 (USER)")
        self.membank = membank
        self.target = target
        self.action = action
        self.truncate = truncate


async def _cli_autodetect_and_optionally_single(do_single: bool):
    from device_detection import ReaderDetectionManager
    from transport import SerialTransport
    from serialinterface import AsyncR200Interrogator
    from hyb506 import AsyncHYB506Interrogator
    from chafon import AsyncChafonInterrogator

    mgr = ReaderDetectionManager()
    readers = await mgr.detect_all_readers_async()
    if not readers:
        print("No readers detected.")
        return

    for r in readers:
        print(str(r))

    if not do_single:
        return

    async def run_single_for_reader(r):
        interrogator = None
        transport = None
        try:
            if r.reader_type.startswith("R200"):
                flavor = 'AADD' if 'AADD' in r.reader_type else 'BB7E'
                transport = SerialTransport(r.port)
                interrogator = AsyncR200Interrogator(transport, flavor)
            elif r.reader_type == "HYB506":
                transport = SerialTransport(r.port, baudrate=57600)
                interrogator = AsyncHYB506Interrogator(transport)
            elif r.reader_type == "CF600":
                transport = SerialTransport(r.port)
                interrogator = AsyncChafonInterrogator(transport)
            else:
                print(f"Unsupported reader type for single read: {r.reader_type}")
                return

            ok = await interrogator.connect()
            if not ok:
                print(f"{r.reader_type} on {r.port}: connect failed")
                return
            result = await interrogator.read_single()
            if result is None:
                print(f"{r.reader_type} on {r.port}: No tag or timeout")
            else:
                if isinstance(result, bytes):
                    hex_result = ''.join('{:02X}'.format(x) for x in result)
                else:
                    hex_result = result
                print(f"{r.reader_type} on {r.port}: {hex_result}")
        finally:
            if interrogator:
                await interrogator.disconnect()

    for r in readers:
        await run_single_for_reader(r)


async def _cli_single(reader_type: str, port: str):
    from transport import SerialTransport
    from serialinterface import AsyncR200Interrogator
    from hyb506 import AsyncHYB506Interrogator
    from chafon import AsyncChafonInterrogator

    interrogator = None
    try:
        if reader_type == 'r200-aadd':
            transport = SerialTransport(port)
            interrogator = AsyncR200Interrogator(transport, 'AADD')
        elif reader_type == 'r200-bb7e':
            transport = SerialTransport(port)
            interrogator = AsyncR200Interrogator(transport, 'BB7E')
        elif reader_type == 'hyb506':
            transport = SerialTransport(port, baudrate=57600)
            interrogator = AsyncHYB506Interrogator(transport)
        elif reader_type == 'chafon':
            transport = SerialTransport(port)
            interrogator = AsyncChafonInterrogator(transport)
        else:
            print("Unsupported reader type.")
            return

        ok = await interrogator.connect()
        if not ok:
            print("Failed to connect.")
            return
        result = await interrogator.read_single()
        if result is None:
            print("No tag detected or timeout")
        else:
            if isinstance(result, bytes):
                hex_result = ''.join('{:02X}'.format(x) for x in result)
            else:
                hex_result = result
            print(hex_result)
    finally:
        if interrogator:
            await interrogator.disconnect()


def main():
    parser = argparse.ArgumentParser(description='RAIN RFID Reader Control')
    parser.add_argument('--mode', choices=['cli', 'gui'], default='cli')
    parser.add_argument('--port', default='/dev/ttyUSB0')
    parser.add_argument('--reader-type', choices=['r200-aadd', 'r200-bb7e', 'hyb506', 'chafon'])
    parser.add_argument('--single', action='store_true')
    parser.add_argument('--autodetect', action='store_true')

    args = parser.parse_args()

    if args.mode == 'gui':
        from gui import main as gui_main
        gui_main()
        return

    if args.autodetect:
        asyncio.run(_cli_autodetect_and_optionally_single(args.single))
        return

    if args.single and args.reader_type and args.port:
        asyncio.run(_cli_single(args.reader_type, args.port))
        return

    parser.print_help()


if __name__ == '__main__':
    main()
