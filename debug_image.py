import sys
import os
from PyQt6.QtWidgets import QApplication, QLabel, QWidget
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

def test_image_load():
    app = QApplication(sys.argv)
    
    # Path from your directory listing
    path = "assests/img/idle/sitting_leg_hanging_1.png"
    
    print(f"Checking path: {os.path.abspath(path)}")
    print(f"File exists: {os.path.exists(path)}")
    
    if not os.path.exists(path):
        return
        
    pixmap = QPixmap(path)
    print(f"Pixmap is null: {pixmap.isNull()}")
    print(f"Pixmap size: {pixmap.size().width()}x{pixmap.size().height()}")
    
    # Show a simple window to see if it renders at all
    w = QWidget()
    w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    # NO transparency for this test to see if it's a transparency issue
    l = QLabel(w)
    l.setPixmap(pixmap)
    w.show()
    
    # Auto close after 3 seconds
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(3000, app.quit)
    app.exec()

if __name__ == "__main__":
    test_image_load()
