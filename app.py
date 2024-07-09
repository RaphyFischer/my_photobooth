import sys, os, time, yaml, json, random
from datetime import datetime
import subprocess
import cv2
from PIL import Image, ImageFont, ImageDraw
import qrcode
import numpy as np
import zc.lockfile
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QTimer, QObject
from PyQt5.QtGui import QImage, QMovie, QPixmap, QIcon, QFontDatabase, QColor
from PyQt5.QtWidgets import QApplication, QMainWindow
from MainWindow import Ui_MainWindow
import share_gdrive
from list_cameras import list_stream_cameras
from settings_button import SettingsButton

# prevent application from running twice
lock = zc.lockfile.LockFile('lock')

# Settings are read from settings.yaml. Adjust them there or in GUI by long pressing the welcome message
SETTINGS = {}

def switch_canon_to_liveview():
    # canon eos m3 goes to picture playback on usb connect and after taking images
    # this function resets it to shooting mode/liveview
    # install chdk on your sd card and run this command gphoto2 --set-config chdk=On
    p =subprocess.Popen(["gphoto2", "--capture-movie", "--stdout"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    time.sleep(0.7)
    p.kill()

class UploadThread(QThread):
    changePixmap = pyqtSignal(QImage)

    def run(self):
        # share file via link
        try:
            file_id = share_gdrive.upload_image(SETTINGS["FILE_NAME"])
            link = share_gdrive.share_image(file_id)
            print(f"Image uploaded to {link}")

            # create qr code for image
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(link)
            qr.make(fit=True)

            img = qr.make_image(fill_color=(247, 244, 183), back_color=(42, 49, 65))
            img = np.array(img.resize((600,600), Image.NEAREST))
            qt_img = QImage(img.data, img.shape[1], img.shape[0], img.shape[1]*img.shape[2], QImage.Format_RGB888)
            self.changePixmap.emit(qt_img)
        except:
            print("Upload failed")

class StreamThread(QThread):
    changePixmap = pyqtSignal(QImage)

    def run(self):
        height, width, channel = 720, 1280, 3
        scale = 1.6
        cropped_width = int(3*height/2)                     #crop black borders of 16:9 monitor
        width_to_crop = width-cropped_width
        scaled_width = int(cropped_width*scale)
        scaled_height = int(height*scale)
        
        cap = cv2.VideoCapture(SETTINGS["CAMERA_INDEX"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 25)

        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            if not SETTINGS["FREEZE_STREAM"]:
                frame = frame[:,int(width_to_crop/2):int(width-(width_to_crop/2)),:].copy()
            elif os.path.isfile(SETTINGS["FILE_NAME"]):
                frame = cv2.imread(SETTINGS["FILE_NAME"])
                # collages are saved "unflipped"! -> Flip twice here
                if "collage" in SETTINGS["FILE_NAME"]:
                    frame = cv2.flip(frame, 1)
            else:
                continue
            frame = cv2.flip(frame, 1)
            rgbImage = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if SETTINGS["COLLAGE_TEMPLATE"] is not None:
                collageImage = SETTINGS["COLLAGE_TEMPLATE"]
                positionInfo = SETTINGS["COLLAGE_POSITIONS"][SETTINGS["COLLAGE_ID"]]
                xcenter, ycenter = positionInfo["position"]
                w, h = positionInfo["size"]
                collageImage[ycenter-int(h/2):ycenter+int(h/2), xcenter-int(w/2):xcenter+int(w/2)] = \
                    cv2.resize(rgbImage, positionInfo["size"], interpolation = cv2.INTER_AREA)
                SETTINGS["COLLAGE_TEMPLATE"] = collageImage
                rgbImage = collageImage

            if SETTINGS["CHALLENGE"] is not None:
                chal = SETTINGS["CHALLENGE"]
                pil_image = Image.fromarray(rgbImage)
                draw = ImageDraw.Draw(pil_image, "RGBA")

                font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), "ui/font/Oxanium-Bold.ttf"), 30)
                position = (int(cropped_width/2), 90)
                if " - "in chal:
                    title, text = chal.split(" - ")
                else:
                    title, text = "", chal
                text = f"Deine Challenge: {title} -\n{text}"

                left, top, right, bottom = draw.textbbox(position, text, font=font, anchor="mm")
                draw.rectangle((left-5, top-25, right+5, bottom+5), fill=(0,0,0,127))
                draw.text(position, text, font=font, fill=(247, 244, 183, 255), anchor="mm")

                # Convert back to Numpy array and switch back from RGB to BGR
                rgbImage = np.asarray(pil_image)

            rgbImage_resized = cv2.resize(rgbImage, (scaled_width, scaled_height), interpolation = cv2.INTER_AREA)
            convertToQtFormat = QImage(rgbImage_resized.data, scaled_width, scaled_height, channel*scaled_width, QImage.Format_RGB888)
            self.changePixmap.emit(convertToQtFormat)

class CaptureWorker(QObject):
    progress = pyqtSignal(int)

    @pyqtSlot()
    def run(self):
        global SETTINGS

        print("Countdown started")
        subprocess.Popen(["gphoto2", "--reset"])
        for secs_left in range(SETTINGS["COUNTDOWN_TIME_SECONDS"], 1, -1):
            self.progress.emit(secs_left)
            time.sleep(1)

        print('Capturing image')
        SETTINGS["FILE_NAME"] = os.path.join(SETTINGS["TARGET_DIR"], "photobox_%s.jpg" %datetime.now().strftime("%m%d%Y_%H%M%S"))
        if SETTINGS["CHALLENGE"] is not None:
            SETTINGS["FILE_NAME"] = os.path.join(SETTINGS["TARGET_DIR"], "challenge_%s_%s.jpg" %(SETTINGS["CHALLENGE"][:25], datetime.now().strftime("%m%d%Y_%H%M%S")))

        #gphoto2 --filename data/test/photobox_\%m\%d\%Y_\%H\%M\%S.jpg --capture-image-and-download
        subprocess.Popen(["gphoto2", "--set-config", "chdk=On", "--filename", SETTINGS["FILE_NAME"], "--capture-image-and-download", "--force-overwrite", "--keep"])
        
        # send 0 for "click"
        self.progress.emit(1)
        time.sleep(1)
        self.progress.emit(0)
        SETTINGS["FREEZE_STREAM"] = True
        
        # wait for image to transfer from camera to device
        while not os.path.isfile(SETTINGS["FILE_NAME"]):
            time.sleep(0.2)

        # and -1 for shutter icon
        self.progress.emit(-1)
        
        print('Showing preview')
        preview_countdown = SETTINGS["PREVIEW_TIME_SECONDS"]
        while preview_countdown > 0 and SETTINGS["FREEZE_STREAM"]:
            time.sleep(0.2)
            preview_countdown -= 0.2
        switch_canon_to_liveview()
        SETTINGS["FREEZE_STREAM"] = False
        self.progress.emit(-2)

class Window(QMainWindow, Ui_MainWindow):
    work_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.loadSettings()
        self.setupUi(self)
        self.loadBackgroundImage()
        self.loadCollageImages()
        self.refreshWelcomeText()
        self.setRecaptureMode()
        self.overlay_buttons_on_stream()
        self.hidden_settings = SettingsButton(self.welcome_message)
        self.collage_button.setVisible(SETTINGS["SHOW_COLLAGE"])
        self.challenge_button.setVisible(SETTINGS["SHOW_CHALLENGE"])

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refreshWelcomeText)
        self.timer.start()

        self.hidden_settings.longclicked.connect(self.settingsClicked)
        self.start_button.clicked.connect(self.startButtonClicked)
        self.collage_button.clicked.connect(self.collageButtonClicked)
        self.challenge_button.clicked.connect(self.challengeButtonClicked)
        self.home_button.clicked.connect(self.homeButtonClicked)
        self.delete_button.clicked.connect(self.deleteButtonClicked)
        self.capture_button.clicked.connect(self.captureButtonClicked)
        self.download_button.clicked.connect(self.downloadButtonClicked)
        self.print_button.clicked.connect(self.printButtonClicked)
        self.back_button.clicked.connect(self.homeButtonClicked)
        self.save_setting_button.clicked.connect(self.saveSettings)
        self.shutdown_button.clicked.connect(self.shutdown)
        self.open_button.clicked.connect(self.openFileDialog)
        self.templateListWidget.itemClicked.connect(self.templateSelected)

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
        if SETTINGS["SHOW_SHARE"]:
            share_gdrive.get_credentials()

    def loadBackgroundImage(self):
        style = "QWidget#start_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %SETTINGS["BACKGROUND_IMAGE"]
        self.start_page.setStyleSheet(style)
        style = "QWidget#photo_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %SETTINGS["BACKGROUND_IMAGE"]
        self.photo_page.setStyleSheet(style)
        style = "QWidget#download_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %SETTINGS["BACKGROUND_IMAGE"]
        self.download_page.setStyleSheet(style)
        style = "QWidget#setup_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %SETTINGS["BACKGROUND_IMAGE"]
        self.setup_page.setStyleSheet(style)
        style = "QWidget#collage_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %SETTINGS["BACKGROUND_IMAGE"]
        self.collage_page.setStyleSheet(style)

    def loadCollageImages(self):
        self.templateListWidget.clear()

        # read images from collage directory
        dir_path = os.path.dirname(os.path.realpath(__file__))
        collages_path = os.path.join(dir_path, "ui", "collages")
        files = os.listdir(collages_path)
        for f in files:
            if f.endswith(".png"):
                item = QtWidgets.QListWidgetItem()
                item.setText(f[:-4])
                item.setForeground(QColor(247, 244, 183))
                icon = QIcon()
                icon.addPixmap(QPixmap(os.path.join(collages_path, f)), QIcon.Normal, QIcon.Off)
                item.setIcon(icon)
                self.templateListWidget.addItem(item)
        self.templateListWidget.setIconSize(QtCore.QSize(540, 360))

    def refreshWelcomeText(self):
        message_and_time = datetime.now().strftime("%A %d. %b %Y   %H:%M")+"\n"+SETTINGS["WELCOME_MESSAGE"]
        self.welcome_message.setText(message_and_time)
        self.welcome_message.setStyleSheet(f"color: {SETTINGS['WELCOME_TEXT_COLOR']};")
        self.stream.setStyleSheet(f"border: 5px solid {SETTINGS['IMAGE_BORDER_COLOR']};")

    def setRecaptureMode(self):
        # if recapture is activated show home button in photo view else show save button
        icon = QIcon()
        if SETTINGS["SHOW_RECAPTURE"]:icon.addPixmap(QPixmap(":/files/icons/home.png"), QIcon.Normal, QIcon.Off)
        else: icon.addPixmap(QPixmap(":/files/icons/save.png"), QIcon.Normal, QIcon.Off)
        self.home_button.setIcon(icon)

    def overlay_buttons_on_stream(self):
        spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        spacer_vert = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.photo_page_grid.addItem(spacer, 0, 0, 0, 1)                                # used to reduce the gap between border and image. Vertical is not working so adjust bottom margin of photo_page
        self.photo_page_grid.addWidget(self.stream, 0, 1,0,1)
        self.photo_page_grid.addItem(spacer, 0, 2, 0, 1)
        self.photo_page_grid.addLayout(self.photo_page_buttons, 4, 0, 1, 1)

        if SETTINGS["SHOW_BUTTON_TEXT"]:
            self.home_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.delete_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.download_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.print_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)

    def showImageControlButtons(self, visible):
        if visible:                                                     # icon menue is visible
            self.home_button.setVisible(True)
            self.delete_button.setVisible(SETTINGS["SHOW_DELETE"])
            self.capture_button.setVisible(SETTINGS["SHOW_RECAPTURE"])
            self.download_button.setVisible(SETTINGS["SHOW_SHARE"])
            self.print_button.setVisible(SETTINGS["SHOW_PRINT"])
            self.capture_button.setEnabled(True)
        else:                                                           # capture countdown is running
            self.capture_button.setVisible(True)
            self.home_button.setVisible(False)
            self.delete_button.setVisible(False)
            self.download_button.setVisible(False)
            self.print_button.setVisible(False)
            self.capture_button.setEnabled(False)
        self.show()

    @pyqtSlot(QImage)
    def setImage(self, image):
        self.stream.setPixmap(QPixmap.fromImage(image))

    def startButtonClicked(self):
        print("Start Button pressed")
        switch_canon_to_liveview()
        self.showImageControlButtons(False)
        self.stackedWidget.setCurrentIndex(1)
        self.captureButtonClicked()

    def collageButtonClicked(self):
        print("Start Collage clicked")
        self.stackedWidget.setCurrentIndex(4)

    def challengeButtonClicked(self):
        print("Start Challenge clicked")
        switch_canon_to_liveview()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        challenges_path = os.path.join(dir_path, "challenges.txt")
        with open(challenges_path) as f:
            lines = f.readlines()
        SETTINGS["CHALLENGE"] = random.choice(lines)

        self.showImageControlButtons(False)
        self.capture_button.setEnabled(True)
        self.stackedWidget.setCurrentIndex(1)

    def templateSelected(self):
        global SETTINGS
        print("Template was selected")
        switch_canon_to_liveview()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        template_path = os.path.join(dir_path, "ui","collages",self.templateListWidget.selectedItems()[0].text())
        with open(template_path+"_positions.json") as f:
            collage_dict = json.load(f)
            template = cv2.imread(os.path.join(dir_path, "ui","collages", collage_dict["filename"]))
            template = cv2.cvtColor(template, cv2.COLOR_BGR2RGB)
            SETTINGS["COLLAGE_TEMPLATE"] = template
            SETTINGS["COLLAGE_POSITIONS"] = collage_dict["images"]
        SETTINGS["COLLAGE_ID"] = 0
        self.original_preview_time = SETTINGS["PREVIEW_TIME_SECONDS"]
        SETTINGS["PREVIEW_TIME_SECONDS"] = 1                                   # only short preview during collag

        self.showImageControlButtons(False)
        self.capture_button.setEnabled(True)
        self.stackedWidget.setCurrentIndex(1)

    def captureButtonClicked(self):
        global SETTINGS
        SETTINGS["FREEZE_STREAM"] = False                                       # stops the preview
        self.showImageControlButtons(False)
        self.work_requested.emit()

    def updateCountdown(self, secs_left):
        global SETTINGS
        if secs_left > 0:
            file = os.path.join(os.path.dirname(__file__), SETTINGS["COUNTDOWN_SOUND"])
            subprocess.Popen(["aplay", file])
            self.capture_button.setIcon(QIcon())
            self.capture_button.setText(str(secs_left))
            self.stream.setStyleSheet(f"border: 5px solid white")               # blinking border
        elif secs_left == 0:                                                    # at capture
            self.capture_button.setText("Click")
        elif secs_left == -1:                                                     # after capture
            self.capture_button.setText("")
            self.capture_button.setIcon(QIcon(":/files/icons/aperature.png"))
            if SETTINGS["COLLAGE_ID"] is None:
                self.showImageControlButtons(True)
        elif secs_left == -2:                                                 # after preview
            if SETTINGS["SHOW_RECAPTURE"] == False:
                self.stackedWidget.setCurrentIndex(0)
            if SETTINGS["COLLAGE_ID"] is not None and \
                SETTINGS["COLLAGE_ID"]+1 < len(SETTINGS["COLLAGE_POSITIONS"]):
                SETTINGS["COLLAGE_ID"] += 1
                time.sleep(2)
                switch_canon_to_liveview()
                self.showImageControlButtons(False)
                self.capture_button.setEnabled(True)
            elif SETTINGS["COLLAGE_ID"] is not None and \
                SETTINGS["COLLAGE_ID"]+1 == len(SETTINGS["COLLAGE_POSITIONS"]):
                SETTINGS["FREEZE_STREAM"] = True
                self.showImageControlButtons(True)
                self.capture_button.setEnabled(False)
                SETTINGS["FILE_NAME"] = os.path.join(SETTINGS["TARGET_DIR"], "collage_%s.jpg" %datetime.now().strftime("%m%d%Y_%H%M%S"))
                collage = SETTINGS["COLLAGE_TEMPLATE"]
                collage = cv2.cvtColor(collage, cv2.COLOR_BGR2RGB)
                cv2.imwrite(SETTINGS["FILE_NAME"], collage)
                SETTINGS["PREVIEW_TIME_SECONDS"] = self.original_preview_time
                SETTINGS["COLLAGE_TEMPLATE"] = None
                print("Collage Finished")


    def homeButtonClicked(self):
        print("Home Button pressed")
        SETTINGS["FREEZE_STREAM"] = False                                       # stops eventually running preview countdown
        SETTINGS["CHALLENGE"] = None
        SETTINGS["COLLAGE_ID"] = None

        self.stackedWidget.setCurrentIndex(0)
    
    def deleteButtonClicked(self):
        print("Delete last Photo")
        try:
            os.remove(SETTINGS["FILE_NAME"])
        except FileNotFoundError:
            pass
        self.homeButtonClicked()

    def printButtonClicked(self):
        # use CUPS+Gutenprint to print Image via Selpy CP400
        print("Printing photo")
        subprocess.Popen(["lpr", "-P", SETTINGS["PRINTER_NAME"], SETTINGS["FILE_NAME"]])

    @pyqtSlot(QImage)
    def insertQRCode(self, image):
        self.qr_code.setPixmap(QPixmap.fromImage(image))
        self.instructions.setText("Bitte QR-Code scannen")

    def downloadButtonClicked(self):
        print("Switch to download site")
        self.stackedWidget.setCurrentIndex(2)
        
        # set loading spinner
        self.instructions.setText("Download wird vorbereitet...\nBitte warten")
        self.qr_code.clear()
        #movie = QMovie("ui/icons/spinner.gif")
        #self.qr_code.setMovie(movie)
        #movie.start()

        th = UploadThread(self)
        th.changePixmap.connect(self.insertQRCode)
        th.start()

    def settingsClicked(self):
        print("Go to settings")
        # init settings view with current values
        self.lineEdit_welcome_message.setText(SETTINGS["WELCOME_MESSAGE"])
        self.lineEdit_target_dir.setText(SETTINGS["TARGET_DIR"])
        self.spinBox_countdown_time.setValue(SETTINGS["COUNTDOWN_TIME_SECONDS"])
        self.spinBox_preview_time.setValue(SETTINGS["PREVIEW_TIME_SECONDS"])
        self.checkBox_collage.setChecked(SETTINGS["SHOW_COLLAGE"])
        self.checkBox_filter.setChecked(SETTINGS["SHOW_CHALLENGE"])
        self.checkBox_delete.setChecked(SETTINGS["SHOW_DELETE"])
        self.checkBox_recapture.setChecked(SETTINGS["SHOW_RECAPTURE"])
        self.checkBox_print.setChecked(SETTINGS["SHOW_PRINT"])
        self.checkBox_share.setChecked(SETTINGS["SHOW_SHARE"])
        self.checkBox_button_text.setChecked(SETTINGS["SHOW_BUTTON_TEXT"])
        self.stackedWidget.setCurrentIndex(3)

    def openFileDialog(self):
        folderpath = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select Folder')
        if folderpath:
            self.lineEdit_target_dir.setText(folderpath)        

    def loadSettings(self):
        # load the settings from yaml to globals to use them as variables
        global SETTINGS

        with open(os.path.join(os.path.dirname(__file__), "settings.yaml"), "r") as stream:
            try:
                SETTINGS = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)

        # init some variables
        SETTINGS["FILE_NAME"] = ""                          # holds last filename
        SETTINGS["FREEZE_STREAM"] = False
        SETTINGS["COLLAGE_TEMPLATE"] = None
        SETTINGS["COLLAGE_ID"] = None
        SETTINGS["CHALLENGE"] = None

        # create the target dir if necessary
        try:
            os.makedirs(SETTINGS["TARGET_DIR"],exist_ok=True)
        except PermissionError:
            print(f"Couldn't create {SETTINGS['TARGET_DIR']}")
            SETTINGS["TARGET_DIR"] = "photobox/images"
            os.makedirs(SETTINGS["TARGET_DIR"],exist_ok=True)
            print(f"Using {SETTINGS['TARGET_DIR']} instead")

    def saveSettings(self):
        global SETTINGS

        SETTINGS["WELCOME_MESSAGE"] = self.lineEdit_welcome_message.text()
        SETTINGS["TARGET_DIR"] = self.lineEdit_target_dir.text()
        SETTINGS["COUNTDOWN_TIME_SECONDS"] = self.spinBox_countdown_time.value()
        SETTINGS["PREVIEW_TIME_SECONDS"] = self.spinBox_preview_time.value()
        SETTINGS["SHOW_COLLAGE"] = self.checkBox_collage.isChecked()
        SETTINGS["SHOW_CHALLENGE"] = self.checkBox_filter.isChecked()
        SETTINGS["SHOW_DELETE"] = self.checkBox_delete.isChecked()
        SETTINGS["SHOW_RECAPTURE"] = self.checkBox_recapture.isChecked()
        SETTINGS["SHOW_PRINT"] = self.checkBox_print.isChecked()
        SETTINGS["SHOW_SHARE"] = self.checkBox_share.isChecked()
        SETTINGS["SHOW_BUTTON_TEXT"] = self.checkBox_button_text.isChecked()

        with open(os.path.join(os.path.dirname(__file__), "settings.yaml"), "w") as outfile:
            try:
                yaml.dump(SETTINGS, outfile, default_flow_style=False)
            except yaml.YAMLError as exc:
                print(exc)

        self.loadSettings()
        self.loadBackgroundImage()
        self.refreshWelcomeText()
        self.setRecaptureMode()
        self.overlay_buttons_on_stream()
        self.collage_button.setVisible(SETTINGS["SHOW_COLLAGE"])
        self.challenge_button.setVisible(SETTINGS["SHOW_CHALLENGE"])
        self.stackedWidget.setCurrentIndex(0)

    def shutdown(self):
        print("Goodbye. See you next time.")
        QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont(os.path.join(os.path.dirname(__file__), "ui/font/Oxanium-Bold.ttf"))
    win = Window()
    #win.resize(1920, 1200)
    #win.show()
    win.showFullScreen()
    sys.exit(app.exec())