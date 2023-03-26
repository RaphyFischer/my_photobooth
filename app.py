import sys, os, time, math
from datetime import datetime
import cv2
import gphoto2 as gp
from playsound import playsound
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QTimer, QObject
from PyQt5.QtGui import QImage, QPixmap, QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow
from MainWindow import Ui_MainWindow

WELCOME_MESSAGE = "Welcome to Hochzeit"
TARGET_DIR = "data/Hochzeit_xyz"
COUNTDOWN_SECONDS = 3
CAMERA_INDEX = 0

STREAM_CAPTURE = False                  # global variable indicating a open stream

# init the camera
callback_obj = gp.check_result(gp.use_python_logging())
CAMERA = gp.Camera()
try:
    CAMERA.init()
except:
    print("No Camera connected or connected Camera not compatible with gphoto2")

# create the target dir if necessary
if not os.path.exists(TARGET_DIR):
    os.makedirs(TARGET_DIR)

class StreamThread(QThread):
    changePixmap = pyqtSignal(QImage)

    def run(self):
        cap = cv2.VideoCapture(CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        print("Start streaming images")
        while STREAM_CAPTURE:
            ret, frame = cap.read()
            if ret:
                # https://stackoverflow.com/a/55468544/6622587
                rgbImage = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgbImage.shape
                bytesPerLine = ch * w
                convertToQtFormat = QImage(rgbImage.data, w, h, bytesPerLine, QImage.Format_RGB888)
                self.changePixmap.emit(convertToQtFormat)
        print("Stop streaming images")

class CountDownWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    @pyqtSlot()
    def do_work(self):
        print("Countdown started")
        for secs_left in range(COUNTDOWN_SECONDS, 0, -1):
            playsound(os.path.join(os.path.dirname(__file__), "ui/sounds/countdown_ping.wav"), block=False)
            self.progress.emit(secs_left)
            time.sleep(1)

        self.progress.emit(0)
        print('Capturing image')
        file_path = CAMERA.capture(gp.GP_CAPTURE_IMAGE)
        print('Camera file path: {0}/{1}'.format(file_path.folder, file_path.name))
        target = os.path.join(TARGET_DIR, "photobox_%s.jpg" %datetime.now().strftime("%m%d%Y_%H%M%S"))
        print('Copying image to', target)
        camera_file = CAMERA.file_get(file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL)
        camera_file.save(target)

        self.finished.emit()

class Window(QMainWindow, Ui_MainWindow):
    work_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.refreshWelcomeText()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refreshWelcomeText)
        self.timer.start()

        self.start_button.clicked.connect(self.startButtonClicked)
        self.home_button.clicked.connect(self.homeButtonClicked)
        self.capture_button.clicked.connect(self.captureButtonClicked)

        self.worker = CountDownWorker()
        self.worker_thread = QThread()
        self.worker.progress.connect(self.update_countdown)
        self.worker.finished.connect(self.finished_capture)
        self.work_requested.connect(self.worker.do_work)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.start()

    def refreshWelcomeText(self):
        message_and_time = datetime.now().strftime("%A %d. %b %Y   %H:%M")+"\n"+WELCOME_MESSAGE
        self.welcome_message.setText(message_and_time)

    @pyqtSlot(QImage)
    def setImage(self, image):
        self.stream.setPixmap(QPixmap.fromImage(image))

    def startButtonClicked(self):
        global STREAM_CAPTURE

        print("Start Button pressed")
        STREAM_CAPTURE = True
        self.stackedWidget.setCurrentIndex(1)

        # start streaming thread
        th = StreamThread(self)
        th.changePixmap.connect(self.setImage)
        th.start()

    def homeButtonClicked(self):
        global STREAM_CAPTURE

        print("Home Button pressed")
        STREAM_CAPTURE = False
        self.stackedWidget.setCurrentIndex(0)

    def captureButtonClicked(self):
        self.work_requested.emit()

    def update_countdown(self, secs_left):
        self.capture_button.setIcon(QIcon())
        if secs_left > 0:
            self.capture_button.setText(str(secs_left))
        else:
            self.capture_button.setText("Click")
        #self.capture_button.repaint()

    def finished_capture(self):
        self.capture_button.setText("")
        self.capture_button.setIcon(QIcon(":/images/images/aperature.png"))
        #self.capture_button.repaint()

    def setText(self, secs_left):
        self.capture_button.setText(str(secs_left))
        #self.capture_button.repaint()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    win.show()
    #win.showFullScreen()
    sys.exit(app.exec())
    CAMERA.exit()