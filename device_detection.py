import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Tuple
from transport import SerialTransport


class DetectedReader:
    """Represents a detected RFID reader with its connection details"""
    
    def __init__(self, port: str, reader_type: str, device_info: str, detector_class: type):
        self.port = port
        self.reader_type = reader_type
        self.device_info = device_info
        self.detector_class = detector_class
    
    def __str__(self):
        return f"{self.reader_type} on {self.port} - {self.device_info}"


class DeviceDetector(ABC):
    """Abstract base class for device-specific detection implementations"""
    
    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout
    
    @abstractmethod
    async def detect_device_async(self, port: str) -> bool:
        """
        Attempt to detect this device type on the specified port
        Returns True if device is detected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_device_info(self, response_data: bytes) -> str:
        """
        Extract human-readable device information from detection response
        Returns formatted string for display in GUI
        """
        pass
    
    @abstractmethod
    def get_reader_type(self) -> str:
        """
        Return the reader type identifier for this detector
        """
        pass
    
    @abstractmethod
    def _get_detection_command(self) -> bytes:
        """
        Return the command bytes to send for device detection
        """
        pass
    
    @abstractmethod
    def validate_response(self, response_data: bytes) -> bool:
        """
        Validate response data to determine if this device type is detected
        Returns True if response indicates this device type, False otherwise
        """
        pass
    
    async def _send_detection_command(self, port: str, command: bytes) -> Optional[bytes]:
        """
        Helper method to send detection command and receive response
        Returns response bytes or None if failed/timeout
        """
        transport = None
        try:
            transport = SerialTransport(port, timeout=self.timeout)
            
            if not await transport.connect():
                return None
            
            response_data = bytearray()
            response_received = asyncio.Event()
            
            def data_callback(data: bytes):
                response_data.extend(data)
                response_received.set()
            
            transport.set_data_callback(data_callback)
            
            await transport.write(command)
            
            try:
                await asyncio.wait_for(response_received.wait(), timeout=self.timeout)
                return bytes(response_data)
            except asyncio.TimeoutError:
                return None
                
        except Exception as e:
            print(f"Detection error on {port}: {e}")
            return None
        finally:
            if transport:
                await transport.disconnect()


class ReaderDetectionManager:
    """Manages detection of all supported reader types across available ports"""
    
    def __init__(self):
        self.detectors: List[DeviceDetector] = []
        self.detected_readers: List[DetectedReader] = []
    
    def register_detector(self, detector: DeviceDetector):
        """Register a device detector"""
        self.detectors.append(detector)
    
    def get_plausible_ports(self) -> List[str]:
        """Get list of plausible serial ports for RFID readers"""
        import serial.tools.list_ports
        
        common_rfid_ports = ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyS0', '/dev/ttyS1', '/dev/ttyACM0', '/dev/ttyACM1']
        
        available_ports = serial.tools.list_ports.comports()
        available_port_names = [port.device for port in available_ports]
        
        plausible_ports = []
        
        for port in common_rfid_ports:
            if port in available_port_names:
                plausible_ports.append(port)
        
        for port in available_ports:
            port_name = port.device
            if port_name not in common_rfid_ports:
                description = port.description.lower()
                is_likely_rfid = any(keyword in description for keyword in 
                                   ['usb', 'serial', 'uart', 'ftdi', 'cp210', 'ch340'])
                if is_likely_rfid:
                    plausible_ports.append(port_name)
        
        return plausible_ports
    
    async def detect_all_readers_async(self) -> List[DetectedReader]:
        """
        Detect all supported readers on all plausible ports
        Returns list of detected readers
        """
        self.detected_readers.clear()
        plausible_ports = self.get_plausible_ports()
        
        if not plausible_ports:
            print("No plausible serial ports found for RFID reader detection")
            return self.detected_readers
        
        print(f"Scanning {len(plausible_ports)} ports with {len(self.detectors)} detector types...")
        
        detection_tasks = []
        for port in plausible_ports:
            for detector in self.detectors:
                task = self._detect_single_reader(port, detector)
                detection_tasks.append(task)
        
        if detection_tasks:
            results = await asyncio.gather(*detection_tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, DetectedReader):
                    self.detected_readers.append(result)
                elif isinstance(result, Exception):
                    print(f"Detection task failed: {result}")
        
        print(f"Detection complete. Found {len(self.detected_readers)} readers.")
        return self.detected_readers
    
    async def _detect_single_reader(self, port: str, detector: DeviceDetector) -> Optional[DetectedReader]:
        """
        Attempt to detect a specific reader type on a specific port
        Returns DetectedReader if successful, None otherwise
        """
        try:
            detection_command = detector._get_detection_command()
            response_data = await detector._send_detection_command(port, detection_command)
            
            if response_data and detector.validate_response(response_data):
                device_info = detector.get_device_info(response_data)
                reader_type = detector.get_reader_type()
                return DetectedReader(port, reader_type, device_info, type(detector))
        except Exception as e:
            print(f"Error detecting {detector.get_reader_type()} on {port}: {e}")
        
        return None


class R200DetectorAADD(DeviceDetector):
    """Detector for R200 readers using AADD protocol flavor"""
    
    def get_reader_type(self) -> str:
        return "R200 (AADD)"
    
    def _get_detection_command(self) -> bytes:
        from r200 import CMD_MODULE_INFO
        return bytes(CMD_MODULE_INFO)
    
    def validate_response(self, response_data: bytes) -> bool:
        """Validate R200 AADD response format"""
        try:
            if not response_data or len(response_data) < 3:
                return False
            
            if (response_data[0] == 0xAA and 
                len(response_data) > 6 and 
                response_data[1] == 0x01 and 
                response_data[2] == 0x03 and
                response_data[-1] == 0xDD):
                return True
                
        except Exception as e:
            print(f"R200 AADD validation error: {e}")
        
        return False
    
    async def detect_device_async(self, port: str) -> bool:
        """Detect R200 AADD device by sending CMD_MODULE_INFO and checking response format"""
        try:
            command = self._get_detection_command()
            response = await self._send_detection_command(port, command)
            return self.validate_response(response) if response else False
        except Exception as e:
            print(f"R200 AADD detection error on {port}: {e}")
            return False
    
    def get_device_info(self, response_data: bytes) -> str:
        """Extract ASCII device info from CMD_MODULE_INFO response"""
        try:
            if len(response_data) >= 22:  # Minimum length for valid response
                ascii_text = response_data[6:21].decode('ascii', errors='ignore').strip()
                return ascii_text if ascii_text else "R200 Reader"
        except Exception:
            pass
        return "R200 Reader"


class R200DetectorBB7E(DeviceDetector):
    """Detector for R200 readers using BB7E protocol flavor"""
    
    def get_reader_type(self) -> str:
        return "R200 (BB7E)"
    
    def _get_detection_command(self) -> bytes:
        from r200 import CMD_MODULE_INFO
        command = bytearray(bytes(CMD_MODULE_INFO))
        command[0], command[-1] = 0xBB, 0x7E
        return bytes(command)
    
    def validate_response(self, response_data: bytes) -> bool:
        """Validate R200 BB7E response format"""
        try:
            if not response_data or len(response_data) < 3:
                return False
            
            if (response_data[0] == 0xBB and 
                len(response_data) > 6 and 
                response_data[1] == 0x01 and 
                response_data[2] == 0x03 and
                response_data[-1] == 0x7E):
                return True
                
        except Exception as e:
            print(f"R200 BB7E validation error: {e}")
        
        return False
    
    async def detect_device_async(self, port: str) -> bool:
        """Detect R200 BB7E device by sending CMD_MODULE_INFO and checking response format"""
        try:
            command = self._get_detection_command()
            response = await self._send_detection_command(port, command)
            return self.validate_response(response) if response else False
        except Exception as e:
            print(f"R200 BB7E detection error on {port}: {e}")
            return False
    
    def get_device_info(self, response_data: bytes) -> str:
        """Extract ASCII device info from CMD_MODULE_INFO response"""
        try:
            if len(response_data) >= 22:  # Minimum length for valid response
                ascii_text = response_data[6:21].decode('ascii', errors='ignore').strip()
                return ascii_text if ascii_text else "R200 Reader"
        except Exception:
            pass
        return "R200 Reader"


class CF600Detector(DeviceDetector):
    """Detector for Chafon CF600 readers"""
    
    def get_reader_type(self) -> str:
        return "CF600"
    
    def _get_detection_command(self) -> bytes:
        from chafon import rfm_module_int, crc
        checksum = crc(rfm_module_int)
        command_with_checksum = rfm_module_int + bytes([(checksum & 0xFF00) >> 8, checksum & 0xFF])
        return command_with_checksum
    
    def validate_response(self, response_data: bytes) -> bool:
        """Validate CF600 response format and CRC"""
        try:
            if not response_data or len(response_data) < 4:
                return False
            
            if response_data[0] == 0xCF and len(response_data) >= 4:
                from chafon import crc
                crc_expected = (response_data[-2] << 8) | response_data[-1]
                crc_actual = crc(response_data[0:-2])
                
                if crc_actual == crc_expected:
                    return True
                    
        except Exception as e:
            print(f"CF600 validation error: {e}")
        
        return False
    
    async def detect_device_async(self, port: str) -> bool:
        """Detect CF600 device by sending module info command and checking CRC"""
        try:
            command = self._get_detection_command()
            response = await self._send_detection_command(port, command)
            return self.validate_response(response) if response else False
        except Exception as e:
            print(f"CF600 detection error on {port}: {e}")
            return False
    
    def get_device_info(self, response_data: bytes) -> str:
        """Extract device info from CF600 response"""
        try:
            if len(response_data) >= 4:
                return f"CF600 Reader (Response: {' '.join(f'{b:02X}' for b in response_data[:8])})"
        except Exception:
            pass
        return "CF600 Reader"


class HYB506Detector(DeviceDetector):
    """Detector for HYB506 readers"""
    
    def get_reader_type(self) -> str:
        return "HYB506"
    
    def _get_detection_command(self) -> bytes:
        from hyb506 import generate_command
        return bytes(generate_command(0x21))
    
    def validate_response(self, response_data: bytes) -> bool:
        """Validate HYB506 response format and CRC"""
        try:
            if not response_data or len(response_data) < 4:
                return False
            
            from hyb506 import crc16
            crc_expected = (response_data[-1] << 8) | response_data[-2]  # Note: byte order may vary
            crc_actual = crc16(response_data[0:-2])
            
            if crc_actual == crc_expected:
                return True
                
        except Exception as e:
            print(f"HYB506 validation error: {e}")
        
        return False
    
    async def detect_device_async(self, port: str) -> bool:
        """Detect HYB506 device by sending reader info command and checking CRC"""
        try:
            command = self._get_detection_command()
            response = await self._send_detection_command(port, command)
            return self.validate_response(response) if response else False
        except Exception as e:
            print(f"HYB506 detection error on {port}: {e}")
            return False
    
    def get_device_info(self, response_data: bytes) -> str:
        """Extract device info from HYB506 response"""
        try:
            if len(response_data) >= 4:
                result_length = response_data[0]
                return f"HYB506 Reader (Length: {result_length})"
        except Exception:
            pass
        return "HYB506 Reader"
