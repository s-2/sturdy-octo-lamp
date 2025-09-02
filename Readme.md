This project implements an abstraction layer to the communication with RAIN RFID readers connected via serial ports.

The reference implementation is for the R200 reader protocol, which is defined as per "R200 user protocol V2.3.3.pdf" in the "docs" folder.
The R200 reader comes in two flavors, only differing in the protocol start and end byte. For regular R200 the start byte is 0xAA and the end byte is 0xDD. However, a different flavor of YRM100x readers is available that use 0xBB as start and 0x7E as end byte.

The framework is structured to allow easy implementation of further reader protocols in the future, or add a GUI (e.g. based on Tkinter or PyQt6) later.

CLI
- Unified entry point: pyrainrfid.py
- Autodetect readers:
  python3 pyrainrfid.py --autodetect
- Single read with explicit reader/port:
  python3 pyrainrfid.py --single --reader-type r200-aadd --port /dev/ttyUSB0
  python3 pyrainrfid.py --single --reader-type r200-bb7e --port /dev/ttyUSB0
  python3 pyrainrfid.py --single --reader-type hyb506 --port /dev/ttyUSB1
  python3 pyrainrfid.py --single --reader-type chafon --port /dev/ttyUSB2
- Autodetect and perform single read on each detected reader:
  python3 pyrainrfid.py --autodetect --single
- Launch GUI:
  python3 pyrainrfid.py --mode gui

Notes
- HYB506 and Chafon read_single() currently return ASCII hex of the payload bytes with CRC verified.
