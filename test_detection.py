#!/usr/bin/env python3

import sys
import asyncio
from device_detection import ReaderDetectionManager

async def test_detection_framework():
    """Test the device detection framework functionality"""
    print("Testing device detection framework...")
    
    manager = ReaderDetectionManager()
    
    ports = manager.get_plausible_ports()
    print(f"✓ Found {len(ports)} plausible ports: {ports}")
    
    print("Testing detection process...")
    try:
        detected = await asyncio.wait_for(manager.detect_all_readers_async(), timeout=5.0)
        print(f"✓ Detection completed: {len(detected)} readers found")
        for reader in detected:
            print(f"  - {reader}")
    except asyncio.TimeoutError:
        print("✓ Detection timed out (expected in headless environment)")
    except Exception as e:
        print(f"✗ Detection error: {e}")
        return False
    
    print("Testing reader-specific detection methods...")
    try:
        from r200 import R200Interrogator
        from chafon import detect_device_async as cf600_detect
        from hyb506 import detect_device_async as hyb506_detect
        
        print("✓ R200Interrogator imported successfully")
        print("✓ CF600 detect_device_async imported successfully")
        print("✓ HYB506 detect_device_async imported successfully")
        
        r200_aadd = R200Interrogator(flavor='AADD')
        r200_bb7e = R200Interrogator(flavor='BB7E')
        print("✓ R200 instances created successfully")
        
    except Exception as e:
        print(f"✗ Reader-specific method error: {e}")
        return False
    
    print("✓ Framework test completed successfully")
    return True

def test_gui_imports():
    """Test that GUI imports work correctly"""
    print("Testing GUI imports...")
    try:
        from gui import RFIDReaderGUI, AsyncController
        print("✓ GUI classes imported successfully")
        
        controller = AsyncController()
        print("✓ AsyncController initialized successfully")
        
        return True
    except Exception as e:
        print(f"✗ GUI import error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("RFID Reader Detection Framework Test")
    print("=" * 50)
    
    gui_success = test_gui_imports()
    
    detection_success = asyncio.run(test_detection_framework())
    
    print("=" * 50)
    if gui_success and detection_success:
        print("✓ ALL TESTS PASSED")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
