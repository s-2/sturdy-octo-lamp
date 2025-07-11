import sys
import asyncio
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QComboBox, QPushButton, QPlainTextEdit, QLabel, QStatusBar,
    QGroupBox, QMessageBox, QLineEdit, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
import serial.tools.list_ports
from transport import SerialTransport
from serialinterface import AsyncR200Interrogator
from device_detection import ReaderDetectionManager, DetectedReader

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
    readers_detected = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.interrogator: Optional[AsyncR200Interrogator] = None
        self.transport: Optional[SerialTransport] = None
        self.detected_readers = {}  # Dictionary to track reader instances by port
        self.detection_manager = ReaderDetectionManager()
    
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
            self.interrogator = None
            self.transport = None
    
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
            self.connection_status_changed.emit(False, f"Disconnect error: {str(e)}")
            self.interrogator = None
            self.transport = None
    
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
    
    async def detect_readers_async(self):
        """Detect all available readers and emit results"""
        try:
            detected_readers = await self.detection_manager.detect_all_readers_async()
            
            self.detected_readers.clear()
            for reader in detected_readers:
                self.detected_readers[reader.port] = reader
            
            self.readers_detected.emit(detected_readers)
            
        except Exception as e:
            self.error_occurred.emit(f"Detection error: {str(e)}")
    
    async def perform_single_read_on_reader(self, selected_reader: 'DetectedReader'):
        """Perform single read operation on a specific detected reader"""
        try:
            if "R200" in selected_reader.reader_type:
                controller = AsyncR200Interrogator()
                await controller.connect_to_port(selected_reader.port)
                result = await controller.perform_single_read()
                await controller.disconnect_from_port()
                
                if result:
                    hex_result = ''.join('{:02X}'.format(x) for x in result)
                    self.result_ready.emit(f"{selected_reader.reader_type}: {hex_result}")
                else:
                    self.result_ready.emit(f"{selected_reader.reader_type}: No tag detected")
            else:
                self.error_occurred.emit(f"Single read not yet implemented for {selected_reader.reader_type}")
                
        except Exception as e:
            self.error_occurred.emit(f"Read error on {selected_reader.reader_type}: {str(e)}")


class RFIDReaderGUI(QMainWindow):
    """Main GUI application for RFID reader control"""
    
    def __init__(self):
        super().__init__()
        self.controller = AsyncController()
        self.is_connected = False
        self.selected_reader = None
        self.detection_manager = ReaderDetectionManager()
        self.init_ui()
        self.setup_controller()
        self.setup_detection_manager()
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
        
        readers_group = QGroupBox("Detected Readers")
        readers_layout = QVBoxLayout(readers_group)
        
        self.readers_list = QListWidget()
        self.readers_list.setMaximumHeight(120)
        self.readers_list.itemSelectionChanged.connect(self.on_reader_selection_changed)
        readers_layout.addWidget(self.readers_list)
        
        readers_button_layout = QHBoxLayout()
        self.detect_readers_button = QPushButton("Detect Readers")
        self.detect_readers_button.clicked.connect(self.detect_readers)
        readers_button_layout.addWidget(self.detect_readers_button)
        readers_button_layout.addStretch()
        readers_layout.addLayout(readers_button_layout)
        
        layout.addWidget(readers_group)
        
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
        self.controller.readers_detected.connect(self._update_readers_list)
    
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
        
        port = self.port_combo.currentData()
        
        if not port:
            if ' - ' in port_text:
                port = port_text.split(' - ')[0]
            else:
                port = port_text
            
            port = port.split(' ✓')[0].split(' (')[0].strip()
        
        if not port or port == "No serial ports found":
            QMessageBox.warning(self, "Warning", "Please select a valid serial port")
            return
        
        flavor = 'AADD' if 'AADD' in self.flavor_combo.currentText() else 'BB7E'
        
        self.connect_button.setEnabled(False)
        self.status_bar.showMessage(f"Connecting to {port}...")
        
        self._schedule_async_task(self.controller.connect_to_port(port, flavor))
    
    def disconnect(self):
        """Disconnect from the current port"""
        self._schedule_async_task(self.controller.disconnect_from_port())
    
    def perform_single_read(self):
        """Perform a single RFID read operation"""
        if not self.selected_reader:
            QMessageBox.warning(self, "Warning", "Please detect and select a reader first")
            return
        
        self.single_read_button.setEnabled(False)
        self.status_bar.showMessage("Reading RFID tag...")
        
        self._schedule_async_task(self._perform_single_read_on_selected_reader())
    
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
        print(f"DEBUG: update_connection_status called with connected={connected}, message='{message}'")
        self.is_connected = connected
        
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.single_read_button.setEnabled(connected)
        
        if connected:
            self.connect_button.setText("Connected")
        else:
            self.connect_button.setText("Connect")
        
        self.status_bar.showMessage(message)
        print(f"DEBUG: Button states - Connect: {self.connect_button.isEnabled()}, Disconnect: {self.disconnect_button.isEnabled()}, Single Read: {self.single_read_button.isEnabled()}")
    
    def closeEvent(self, event):
        """Handle application close event"""
        if self.is_connected:
            self._schedule_async_task(self.controller.disconnect_from_port())
        event.accept()
    
    def setup_detection_manager(self):
        """Setup the detection manager"""
        QTimer.singleShot(1000, self.detect_readers)  # Delay 1 second after startup
    
    def detect_readers(self):
        """Trigger reader detection process"""
        self.detect_readers_button.setEnabled(False)
        self.detect_readers_button.setText("Detecting...")
        self.status_bar.showMessage("Detecting RFID readers...")
        
        self._schedule_async_task(self._perform_controller_detection())
    
    async def _perform_controller_detection(self):
        """Perform async reader detection using controller"""
        try:
            await self.controller.detect_readers_async()
        except Exception as e:
            self.status_bar.showMessage(f"Detection error: {str(e)}")
            self.display_error(f"Detection failed: {str(e)}")
        finally:
            self.detect_readers_button.setEnabled(True)
            self.detect_readers_button.setText("Detect Readers")
    
    def _update_readers_list(self, detected_readers):
        """Update the readers list widget with detected readers"""
        self.readers_list.clear()
        
        for reader in detected_readers:
            item = QListWidgetItem(str(reader))
            item.setData(1, reader)  # Store DetectedReader object in item data
            self.readers_list.addItem(item)
        
        if detected_readers:
            self.readers_list.setCurrentRow(0)  # Select first reader by default
            self.status_bar.showMessage(f"Found {len(detected_readers)} reader(s)")
        else:
            self.status_bar.showMessage("No readers detected")
        
        self.detect_readers_button.setEnabled(True)
        self.detect_readers_button.setText("Detect Readers")
    
    def on_reader_selection_changed(self):
        """Handle reader selection change"""
        current_item = self.readers_list.currentItem()
        if current_item:
            self.selected_reader = current_item.data(1)
            self.status_bar.showMessage(f"Selected: {self.selected_reader}")
        else:
            self.selected_reader = None
    
    async def _perform_single_read_on_selected_reader(self):
        """Perform single read operation on the currently selected reader"""
        try:
            if not self.selected_reader:
                self.display_error("No reader selected")
                return
            
            if "R200" in self.selected_reader.reader_type:
                controller = AsyncR200Interrogator()
                await controller.connect_to_port(self.selected_reader.port)
                result = await controller.perform_single_read()
                await controller.disconnect_from_port()
                self.display_result(f"Single read result from {self.selected_reader.reader_type}: {result}")
            else:
                self.display_error(f"Single read not yet implemented for {self.selected_reader.reader_type}")
                
        except Exception as e:
            self.display_error(f"Single read failed: {str(e)}")
        finally:
            self.single_read_button.setEnabled(True)
            self.status_bar.showMessage("Ready")
    
    def _schedule_async_task(self, coro):
        """Schedule an async task in the current event loop"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            QTimer.singleShot(0, lambda: asyncio.ensure_future(coro))


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
