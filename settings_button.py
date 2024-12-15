# Settings Button is hidden behind welcome message
# Settings can be reached by long pressig (https://stackoverflow.com/a/13851527) the text in the label
from PyQt6 import QtWidgets, QtCore

class SettingsButton(QtWidgets.QPushButton):
    longclicked = QtCore.pyqtSignal(bool)

    def __init__(self, *args, **kwargs):
        QtWidgets.QPushButton.__init__(self, *args, **kwargs)
        self.setAutoRepeat(True)
        self.setAutoRepeatInterval(1000)
        self.clicked.connect(self.handleClicked)
        self.long_press_duration = 5000
        self.setFlat(True)
        self.setStyleSheet("QPushButton { background-color: transparent; border: 0px}");
        self.setMinimumSize(2000, 2000)

    def handleClicked(self):
        #print(self.long_press_duration)
        if self.isDown():
            if self.long_press_duration > 0:
                self.long_press_duration -= 50
                self.setAutoRepeatInterval(50)
            else:
                print('Button long pressed')
                self.long_press_duration = 5000
                self.setAutoRepeatInterval(1000)
                self.longclicked.emit(True)
        else:
            self.long_press_duration = 5000
            self.setAutoRepeatInterval(1000)

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    button = SettingsButton('Press and Hold to reach settings')
    button.show()
    sys.exit(app.exec_())