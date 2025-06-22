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
    # result = send_command(command_with_checksum)    # not yet implemented

    # expected response: CF 01 00 50 01 00 A3 F5
    # if result[0] == 0xCF:

    return False

async def detect_device_async(port: str) -> tuple[bool, str]:
    """Detect CF600 device on specified port and return success status with device info"""
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
        
        checksum = crc(rfm_module_int)
        command_with_checksum = rfm_module_int + bytes([(checksum & 0xFF00) >> 8, checksum & 0xFF])
        
        await transport.write(command_with_checksum)
        
        try:
            await asyncio.wait_for(response_ready.wait(), timeout=2.0)
            result = bytes(response_data)
            
            if len(result) >= 4 and result[0] == 0xCF:
                crc_expected = (result[-2] << 8) | result[-1]
                crc_actual = crc(result[0:-2])
                
                if crc_actual == crc_expected:
                    device_info = f"CF600 Reader (Response: {' '.join(f'{b:02X}' for b in result[:8])})"
                    return True, device_info
            
            return False, ""
            
        except asyncio.TimeoutError:
            return False, ""
            
    except Exception as e:
        print(f"CF600 detection error on {port}: {e}")
        return False, ""
    finally:
        if transport:
            await transport.disconnect()
