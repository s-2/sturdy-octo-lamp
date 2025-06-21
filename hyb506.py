import binascii

from pyrainrfid import MemBank

"""hyintech HYB506"""

# device serial protocol described in `docs/UHFReader06 UHF RFID Reader User's Manual V1.7.doc`

def crc16(data):
    crc = 0xffff
    for i in range(len(data)):
        crc ^= data[i]
        for j in range(8):
            if crc & 1:
                crc ^= 0x10810
            crc >>= 1
    return crc


def generate_command(cmd_byte, payload=bytes(), reader_addr=0x00):
    size = 4 + len(payload)
    cmd = bytearray(1 + size)
    cmd[0] = size
    cmd[1] = reader_addr
    cmd[2] = cmd_byte
    for i in range(len(payload)):
        cmd[3 + i] = payload[i]
    crc = crc16(cmd[:-2])
    cmd[-2] = crc & 0x00FF
    cmd[-1] = (crc & 0xFF00) >> 8

    return cmd


def generate_write_command(write_data, write_offset, write_len, tag_epc_len, tag_epc,
                           membank=MemBank.EPC_UII, access_password=bytes([0x00, 0x00, 0x00, 0x00])):
    """generates a Command from given write parameters"""
    write_len_bytes = write_len * 2
    epc_len_bytes = tag_epc_len * 2
    write_command = bytearray(10 + write_len_bytes + epc_len_bytes)

    write_command[0] = write_len
    write_command[1] = tag_epc_len
    for i in range(epc_len_bytes):
        write_command[2 + i] = tag_epc[i]
    write_command[2 + epc_len_bytes] = membank
    write_command[3 + epc_len_bytes] = write_offset
    for i in range(write_len_bytes):
        write_command[4 + epc_len_bytes + i] = write_data[i]
    write_command[4 + epc_len_bytes + write_len_bytes] = access_password[0]
    write_command[5 + epc_len_bytes + write_len_bytes] = access_password[1]
    write_command[6 + epc_len_bytes + write_len_bytes] = access_password[2]
    write_command[7 + epc_len_bytes + write_len_bytes] = access_password[3]
    write_command[8 + epc_len_bytes + write_len_bytes] = 0x00  # maskadr
    write_command[9 + epc_len_bytes + write_len_bytes] = epc_len_bytes  # #masklen

    return generate_command(0x03, write_command)


def detect_device():
    reader_info_cmd = generate_command(0x21)

    # todo: send to serial port
    result = send_command(reader_info_cmd)  # not yet implemented

    result_length = result[0]
    crc_expected = (result[-2] << 8) | result[-1]
    crc_actual = crc16(result[0:-2])

    # just accept any response with valid crc for now
    if crc_actual == crc_expected:
        return True

    return False



led_buzzer_cmd = generate_command(0x33, bytes([1, 1, 2]))
print(binascii.hexlify(led_buzzer_cmd))

inventory_cmd = generate_command(0x01)
print(binascii.hexlify(inventory_cmd))

ledflash_cmd = generate_write_command(bytes.fromhex('0000'), 4, 1, 2,
                                      bytes.fromhex('00000000'), MemBank.TID)
print(binascii.hexlify(ledflash_cmd))