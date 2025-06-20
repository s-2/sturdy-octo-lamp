import asyncio
import binascii
from typing import Optional, Callable, Any
from transport import SerialTransport
from pyrainrfid import InterrogatorAPI


def parse_single(msg):
    """parses the result payload for the response to CMD_SINGLE"""
    if msg[0] & 0x80:
        rssi = (msg[0] & 0x7F) - 128
    else:
        rssi = msg[0]
    pc = (msg[1] * 256) + msg[2]
    epc = msg[3:-3]
    epc_crc = msg[-3:-1]
    epc_str = ''.join('{:02x}'.format(x) for x in epc)
    print('\nEPC:', epc_str, "\t(RSSI: {:02d})".format(rssi))
    return epc


def parse_response(inp):
    """Parse R200 protocol response and extract payload"""
    state, pos, msg_type, msg_cmd, pl = 0, 0, 0, 0, 0

    while pos < len(inp):
        if state == 0 and (inp[pos] == 0xAA or inp[pos] == 0xBB):
            state = 1
            start_byte = inp[pos]

        elif state == 1:
            msg_type, msg_cmd = inp[pos], inp[pos+1]
            pos = pos + 1
            state = 2

        elif state == 2:
            pl = inp[pos] * 256 + inp[pos+1]
            pos = pos + 1
            state = 3

        elif state == 3:
            buf = inp[pos:pos+pl+1]
            end_byte = 0xDD if start_byte == 0xAA else 0x7E
            if inp[pos+pl+1] == end_byte:
                checksum_expected = inp[pos+pl]
                checksum_actual = sum(i for i in inp[pos-4:pos+pl]) & 0xFF
                if checksum_expected != checksum_actual:
                    print("invalid checksum")
                if msg_type == 0x02 and msg_cmd == 0x22:
                    return parse_single(buf)
                elif msg_type == 0x01 and msg_cmd == 0xFF:
                    print(".", end='')
            else:
                print("parse error")
            state, msg_type, msg_cmd, pl = 0, 0, 0, 0
            pos = pos + pl

        pos = pos + 1

    return bytes([])


class AsyncR200Interrogator(InterrogatorAPI):
    """Async version of R200 Interrogator using transport abstraction"""
    
    def __init__(self, transport: SerialTransport, flavor: str = 'AADD'):
        self.transport = transport
        self.flavor = flavor
        self.response_buffer = bytearray()
        self.pending_responses = {}
        self.response_callbacks = {}
        
        if flavor not in ('AADD', 'BB7E'):
            raise ValueError('unsupported start/stop byte flavor for R200 Interrogator given')
        
        self.transport.set_data_callback(self._handle_data_received)
        self.transport.set_connection_lost_callback(self._handle_connection_lost)
    
    async def connect(self) -> bool:
        """Connect to the RFID reader"""
        return await self.transport.connect()
    
    async def disconnect(self) -> None:
        """Disconnect from the RFID reader"""
        await self.transport.disconnect()
    
    def _handle_data_received(self, data: bytes):
        """Handle incoming data from the transport"""
        print(f'< {" ".join("{:02X}".format(r) for r in data)}')
        self.response_buffer.extend(data)
        
        response = parse_response(self.response_buffer)
        if response:
            self.response_buffer.clear()
            if hasattr(self, '_current_callback') and self._current_callback:
                self._current_callback(response)
    
    def _handle_connection_lost(self, exc: Exception):
        """Handle connection loss"""
        print(f"Connection lost: {exc}")
    
    async def send_command(self, cmd_bytes: bytes, response_callback: Optional[Callable] = None) -> Optional[bytes]:
        """Send command to the interrogator"""
        if not self.transport.is_connected:
            raise RuntimeError("Not connected to interrogator")
        
        command = bytearray(cmd_bytes)
        if self.flavor == 'BB7E':
            command[0], command[-1] = 0xBB, 0x7E
        
        self._current_callback = response_callback
        await self.transport.write(bytes(command))
        
        if response_callback is None:
            await asyncio.sleep(0.1)
            return None
    
    async def read_single(self) -> Optional[bytes]:
        """Perform a single RFID read operation"""
        from r200 import CMD_SINGLE
        
        result_future = asyncio.Future()
        
        def callback(response):
            if not result_future.done():
                result_future.set_result(response)
        
        await self.send_command(bytes(CMD_SINGLE), callback)
        
        try:
            return await asyncio.wait_for(result_future, timeout=2.0)
        except asyncio.TimeoutError:
            print("Timeout waiting for response")
            return None

