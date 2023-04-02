import sys, os, time
from datetime import datetime
import subprocess
import functools
import cv2
import gphoto2 as gp
from playsound import playsound
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QTimer, QObject
from PyQt5.QtGui import QImage, QPixmap, QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow
from MainWindow import Ui_MainWindow

WELCOME_MESSAGE = "Welcome to our Photobooth"
TARGET_DIR = "data/test"
COUNTDOWN_SECONDS = 5
COUNTDOWN_SOUND = os.path.join(os.path.dirname(__file__), "ui/sounds/countdown_ping.wav")
PREVIEW_TIME_SECONDS = 5
PRINTER_NAME = "CP400"
CAMERA_INDEX = 2
SHOW_PRINT = True
SHOW_DELETE = True
SHOW_SHARE = True

STREAM_CAPTURE = False                  # global variable indicating a open stream
FREEZE_STREAM = False

# init the camera
callback_obj = gp.check_result(gp.use_python_logging())
CAMERA = gp.Camera()
try:
    CAMERA.init()
except:
    print("No Camera connected or connected Camera not compatible with gphoto2")

# create the target dir if necessary
os.makedirs(os.path.join(os.path.dirname(__file__), TARGET_DIR),exist_ok=True)

class StreamThread(QThread):
    changePixmap = pyqtSignal(QImage)

    def run(self):
        height, width, channel = 720, 1280, 3
        scale = 1.2
        cropped_width = int(3*height/2)                     #crop black borders of 16:9 monitor
        width_to_crop = width-cropped_width
        scaled_width = int(cropped_width*scale)
        scaled_height = int(height*scale)
        
        cap = cv2.VideoCapture(CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        while True:
            ret, frame = cap.read()
            if ret:
                frame = cv2.flip(frame, 1)
                rgbImage = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgbImage = rgbImage[:,int(width_to_crop/2):int(width-(width_to_crop/2)),:].copy()
                rgbImage_resized = cv2.resize(rgbImage, (scaled_width, scaled_height), interpolation = cv2.INTER_AREA)
                convertToQtFormat = QImage(rgbImage_resized.data, scaled_width, scaled_height, channel*scaled_width, QImage.Format_RGB888)
                if not FREEZE_STREAM: self.changePixmap.emit(convertToQtFormat)

class CaptureWorker(QObject):
    progress = pyqtSignal(int)

    @pyqtSlot()
    def run(self):
        global FREEZE_STREAM, FILE_NAME, PREVIEW_TIME_SECONDS

        print("Countdown started")
        for secs_left in range(COUNTDOWN_SECONDS, 0, -1):
            self.progress.emit(secs_left)
            time.sleep(1)

        print('Capturing image')
        FILE_NAME = os.path.join(os.path.dirname(__file__), TARGET_DIR, "photobox_%s.jpg" %datetime.now().strftime("%m%d%Y_%H%M%S"))
        self.progress.emit(0)
        #gphoto2 --filename data/test/photobox_\%m\%d\%Y_\%H\%M\%S.jpg --capture-image-and-download
        subprocess.Popen(["gphoto2", "--filename", FILE_NAME, "--capture-image-and-download", "--force-overwrite"])
        time.sleep(0.2)
        self.progress.emit(-1)

        print('Showing preview')
        FREEZE_STREAM = True
        while PREVIEW_TIME_SECONDS > 0:
            time.sleep(0.01)
            PREVIEW_TIME_SECONDS -= 0.01
        FREEZE_STREAM = False

class Window(QMainWindow, Ui_MainWindow):
    work_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.refreshWelcomeText()
        self.overlay_buttons_on_stream()
        self.print_button.setVisible(False)
        self.delete_button.setVisible(False)
        self.download_button.setVisible(False)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refreshWelcomeText)
        self.timer.start()

        self.start_button.clicked.connect(self.startButtonClicked)
        self.home_button.clicked.connect(self.homeButtonClicked)
        self.delete_button.clicked.connect(self.deleteButtonClicked)
        self.capture_button.clicked.connect(self.captureButtonClicked)
        self.download_button.clicked.connect(self.downloadButtonClicked)
        self.print_button.clicked.connect(self.printButtonClicked)
        self.back_button.clicked.connect(self.homeButtonClicked)

        # start capture worker
        self.worker = CaptureWorker()
        self.worker_thread = QThread()
        self.worker.progress.connect(self.update_countdown)
        self.work_requested.connect(self.worker.run)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.start()

        # start streaming thread
        th = StreamThread(self)
        th.changePixmap.connect(self.setImage)
        th.start()

        # start web server hosting images
        if SHOW_SHARE: th = ServerThread(self).start()

    def refreshWelcomeText(self):
        message_and_time = datetime.now().strftime("%A %d. %b %Y   %H:%M")+"\n"+WELCOME_MESSAGE
        self.welcome_message.setText(message_and_time)

    def overlay_buttons_on_stream(self):
        self.photo_page_grid.addWidget(self.stream, 0, 0, 0, 0)
        self.photo_page_grid.addLayout(self.photo_page_buttons, 4, 0, 0, 0)

    @pyqtSlot(QImage)
    def setImage(self, image):
        self.stream.setPixmap(QPixmap.fromImage(image))

    def startButtonClicked(self):
        print("Start Button pressed")
        self.showImageControlButtons(False)
        self.stackedWidget.setCurrentIndex(1)
        self.captureButtonClicked()

    def captureButtonClicked(self):
        global PREVIEW_TIME_SECONDS
        PREVIEW_TIME_SECONDS = -1                           # stop preview
        self.capture_button.setEnabled(False)
        self.showImageControlButtons(False)
        self.work_requested.emit()

    def update_countdown(self, secs_left):
        self.capture_button.setIcon(QIcon())
        if secs_left > 0:
            subprocess.Popen(["aplay", COUNTDOWN_SOUND])
            self.capture_button.setText(str(secs_left))
        elif secs_left == 0:                                # at capture
            self.capture_button.setText("Click")
        elif secs_left < 0:                                 # after capture
            self.capture_button.setText("")
            self.capture_button.setIcon(QIcon(":/images/images/aperature.png"))
            self.showImageControlButtons(True)
            self.capture_button.setEnabled(True)      

    def homeButtonClicked(self):
        print("Home Button pressed")
        self.stackedWidget.setCurrentIndex(0)
    
    def deleteButtonClicked(self):
        print("Delete last Photo")
        os.remove(FILE_NAME)

    def printButtonClicked(self):
        # use CUPS+Gutenprint to print Image via Selpy CP400
        print("Printing photo")
        subprocess.Popen(["lpr", "-P", PRINTER_NAME, FILE_NAME])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window()
    #win.show()
    win.showFullScreen()
    sys.exit(app.exec())