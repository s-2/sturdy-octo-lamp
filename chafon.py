import binascii

"""Chafon CF600 reader"""

# device serial protocol described in `docs/UHF Prime Reader user manual-EN.docx`

rfm_get_deviceinfo = bytes.fromhex("CF FF 00 70 00")
rfm_module_int = bytes.fromhex("CF FF 00 50 00")
fivesecondsinventory = bytes.fromhex("CF FF 00 01 05 00 00 00 00 05")

def crc(inbytes):
    PRESET_VALUE = 0xFFFF
    POLYNOMIAL = 0x8408

    uiCrcValue = PRESET_VALUE

    for i in range(len(inbytes)):
        uiCrcValue = uiCrcValue ^ inbytes[i]

        for j in range(8):
            if uiCrcValue & 0x0001:
                uiCrcValue = (uiCrcValue >> 1) ^ POLYNOMIAL
            else:
                uiCrcValue = (uiCrcValue >> 1)

    return uiCrcValue

def detect_device():
    checksum = crc(rfm_module_int)
    command_with_checksum = rfm_module_int + bytes([(checksum & 0xFF00) >> 8, checksum & 0xFF])  # expected command_with_checksum: CF FF 00 50 00 07 26

    # todo: send to serial device
    result = send_command(command_with_checksum)    # not yet implemented

    # expected response: CF 01 00 50 01 00 A3 F5
    if result[0] == 0xCF:
        crc_expected = (result[-2] << 8) | result[-1]
        crc_actual = crc(result[0:-2])

        if crc_actual == crc_expected:
            return True

    return False
