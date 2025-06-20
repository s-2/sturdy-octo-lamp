import binascii
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
        self.mask_compare = mask_compare  # todo: ensure bytes-like; allow hex string as parameter?
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

        # todo: raise ValueErrors for invalid parameters
