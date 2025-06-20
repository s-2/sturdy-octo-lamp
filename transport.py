import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Callable, Any
import serial_asyncio


class Transport(ABC):
    """Abstract base class for all transport implementations (serial, Bluetooth LE, etc.)"""
    
    def __init__(self):
        self.is_connected = False
        self.data_callback: Optional[Callable[[bytes], None]] = None
        self.connection_lost_callback: Optional[Callable[[Exception], None]] = None
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the device. Returns True if successful."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the device."""
        pass
    
    @abstractmethod
    async def write(self, data: bytes) -> None:
        """Write data to the device."""
        pass
    
    def set_data_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback function to handle received data."""
        self.data_callback = callback
    
    def set_connection_lost_callback(self, callback: Callable[[Exception], None]) -> None:
        """Set callback function to handle connection loss."""
        self.connection_lost_callback = callback


class SerialTransportProtocol(asyncio.Protocol):
    """Protocol handler for serial communication."""
    
    def __init__(self, transport_instance):
        self.transport_instance = transport_instance
        self.transport = None
    
    def connection_made(self, transport):
        self.transport = transport
        self.transport_instance.transport = transport
        self.transport_instance.is_connected = True
        self.transport_instance.connection_event.set()  # Signal connection is ready
        print(f'Serial port opened: {transport}')
        
        if hasattr(transport, 'serial'):
            transport.serial.rts = False
    
    def data_received(self, data: bytes):
        if self.transport_instance.data_callback:
            self.transport_instance.data_callback(data)
    
    def connection_lost(self, exc):
        print('Serial port closed')
        self.transport_instance.is_connected = False
        self.transport_instance.connection_event.clear()  # Clear the event
        if self.transport_instance.connection_lost_callback:
            self.transport_instance.connection_lost_callback(exc)


class SerialTransport(Transport):
    """Concrete implementation for serial port communication."""
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.08):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.transport = None
        self.protocol = None
        self.connection_event = asyncio.Event()
    
    async def connect(self) -> bool:
        """Connect to the serial port."""
        try:
            self.connection_event.clear()
            
            loop = asyncio.get_event_loop()
            self.protocol = SerialTransportProtocol(self)
            
            transport, protocol = await serial_asyncio.create_serial_connection(
                loop, 
                lambda: self.protocol,
                self.port, 
                baudrate=self.baudrate
            )
            
            await asyncio.wait_for(self.connection_event.wait(), timeout=1.0)
            return self.is_connected
        except Exception as e:
            print(f"Failed to connect to {self.port}: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the serial port."""
        if self.transport:
            self.transport.close()
            self.is_connected = False
    
    async def write(self, data: bytes) -> None:
        """Write data to the serial port."""
        if not self.is_connected or not self.transport:
            raise RuntimeError("Not connected to serial port")
        
        self.transport.write(data)
        print(f'> {" ".join("{:02X}".format(c) for c in data)}')


class BluetoothTransport(Transport):
    """Placeholder for future Bluetooth LE implementation using bleak library."""
    
    def __init__(self, device_address: str):
        super().__init__()
        self.device_address = device_address
    
    async def connect(self) -> bool:
        raise NotImplementedError("Bluetooth LE transport not yet implemented")
    
    async def disconnect(self) -> None:
        raise NotImplementedError("Bluetooth LE transport not yet implemented")
    
    async def write(self, data: bytes) -> None:
        raise NotImplementedError("Bluetooth LE transport not yet implemented")
