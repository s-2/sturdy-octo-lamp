import binascii, math, serial, time
import freeslurp

from pyrainrfid import *
import tid

# implements communication with an R200 Reader, based on R200 User Protocol defined in docs/R200 user protocol V2.3.3.pdf


def parse_single(msg):
    """parses the result payload for the response to CMD_SINGLE"""
    # twos-complement workaround since int.from_bytes() supports variable length (e.g. 8 bits) only from Python >= 3.11
    # rssi = int.from_bytes(bytes(msg[0]), byteorder='little', length=8, signed=True)
    if msg[0] & 0x80:
        rssi = (msg[0] & 0x7F) - 128
    else:
        rssi = msg[0]
    pc = (msg[1] * 256) + msg[2]
    epc = msg[3:-3]
    epc_crc = msg[-3:-1]
    # todo: epc_crc
    epc_str = ''.join('{:02x}'.format(x) for x in epc)
    print('\nEPC:', epc_str, "\t(RSSI: {:02d})".format(rssi))

    if epc[0] == 0x13:
        freeslurp.cup(epc_str).parse()

    return epc


def parse_read(msg):
    """parses the result payload for the response to CMD_READ"""
    ul = msg[0]
    pc = (msg[1] * 256) + msg[2]
    epc = msg[3:3+ul-2]
    data = msg[3+ul-2:-1]
    checksum = msg[-1:]  # todo: verify

    print("ul: {:02x} pc: {:04x}".format(ul, pc))
    print("tag epc:", binascii.hexlify(epc))
    print("read result:", binascii.hexlify(data))

    return data


def parse(inp):
    state, pos, msg_type, msg_cmd, pl = 0, 0, 0, 0, 0

    while pos < len(inp):
        if state == 0 and inp[pos] == 0xAA:
            # found start marker
            state = 1

        elif state == 1:
            msg_type, msg_cmd = inp[pos], inp[pos+1]
            pos = pos + 1
            # if msg_type == 0x02 and msg_cmd == 0x22:
            state = 2

        elif state == 2:
            pl = inp[pos] * 256 + inp[pos+1]
            pos = pos + 1
            # print("PL", hex(pl))
            state = 3

        elif state == 3:
            buf = inp[pos:pos+pl+1]
            # print(buf)
            # print(hex(inp[pos+pl+1]))
            if inp[pos+pl+1] == 0xDD:
                # found end marker
                checksum_expected = inp[pos+pl]
                checksum_actual = sum(i for i in inp[pos-4:pos+pl]) & 0xFF  # todo: refactor
                if checksum_expected != checksum_actual:
                    print("invalid checksum")
                # print("parse success")
                if msg_type == 0x02 and msg_cmd == 0x22:
                    return parse_single(buf)  # result of CMD_READ_SINGLE
                elif msg_type == 0x01 and msg_cmd == 0x39:
                    return parse_read(buf)  # result of CMD_READ
                elif msg_type == 0x01 and msg_cmd == 0xFF:
                    print(".", end='')
            else:
                print("parse error")
            state, msg_type, msg_cmd, pl = 0, 0, 0, 0
            pos = pos + pl

        pos = pos + 1

    return bytes([])


class R200Command(InterrogatorCommand):
    """
    encapsulates command to be sent from host to R200 reader
    params: command ID, payload (bytes-like, optional)
    payload length, if left padding with 0x00 is desired
    """

    def __init__(self, cmd=None, payload=None, payload_len=None, flavor=None):
        self.flavor = None
        if cmd is None or cmd < 0 or cmd > 255:
            raise ValueError("no command type given or invalid command size")
        self.cmd = cmd
        if payload is not None:
            if payload_len is not None:
                # may require padding:
                if len(payload) > payload_len:
                    raise ValueError("given payload data is longer than requested payload length")
                self.payload_len = payload_len
            else:
                self.payload_len = len(payload)
            padding = self.payload_len - len(payload)
            self.payload = bytes([0x00] * padding) + bytes(payload)
        else:
            self.payload_len = 0

    def __bytes__(self):
        """generate actual command to be sent to R200"""
        total_length = 7 + self.payload_len
        command = bytearray(total_length)
        command[0] = 0xAA
        command[1] = 0x00 # direction: host to reader
        command[2] = self.cmd
        command[3] = (self.payload_len & 0xFF00) >> 8
        command[4] = (self.payload_len & 0x00FF)
        for i in range(self.payload_len):
            command[5 + i] = self.payload[i]
        checksum = sum(command[1:])
        command[-2] = checksum & 0xFF
        command[-1] = 0xDD

        return bytes(command)

    def rawbytes(self, flavor='AADD'):
        if flavor not in ('AADD', 'BB7E'):
            raise ValueError('unsupported start/stop byte flavor for R200 Interrogator given')
        self.flavor = flavor
        print(self.flavor)
        return self.bytes()


def generate_select_command(select_params):
    """generates an R200Command from given SelectParams object"""
    mask_len_bytes = math.ceil(select_params.mask_len / 8)
    select_command = bytearray(7 + mask_len_bytes)

    # SelParam
    select_command[0] = ((select_params.target & 0b111) << 5) | \
                        ((select_params.action & 0b111) << 3) | \
                        (select_params.membank & 0b11)

    select_command[1] = (select_params.mask_offset & 0xFF000000) >> 24
    select_command[2] = (select_params.mask_offset & 0x00FF0000) >> 16
    select_command[3] = (select_params.mask_offset & 0x0000FF00) >> 8
    select_command[4] = (select_params.mask_offset & 0x000000FF)

    select_command[5] = select_params.mask_len
    select_command[6] = select_params.truncate

    for i in range(mask_len_bytes):
        select_command[7 + i] = select_params.mask_compare[i]

    return CMD_SET_SELECT(select_command)


def parse_select_response(response):
    """parse select response and return as SelectParams object"""
    pass  # todo


def generate_write_command(write_data, write_offset, write_len,
                           membank=MemBank.EPC_UII, access_password=bytes([0x00, 0x00, 0x00, 0x00])):
    """generates an R200Command from given write parameters"""
    '''@param write_offset in words'''
    '''@param write_len in words'''
    write_len_bytes = write_len * 2  # covert words to bytes
    write_command = bytearray(9 + write_len_bytes)

    write_command[0] = access_password[0]
    write_command[1] = access_password[1]
    write_command[2] = access_password[2]
    write_command[3] = access_password[3]

    write_command[4] = membank

    write_command[5] = (write_offset & 0xFF00) >> 8
    write_command[6] = (write_offset & 0x00FF)

    write_command[7] = (write_len & 0xFF00) >> 8
    write_command[8] = (write_len & 0x00FF)

    for i in range(write_len_bytes):  # todo: padding / right alignment?
        write_command[9 + i] = write_data[i]

    return CMD_WRITE(write_command)


def generate_read_command(read_offset, read_len, membank=MemBank.EPC_UII,
                          access_password=bytes([0x00, 0x00, 0x00, 0x00])):
    """generates an R200Command from given read parameters"""
    '''@param read_offset in words'''
    '''@param read_len in words'''
    write_len_bytes = read_len * 2  # covert words to bytes
    read_command = bytearray(9)

    read_command[0] = access_password[0]
    read_command[1] = access_password[1]
    read_command[2] = access_password[2]
    read_command[3] = access_password[3]

    read_command[4] = membank

    read_command[5] = (read_offset & 0xFF00) >> 8
    read_command[6] = (read_offset & 0x00FF)

    read_command[7] = (read_len & 0xFF00) >> 8
    read_command[8] = (read_len & 0x00FF)

    return CMD_READ(read_command)
    # todo: parse response...


def generate_lock_command(ld_bytes, access_password=bytes([0x00, 0x00, 0x00, 0x00])):
    """generates an R200Command from given write parameters"""
    lock_command = bytearray(7)

    lock_command[0] = access_password[0]
    lock_command[1] = access_password[1]
    lock_command[2] = access_password[2]
    lock_command[3] = access_password[3]

    lock_command[4] = ld_bytes[0]
    lock_command[5] = ld_bytes[1]
    lock_command[6] = ld_bytes[2]

    return CMD_LOCK(lock_command)
    # todo: parse response...


CMD_FIRMWARE = R200Command(0x07, [0x01])
CMD_MODULE_INFO = R200Command(0x03, [0x00])
CMD_SINGLE = R200Command(0x22)
CMD_MULTI = R200Command(0x27, [0x22, 0x27, 0x10])  # [reserved, cnt msb, cnt lsb]
CMD_MULTI_STOP = R200Command(0x28)
CMD_GET_SELECT = R200Command(0x0B)
CMD_SET_SELECT = lambda payload: R200Command(0x0C, payload)
CMD_SET_SELECT_MODE = R200Command(0x12, [0x01])  # 0x00, 0x01 or 0x02
CMD_READ = lambda payload: R200Command(0x39, payload)
CMD_WRITE = lambda payload: R200Command(0x49, payload)
CMD_LOCK = lambda payload: R200Command(0x82, payload)
CMD_DENSE_READER_MODE = R200Command(0xF5, [0x01])



####################################################

class R200Interrogator(InterrogatorAPI):

    def __init__(self, flavor='AADD'):  # todo: add parameters for connection?
        self.reader = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.08)
        if flavor not in ('AADD', 'BB7E'):
            raise ValueError('unsupported start/stop byte flavor for R200 Interrogator given')
        self.flavor = flavor
        # reader = serial.Serial('COM18', 115200, timeout=2

    def send_command(self, cmd):
        """
        sends command to Interrogator and returns response
        :param cmd: Command object, should implement a __bytes__() method
        :return:
        """
        command = bytes(cmd)

        # ugly: patch start and stop byte depending on flavor
        if self.flavor == 'BB7E':
            command = bytearray(command)
            command[0], command[-1] = 0xBB, 0x7E

        print('\n> ' + ' '.join('{:02X}'.format(c) for c in command))
        self.reader.write(command)
        time.sleep(0.02)
        ret = self.reader.read(60)
        print('< ' + ' '.join('{:02X}'.format(r) for r in ret))
        return ret

    def read_single(self):
        return self.send_command(CMD_SINGLE)  # bytearray.fromhex("AA 00 22 00 00 22 DD")

    def read_tid(self):
        read_tid = generate_read_command(0, 6, MemBank.TID)
        return self.send_command(read_tid)

    def flash_led(self):
        led_tag = SelectParams(bytes.fromhex("7882f90c"), mask_offset=0x40, membank=MemBank.TID)
        select_cmd = generate_select_command(led_tag)

        # aa0049000b000000000000040001000059dd
        # write to reserved, offset 4 words
        flash_cmd = generate_write_command(bytes.fromhex('00000000'), 4, 2, MemBank.RES)
        # print(binascii.hexlify(bytes(cmd)))
        while True:
            self.reader.write(bytes(select_cmd))
            self.reader.write(bytes(flash_cmd))
            time.sleep(0.1)
        # ret = reader.read(60)
        # return ret

    def modify_access_password(self):
        cmd = generate_write_command(bytes.fromhex('1333 3337'), 2, 2, MemBank.RES)
        self.send_command(cmd)

    def lock_epc(self):
        cmd = generate_lock_command(bytes(LockCommandPayload()), bytes.fromhex('00000000'))
        self.send_command(cmd)

    def unlock_epc(self):
        cmd = generate_lock_command(bytes(LockCommandPayload(lockmode=LockMode.UNLOCKED)), bytes.fromhex('00000000'))
        self.send_command(cmd)

    def detect_device(self):
        result = self.send_command(CMD_MODULE_INFO)

        # todo: parse result
        # result is either BB 01 03 00 10 00 4D 31 30 30 20 32 36 64 42 6D 20 56 31 2E 30 92 7E
        # or AA 01 03 00 10 00 4D 31 30 30 20 32 36 64 42 6D 20 56 31 2E 30 92 DD depending on flavor,
        # with BB or AA being the start byte, 7E or DD the stop byte.
        # the second byte 0x01 means the data direction is from reader to host, while 0x00 indicates host to reader communication, as in commands.
        # 0x03 represents the CMD_MODULE_INFO command, followed by the 16 bit payload length 0x0010, i.e. we expect 16 bytes of payload here.
        # The first byte of payload is "info type" being set to 0x00, followed by an ascii text string that is PL - 1 in length, i.e. 15 bytes here. This string should be displayer to the User.
        # 0x92 is the check sum, which is the arithmetic sum of payload (c.f. the proof-of-concept implementation is parse().

        if result[1] == 0x01 and result[2] == 0x03:
            return True

        return False

    async def detect_device_async(self, port: str) -> tuple[bool, str]:
        """Detect R200 device on specified port and return success status with device info"""
        import asyncio
        from transport import SerialTransport
        
        transport = None
        try:
            transport = SerialTransport(port, timeout=2.0)
            if not await transport.connect():
                return False, ""
            
            response_data = bytearray()
            last_data_time = None
            data_settling_task = None
            response_ready = asyncio.Event()
            
            async def settle_data():
                await asyncio.sleep(0.2)  # Wait 0.2 seconds for data to settle
                response_ready.set()
            
            def data_callback(data: bytes):
                nonlocal last_data_time, data_settling_task
                response_data.extend(data)
                last_data_time = asyncio.get_event_loop().time()
                
                if data_settling_task and not data_settling_task.done():
                    data_settling_task.cancel()
                data_settling_task = asyncio.create_task(settle_data())
            
            transport.set_data_callback(data_callback)
            
            command = bytes(CMD_MODULE_INFO)
            if self.flavor == 'BB7E':
                command = bytearray(command)
                command[0], command[-1] = 0xBB, 0x7E
                command = bytes(command)
            
            await transport.write(command)
            
            try:
                await asyncio.wait_for(response_ready.wait(), timeout=2.0)
                result = bytes(response_data)
                
                if (len(result) >= 3 and result[1] == 0x01 and result[2] == 0x03 and
                    ((self.flavor == 'AADD' and result[0] == 0xAA and result[-1] == 0xDD) or
                     (self.flavor == 'BB7E' and result[0] == 0xBB and result[-1] == 0x7E))):
                    
                    if len(result) >= 22:
                        ascii_text = result[6:21].decode('ascii', errors='ignore').strip()
                        device_info = ascii_text if ascii_text else "R200 Reader"
                    else:
                        device_info = "R200 Reader"
                    
                    return True, device_info
                
                return False, ""
                
            except asyncio.TimeoutError:
                return False, ""
                
        except Exception as e:
            print(f"R200 detection error on {port}: {e}")
            return False, ""
        finally:
            if transport:
                await transport.disconnect()


    def led_animate(self):

        tags = ["7882f903", "7882f904", "7882f905", "7882f906", "7882f907", "7882f908", "7882f909", "7882f90a"]

        select_cmds = [bytes(generate_select_command(SelectParams(
            bytes.fromhex(foo), mask_offset=0x40, membank=MemBank.TID)
        )) for foo in tags]

        # led_tag = SelectParams(bytes.fromhex("7882f90c"), mask_offset=0x40, membank=MemBank.TID)
        # select_cmd = generate_select_command(led_tag)

        # aa0049000b000000000000040001000059dd
        # write to reserved, offset 4 words
        flash_cmd = bytes(generate_write_command(bytes.fromhex('00000000'), 4, 2, MemBank.RES))

        while True:
            for led_sel in select_cmds:
                self.send_command(led_sel)
                self.send_command(flash_cmd)
                time.sleep(0.05)


def select_epc(epc_hex):
    epc = bytes.fromhex(epc_hex)
    return bytes(generate_select_command(SelectParams(epc)))


def em4325_temp():
    return generate_read_command(0x100, 2, MemBank.USER)
    # result: 00 00  00 00  00 00  0E C0


def main():
    """Main entry point for R200 reader application"""
    import argparse
    
    parser = argparse.ArgumentParser(description='R200 RFID Reader Control')
    parser.add_argument('--mode', choices=['cli', 'gui'], default='cli',
                       help='Run in CLI or GUI mode (default: cli)')
    parser.add_argument('--port', default='/dev/ttyUSB0',
                       help='Serial port to use (default: /dev/ttyUSB0)')
    parser.add_argument('--flavor', choices=['AADD', 'BB7E'], default='BB7E',
                       help='Protocol flavor (default: BB7E)')
    parser.add_argument('--single', action='store_true',
                       help='Perform single read and exit')
    parser.add_argument('--animate', action='store_true',
                       help='Run LED animation (continuous)')
    
    args = parser.parse_args()
    
    if args.mode == 'gui':
        from gui import main as gui_main
        gui_main()
    else:
        r200 = R200Interrogator(args.flavor)

        r200.detect_device()

        r200.send_command(CMD_DENSE_READER_MODE)
        
        if args.single:
            response = r200.send_command(CMD_SINGLE)
            if response:
                parse(response)
        elif args.animate:
            r200.led_animate()
        else:
            print("R200 Interrogator initialized. Use --single for single read or --animate for LED animation.")
            print("Or use --mode gui to launch the GUI interface.")


if __name__ == '__main__':
    main()
