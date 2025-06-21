import asyncio
from typing import Optional, List


class DetectedReader:
    """Represents a detected RFID reader with its connection details"""
    
    def __init__(self, port: str, reader_type: str, device_info: str, detector_class: type):
        self.port = port
        self.reader_type = reader_type
        self.device_info = device_info
        self.detector_class = detector_class
    
    def __str__(self):
        return f"{self.reader_type} on {self.port} - {self.device_info}"


class ReaderDetectionManager:
    """Manages detection of all supported reader types across available ports"""
    
    def __init__(self):
        self.detected_readers: List[DetectedReader] = []
    
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
        """Detect all supported readers on all plausible ports"""
        self.detected_readers.clear()
        plausible_ports = self.get_plausible_ports()
        
        if not plausible_ports:
            print("No plausible serial ports found for RFID reader detection")
            return self.detected_readers
        
        print(f"Scanning {len(plausible_ports)} ports with reader-specific detection methods...")
        
        detection_tasks = []
        for port in plausible_ports:
            task = self._detect_readers_on_port(port)
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
    
    async def _detect_readers_on_port(self, port: str) -> Optional[DetectedReader]:
        """Attempt to detect any supported reader type on a specific port"""
        from r200 import R200Interrogator
        from chafon import detect_device_async as cf600_detect
        from hyb506 import detect_device_async as hyb506_detect
        
        try:
            r200_aadd = R200Interrogator(flavor='AADD')
            success, device_info = await r200_aadd.detect_device_async(port)
            if success:
                print(f"✓ Detected R200 (AADD) on {port}")
                return DetectedReader(port, "R200 (AADD)", device_info, R200Interrogator)
        except Exception as e:
            print(f"Error detecting R200 AADD on {port}: {e}")
        
        try:
            r200_bb7e = R200Interrogator(flavor='BB7E')
            success, device_info = await r200_bb7e.detect_device_async(port)
            if success:
                print(f"✓ Detected R200 (BB7E) on {port}")
                return DetectedReader(port, "R200 (BB7E)", device_info, R200Interrogator)
        except Exception as e:
            print(f"Error detecting R200 BB7E on {port}: {e}")
        
        try:
            success, device_info = await cf600_detect(port)
            if success:
                print(f"✓ Detected CF600 on {port}")
                return DetectedReader(port, "CF600", device_info, type(None))
        except Exception as e:
            print(f"Error detecting CF600 on {port}: {e}")
        
        try:
            success, device_info = await hyb506_detect(port)
            if success:
                print(f"✓ Detected HYB506 on {port}")
                return DetectedReader(port, "HYB506", device_info, type(None))
        except Exception as e:
            print(f"Error detecting HYB506 on {port}: {e}")
        
        return None
