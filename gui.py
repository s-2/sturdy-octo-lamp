import sys
import asyncio
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QComboBox, QPushButton, QPlainTextEdit, QLabel, QStatusBar,
    QGroupBox, QMessageBox, QLineEdit
)
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
import serial.tools.list_ports
from transport import SerialTransport
from serialinterface import AsyncR200Interrogator

try:
    import qasyncio
    QASYNCIO_AVAILABLE = True
except ImportError:
    QASYNCIO_AVAILABLE = False


class AsyncController(QObject):
    """Controller to handle async operations with proper asyncio integration"""
    
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    connection_status_changed = pyqtSignal(bool, str)
    
    def __init__(self):
        super().__init__()
        self.interrogator: Optional[AsyncR200Interrogator] = None
        self.transport: Optional[SerialTransport] = None
    
    async def connect_to_port(self, port: str, flavor: str = 'AADD'):
        """Connect to the specified serial port"""
        try:
            self.transport = SerialTransport(port)
            self.interrogator = AsyncR200Interrogator(self.transport, flavor)
            
            success = await self.interrogator.connect()
            if success:
                self.connection_status_changed.emit(True, f"Connected to {port}")
            else:
                self.connection_status_changed.emit(False, f"Failed to connect to {port}")
        except Exception as e:
            self.error_occurred.emit(f"Connection error: {str(e)}")
            self.connection_status_changed.emit(False, f"Error: {str(e)}")
    
    async def disconnect_from_port(self):
        """Disconnect from the current port"""
        try:
            if self.interrogator:
                await self.interrogator.disconnect()
                self.interrogator = None
                self.transport = None
                self.connection_status_changed.emit(False, "Disconnected")
        except Exception as e:
            self.error_occurred.emit(f"Disconnect error: {str(e)}")
    
    async def perform_single_read(self):
        """Perform a single RFID read operation"""
        try:
            if not self.interrogator:
                self.error_occurred.emit("Not connected to any device")
                return
            
            result = await self.interrogator.read_single()
            if result:
                hex_result = ''.join('{:02X}'.format(x) for x in result)
                self.result_ready.emit(hex_result)
            else:
                self.result_ready.emit("No tag detected or timeout")
        except Exception as e:
            self.error_occurred.emit(f"Read error: {str(e)}")


class RFIDReaderGUI(QMainWindow):
    """Main GUI application for RFID reader control"""
    
    def __init__(self):
        super().__init__()
        self.controller = AsyncController()
        self.is_connected = False
        self.init_ui()
        self.setup_controller()
        self.refresh_ports()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("RFID Reader Control - R200")
        self.setGeometry(100, 100, 600, 500)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        connection_group = QGroupBox("Connection")
        connection_layout = QVBoxLayout(connection_group)
        
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Serial Port:"))
        
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(200)
        port_layout.addWidget(self.port_combo)
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_ports)
        port_layout.addWidget(self.refresh_button)
        
        port_layout.addStretch()
        connection_layout.addLayout(port_layout)
        
        flavor_layout = QHBoxLayout()
        flavor_layout.addWidget(QLabel("Protocol:"))
        
        self.flavor_combo = QComboBox()
        self.flavor_combo.addItems(["AADD (Standard R200)", "BB7E (YRM100x)"])
        flavor_layout.addWidget(self.flavor_combo)
        flavor_layout.addStretch()
        connection_layout.addLayout(flavor_layout)
        
        button_layout = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        button_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect)
        self.disconnect_button.setEnabled(False)
        button_layout.addWidget(self.disconnect_button)
        
        button_layout.addStretch()
        connection_layout.addLayout(button_layout)
        
        layout.addWidget(connection_group)
        
        operations_group = QGroupBox("Operations")
        operations_layout = QVBoxLayout(operations_group)
        
        self.single_read_button = QPushButton("Single Read (CMD_SINGLE)")
        self.single_read_button.clicked.connect(self.perform_single_read)
        self.single_read_button.setEnabled(False)
        operations_layout.addWidget(self.single_read_button)
        
        layout.addWidget(operations_group)
        
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)
        
        results_layout.addWidget(QLabel("EPC Data (ASCII Hex):"))
        
        self.results_text = QPlainTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setFont(QFont("Courier", 10))
        self.results_text.setMaximumBlockCount(1000)  # Limit history
        results_layout.addWidget(self.results_text)
        
        clear_button = QPushButton("Clear Results")
        clear_button.clicked.connect(self.results_text.clear)
        results_layout.addWidget(clear_button)
        
        layout.addWidget(results_group)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Select a port and connect")
    
    def setup_controller(self):
        """Setup the async controller"""
        self.controller.result_ready.connect(self.display_result)
        self.controller.error_occurred.connect(self.display_error)
        self.controller.connection_status_changed.connect(self.update_connection_status)
    
    def refresh_ports(self):
        """Refresh the list of available serial ports with auto-detection"""
        self.port_combo.clear()
        
        common_rfid_ports = ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyS0', '/dev/ttyS1', '/dev/ttyACM0', '/dev/ttyACM1']
        
        available_ports = serial.tools.list_ports.comports()
        available_port_names = [port.device for port in available_ports]
        
        existing_common_ports = []
        for port in common_rfid_ports:
            if port in available_port_names:
                self.port_combo.addItem(f"{port} ✓", port)
                existing_common_ports.append(port)
        
        for port in common_rfid_ports:
            if port not in available_port_names:
                self.port_combo.addItem(f"{port} (not found)", port)
        
        if existing_common_ports and len(available_ports) > len(existing_common_ports):
            self.port_combo.insertSeparator(self.port_combo.count())
        
        for port in available_ports:
            port_name = port.device
            if port_name not in common_rfid_ports:
                description = port.description.lower()
                is_likely_rfid = any(keyword in description for keyword in 
                                   ['usb', 'serial', 'uart', 'ftdi', 'cp210', 'ch340'])
                
                if is_likely_rfid:
                    display_text = f"{port_name} - {port.description} 📡"
                else:
                    display_text = f"{port_name} - {port.description}"
                
                self.port_combo.addItem(display_text, port_name)
        
        if existing_common_ports:
            self.port_combo.setCurrentIndex(0)
            self.status_bar.showMessage(f"Auto-detected: {existing_common_ports[0]}")
        elif available_ports:
            self.port_combo.setCurrentIndex(0)
            self.status_bar.showMessage("No common RFID ports found - select manually")
        else:
            self.port_combo.addItem("No serial ports found")
            self.status_bar.showMessage("No serial ports detected")
    
    def toggle_connection(self):
        """Toggle connection to the selected port"""
        if not self.is_connected:
            self.connect()
        else:
            self.disconnect()
    
    def connect(self):
        """Connect to the selected serial port"""
        port_text = self.port_combo.currentText()
        
        if ' - ' in port_text:
            port = self.port_combo.currentData() or port_text.split(' - ')[0]
        else:
            port = port_text
        
        if not port or port == "No additional ports found":
            QMessageBox.warning(self, "Warning", "Please select a valid serial port")
            return
        
        flavor = 'AADD' if 'AADD' in self.flavor_combo.currentText() else 'BB7E'
        
        self.connect_button.setEnabled(False)
        self.status_bar.showMessage(f"Connecting to {port}...")
        
        asyncio.create_task(self.controller.connect_to_port(port, flavor))
    
    def disconnect(self):
        """Disconnect from the current port"""
        asyncio.create_task(self.controller.disconnect_from_port())
    
    def perform_single_read(self):
        """Perform a single RFID read operation"""
        if not self.is_connected:
            QMessageBox.warning(self, "Warning", "Please connect to a device first")
            return
        
        self.single_read_button.setEnabled(False)
        self.status_bar.showMessage("Reading RFID tag...")
        
        asyncio.create_task(self.controller.perform_single_read())
    
    def display_result(self, result: str):
        """Display the read result in the text area"""
        self.results_text.appendPlainText(f"EPC: {result}")
        self.status_bar.showMessage("Read completed")
        self.single_read_button.setEnabled(True)
    
    def display_error(self, error: str):
        """Display error message"""
        self.results_text.appendPlainText(f"ERROR: {error}")
        self.status_bar.showMessage("Error occurred")
        self.single_read_button.setEnabled(self.is_connected)
    
    def update_connection_status(self, connected: bool, message: str):
        """Update the connection status"""
        self.is_connected = connected
        
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.single_read_button.setEnabled(connected)
        
        if connected:
            self.connect_button.setText("Connected")
        else:
            self.connect_button.setText("Connect")
        
        self.status_bar.showMessage(message)
    
    def closeEvent(self, event):
        """Handle application close event"""
        if self.is_connected:
            asyncio.create_task(self.controller.disconnect_from_port())
        event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("RFID Reader Control")
    app.setApplicationVersion("1.0")
    
    if QASYNCIO_AVAILABLE:
        loop = qasyncio.QEventLoop(app)
        asyncio.set_event_loop(loop)
    else:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    window = RFIDReaderGUI()
    window.show()
    
    try:
        if QASYNCIO_AVAILABLE:
            loop.run_forever()
        else:
            timer = QTimer()
            timer.timeout.connect(lambda: loop.run_until_complete(asyncio.sleep(0.01)))
            timer.start(10)  # Process asyncio tasks every 10ms
            
            sys.exit(app.exec())
    except KeyboardInterrupt:
        pass
    finally:
        if not QASYNCIO_AVAILABLE:
            loop.close()


if __name__ == '__main__':
    main()
