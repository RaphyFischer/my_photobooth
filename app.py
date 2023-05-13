import sys, os, time
from datetime import datetime
import subprocess
import functools
import cv2
from PIL import Image
import qrcode
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QTimer, QObject
from PyQt5.QtGui import QImage, QPixmap, QIcon, QFontDatabase
from PyQt5.QtWidgets import QApplication, QMainWindow
from MainWindow import Ui_MainWindow
from http.server import HTTPServer, SimpleHTTPRequestHandler
from PyAccessPoint import pyaccesspoint
import netifaces as ni
from list_cameras import list_stream_cameras
from settings_button import SettingsButton

### Edit Settings here
WELCOME_MESSAGE = "Welcome to our Photobooth"
TARGET_DIR = "data/test"
COUNTDOWN_SECONDS = 5
COUNTDOWN_SOUND = "ui/sounds/countdown_ping.wav"
BACKGROUND_IMAGE = "backgrounds/background.png"     # remember to add your custom background image to ui/resources.qrc before specifing it here
PREVIEW_TIME_SECONDS = 5
PRINTER_NAME = "CP400"
SHOW_COLLAGE = False
SHOW_FILTER = False
SHOW_SAVE = True                                    #save button is also back button. So this is always visible
SHOW_DELETE = True
SHOW_RECAPTURE = True
SHOW_SHARE = True
SHOW_PRINT = True
SHOW_BUTTON_TEXT = False
WEBSERVER_PORT = 1234
ACCESS_POINT_SSID = "photobox"
ACCESS_POINT_PW = "my_photobooth"
###

CAMERA_INDEX = list_stream_cameras()
FILE_NAME = ""                          # holds last filename
FREEZE_STREAM = False
proc = subprocess.run('echo /sys/class/net/*/wireless | awk -F"/" "{ print \$5 }"', shell=True, stdout = subprocess.PIPE)
WEBSERVER_DEVICE = proc.stdout.decode("utf8").rstrip("\n")
try: WEBSERVER_IP = ni.ifaddresses(WEBSERVER_DEVICE)[ni.AF_INET][0]['addr']
except: WEBSERVER_IP="127.0.0.1"

# create the target dir if necessary
os.makedirs(os.path.join(os.path.dirname(__file__), TARGET_DIR),exist_ok=True)

class ServerThread(QThread):
    def run(self):
        '''
        print("Creating access point")
        access_point = pyaccesspoint.AccessPoint(wlan=WEBSERVER_DEVICE, ssid=ACCESS_POINT_SSID, password=ACCESS_POINT_PW)
        access_point.start()
        '''

        print("Hosting Webserver on %s:%s" %(WEBSERVER_IP, WEBSERVER_PORT))
        MyHandler = functools.partial(SimpleHTTPRequestHandler, directory=TARGET_DIR)
        httpd = HTTPServer((WEBSERVER_IP, WEBSERVER_PORT), MyHandler)
        httpd.serve_forever()

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
        preview_countdown = PREVIEW_TIME_SECONDS
        while preview_countdown > 0 and FREEZE_STREAM:
            time.sleep(0.01)
            preview_countdown -= 0.01
        FREEZE_STREAM = False

class Window(QMainWindow, Ui_MainWindow):
    work_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.loadBackgroundImage()
        self.refreshWelcomeText()
        self.setRecaptureMode()
        self.overlay_buttons_on_stream()
        self.hidden_settings = SettingsButton(self.welcome_message)
        self.collage_button.setVisible(SHOW_COLLAGE)
        self.filters_button.setVisible(SHOW_FILTER)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refreshWelcomeText)
        self.timer.start()

        self.hidden_settings.longclicked.connect(self.settingsClicked)
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
        self.worker.progress.connect(self.updateCountdown)
        self.work_requested.connect(self.worker.run)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.start()

        # start streaming thread
        th = StreamThread(self)
        th.changePixmap.connect(self.setImage)
        th.start()

        # start web server hosting images
        if SHOW_SHARE: th = ServerThread(self).start()

    def loadBackgroundImage(self):
        style = "QWidget#start_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %BACKGROUND_IMAGE
        self.start_page.setStyleSheet(style)
        style = "QWidget#photo_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %BACKGROUND_IMAGE
        self.photo_page.setStyleSheet(style)
        style = "QWidget#download_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %BACKGROUND_IMAGE
        self.download_page.setStyleSheet(style)
        style = "QWidget#setup_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %BACKGROUND_IMAGE
        self.setup_page.setStyleSheet(style)

    def refreshWelcomeText(self):
        message_and_time = datetime.now().strftime("%A %d. %b %Y   %H:%M")+"\n"+WELCOME_MESSAGE
        self.welcome_message.setText(message_and_time)

    def setRecaptureMode(self):
        # if recapture is activated show home button in photo view else show save button
        icon = QIcon()
        if SHOW_RECAPTURE:icon.addPixmap(QPixmap(":/files/icons/home.png"), QIcon.Normal, QIcon.Off)
        else: icon.addPixmap(QPixmap(":/files/icons/save.png"), QIcon.Normal, QIcon.Off)
        self.home_button.setIcon(icon)

    def overlay_buttons_on_stream(self):
        self.photo_page_grid.addWidget(self.stream, 0, 0, 0, 0)
        self.photo_page_grid.addLayout(self.photo_page_buttons, 4, 0, 0, 0)

        if SHOW_BUTTON_TEXT:
            self.home_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.delete_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.download_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.print_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)

    def settingsClicked(self):
        print("Go to settings")
        self.stackedWidget.setCurrentIndex(3)

    @pyqtSlot(QImage)
    def setImage(self, image):
        self.stream.setPixmap(QPixmap.fromImage(image))

    def startButtonClicked(self):
        print("Start Button pressed")
        self.showImageControlButtons(False)
        self.stackedWidget.setCurrentIndex(1)
        self.captureButtonClicked()

    def captureButtonClicked(self):
        global FREEZE_STREAM
        FREEZE_STREAM = False                       # stops the preview
        self.capture_button.setEnabled(False)
        self.showImageControlButtons(False)
        self.work_requested.emit()

    def updateCountdown(self, secs_left):
        self.capture_button.setIcon(QIcon())
        if secs_left > 0:
            file = os.path.join(os.path.dirname(__file__), COUNTDOWN_SOUND)
            subprocess.Popen(["aplay", file])
            self.capture_button.setText(str(secs_left))
        elif secs_left == 0:                                # at capture
            self.capture_button.setText("Click")
        elif secs_left < 0:                                 # after capture
            self.capture_button.setText("")
            self.capture_button.setIcon(QIcon(":/files/icons/aperature.png"))
            self.showImageControlButtons(True)
            self.capture_button.setEnabled(True)      

    def homeButtonClicked(self):
        print("Home Button pressed")
        self.stackedWidget.setCurrentIndex(0)
    
    def deleteButtonClicked(self):
        print("Delete last Photo")
        try:
            os.remove(FILE_NAME)
        except FileNotFoundError:
            pass
        self.homeButtonClicked()

    def printButtonClicked(self):
        # use CUPS+Gutenprint to print Image via Selpy CP400
        print("Printing photo")
        subprocess.Popen(["lpr", "-P", PRINTER_NAME, FILE_NAME])

    def downloadButtonClicked(self):
        print("Switch to download site")

        # create first qr code with wifi login
        text = '<html><head/><body><p><span style=" font-size:26pt; font-weight:600;">Schritt 1:</span></p><p><span style=" font-size:18pt;">Verbinden Sie das Gerät mit dem Wifi Hotspot</span></p><p><span style=" font-size:18pt;">SSID: </span><span style=" font-size:18pt; font-weight:600;">%s</span></p><p><span style=" font-size:18pt;">Passwort: </span><span style=" font-size:18pt; font-weight:600; color:#000000;">%s</span></p></body></html>' %(ACCESS_POINT_SSID, ACCESS_POINT_PW)
        self.instructions_step1.setText(text)
        self.instructions_step1.setMargin(20)
        wifi = "WIFI:S:%s;T:WPA;P:%s;;" %(ACCESS_POINT_SSID, ACCESS_POINT_PW)
        img = np.array(qrcode.make(wifi).resize((600,600), Image.NEAREST))
        img = np.stack((img,)*3, axis=-1)
        qt_img = QImage(img.data, img.shape[1], img.shape[0], img.shape[1]*img.shape[2], QImage.Format_RGB888)
        self.qr_code1.setPixmap(QPixmap.fromImage(qt_img))

        # create second qr code with image url
        text = '<html><head/><body><p><span style=" font-size:26pt; font-weight:600;">Schritt2:</span></p><p><span style=" font-size:18pt;">Scannen Sie den QR-Code<br/>um das Bild auf Ihrem Handy herunterzuladen<br/>(lange gedrückt halten -&gt; Bild speichern)</span></p></body></html>'
        self.instructions_step2.setText(text)
        self.instructions_step2.setMargin(20)
        url = 'http://%s:%s/%s' %(WEBSERVER_IP, WEBSERVER_PORT, FILE_NAME.split("/")[-1])
        img = np.array(qrcode.make(url).resize((600,600), Image.NEAREST))
        img = np.stack((img,)*3, axis=-1)
        qt_img = QImage(img.data, img.shape[1], img.shape[0], img.shape[1]*img.shape[2], QImage.Format_RGB888)
        self.qr_code2.setPixmap(QPixmap.fromImage(qt_img))

        self.stackedWidget.setCurrentIndex(2)

    def showImageControlButtons(self, visible):
        if visible:                                                     # icon menue is visible
            self.home_button.setVisible(True)
            self.delete_button.setVisible(SHOW_DELETE)
            self.capture_button.setVisible(SHOW_RECAPTURE)
            self.download_button.setVisible(SHOW_SHARE)
            self.print_button.setVisible(SHOW_PRINT)
        else:                                                           # capture countdown is running
            self.capture_button.setVisible(True)
            self.home_button.setVisible(False)
            self.delete_button.setVisible(False)
            self.download_button.setVisible(False)
            self.print_button.setVisible(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont("ui/font/Oxanium-Bold.ttf")
    win = Window()
    #win.show()
    win.showFullScreen()
    sys.exit(app.exec())