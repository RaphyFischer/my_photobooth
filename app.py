import asyncio
import logging
import sys, os, time, yaml, json, random
from datetime import datetime
import subprocess
from captureworker import CaptureWorker
import cv2
from PIL import Image, ImageFont, ImageDraw
import qrcode
import numpy as np
import zc.lockfile
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QImage, QPixmap, QIcon, QFontDatabase, QColor
from PyQt6.QtWidgets import QApplication, QMainWindow
from MainWindow import Ui_MainWindow
from cameraInitializer import CameraInitializer
import share_gdrive
from list_cameras import list_stream_cameras
from settings_button import SettingsButton
import globals
import resources_rc

# prevent application from running twice
lock = zc.lockfile.LockFile('lock')

def switch_canon_to_liveview():
    # only do this if we use a Canon M3
    if globals.CURRENT_CAMERA is not None and "Canon" in globals.CURRENT_CAMERA and "M3" in globals.CURRENT_CAMERA:
        # canon eos m3 goes to picture playback on usb connect and after taking images
        # this function resets it to shooting mode/liveview
        # install chdk on your sd card and run this command gphoto2 --set-config chdk=On
        p =subprocess.Popen(["gphoto2", "--capture-movie", "--stdout"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        p.communicate()
        time.sleep(0.1)
        p.kill()

class UploadThread(QThread):
    changePixmap = pyqtSignal(QImage)

    def run(self):
        # share file via link
        try:
            file_id = share_gdrive.upload_image(globals.FILE_NAME)
            link = share_gdrive.share_image(file_id)
            logging.info(f"Image uploaded to {link}")

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
            qt_img = QImage(img.data, img.shape[1], img.shape[0], img.shape[1]*img.shape[2], QImage.Format.Format_RGB888)
            self.changePixmap.emit(qt_img)
        except:
            logging.error("Upload failed")

class StreamThread(QThread):
    changePixmap = pyqtSignal(QImage)

    def run(self):
        #height, width, channel = 720, 1280, 3
        height, width, channel = 525, 840, 3
        scale = 1.6
        cropped_width = int(3*height/2)                     #crop black borders of 16:9 monitor
        width_to_crop = width-cropped_width
        scaled_width = int(cropped_width*scale)
        scaled_height = int(height*scale)
        
        cap = cv2.VideoCapture(globals.SETTINGS["CAMERA_INDEX"])
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 25)

        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            if not globals.FREEZE_STREAM:
                frame = frame[:,int(width_to_crop/2):int(width-(width_to_crop/2)),:].copy()
            elif os.path.isfile(globals.FILE_NAME):
                frame = cv2.imread(globals.FILE_NAME)
                # collages are saved "unflipped"! -> Flip twice here
                # if "collage" in globals.FILE_NAME:
                #     frame = cv2.flip(frame, 1)
            else:
                continue
            
            frame = cv2.flip(frame, 1)
            rgbImage = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgbImage_resized = cv2.resize(rgbImage, (scaled_width, scaled_height), interpolation = cv2.INTER_AREA)
            convertToQtFormat = QImage(rgbImage_resized.data, scaled_width, scaled_height, channel*scaled_width, QImage.Format.Format_RGB888)
            self.changePixmap.emit(convertToQtFormat)


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

        self.start_button.setVisible(False)
        self.collage_button.setVisible(False)

        # Start camera initialization
        initCameraThread = CameraInitializer(self)
        initCameraThread.enable_buttons_signal.connect(self.enableStartButtons)
        initCameraThread.start()

        self.hidden_settings = SettingsButton(self.welcome_message)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refreshWelcomeText)
        self.timer.start()

        self.hidden_settings.longclicked.connect(self.settingsClicked)
        self.start_button.clicked.connect(self.startButtonClicked)
        self.collage_button.clicked.connect(self.collageButtonClicked)
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
        self.worker.capture_finished.connect(self.capture_finished)
        self.worker.preview_finished.connect(self.on_preview_finished)
        self.worker.capture_error.connect(self.capture_error)
        self.work_requested.connect(self.worker.run)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.start()

        # start streaming thread
        th = StreamThread(self)
        th.changePixmap.connect(self.setImage)
        th.start()

        # start web server hosting images
        if globals.SETTINGS["SHOW_SHARE"]:
            share_gdrive.get_credentials()

    def loadBackgroundImage(self):
        style = "QWidget#start_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %globals.SETTINGS["BACKGROUND_IMAGE"]
        self.start_page.setStyleSheet(style)
        style = "QWidget#photo_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %globals.SETTINGS["BACKGROUND_IMAGE"]
        self.photo_page.setStyleSheet(style)
        style = "QWidget#download_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %globals.SETTINGS["BACKGROUND_IMAGE"]
        self.download_page.setStyleSheet(style)
        style = "QWidget#setup_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %globals.SETTINGS["BACKGROUND_IMAGE"]
        self.setup_page.setStyleSheet(style)
        style = "QWidget#collage_page{border-image: url(:/files/%s) 0 0 0 0 stretch stretch;}" %globals.SETTINGS["BACKGROUND_IMAGE"]
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
                icon.addPixmap(QPixmap(os.path.join(collages_path, f)), QIcon.Mode.Normal, QIcon.State.Off)
                item.setIcon(icon)
                self.templateListWidget.addItem(item)
        self.templateListWidget.setIconSize(QtCore.QSize(540, 360))

    def refreshWelcomeText(self):
        message_and_time = datetime.now().strftime("%A %d. %b %Y   %H:%M")+"\n"+globals.SETTINGS["WELCOME_MESSAGE"]
        self.welcome_message.setText(message_and_time)
        self.welcome_message.setStyleSheet(f"color: {globals.SETTINGS['WELCOME_TEXT_COLOR']};")
        self.stream.setStyleSheet(f"border: 5px solid {globals.SETTINGS['IMAGE_BORDER_COLOR']};")

    def setRecaptureMode(self):
        # if recapture is activated show home button in photo view else show save button
        icon = QIcon()
        if globals.SETTINGS["SHOW_RECAPTURE"]:icon.addPixmap(QPixmap(":/files/icons/home.png"), QIcon.Mode.Normal, QIcon.State.Off)
        else: icon.addPixmap(QPixmap(":/files/icons/save.png"), QIcon.Mode.Normal, QIcon.State.Off)
        self.home_button.setIcon(icon)

    def overlay_buttons_on_stream(self):
        spacer = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        spacer_vert = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.photo_page_grid.addItem(spacer, 0, 0, 0, 1)                                # used to reduce the gap between border and image. Vertical is not working so adjust bottom margin of photo_page
        self.photo_page_grid.addWidget(self.stream, 0, 1,0,1)
        self.photo_page_grid.addItem(spacer, 0, 2, 0, 1)
        self.photo_page_grid.addLayout(self.photo_page_buttons, 4, 0, 1, 1)

        if globals.SETTINGS["SHOW_BUTTON_TEXT"]:
            self.home_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.delete_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.download_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
            self.print_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)

    def showImageControlButtons(self, visible):
        if visible:                          
            self.home_button.setVisible(True)
            self.delete_button.setVisible(globals.SETTINGS["SHOW_DELETE"])
            self.capture_button.setVisible(globals.SETTINGS["SHOW_RECAPTURE"])
            self.download_button.setVisible(globals.SETTINGS["SHOW_SHARE"])
            self.print_button.setVisible(globals.SETTINGS["SHOW_PRINT"])
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

    def capture_error(self, error):
        logging.error(f"Error during image capture process. Returning to home screen. Error: {error}")
        self.homeButtonClicked()

    def startButtonClicked(self):
        logging.info("Start Button pressed")
        globals.CAPTURE_MODE = globals.CaptureMode.SINGLE
        globals.CURRENT_COLLAGE = None
        switch_canon_to_liveview()
        self.showImageControlButtons(False)
        self.stackedWidget.setCurrentIndex(1)
        self.capture_button.setEnabled(True)
        self.capture_button.setVisible(True)

    def collageButtonClicked(self):
        logging.info("Start Collage clicked")
        globals.CAPTURE_MODE = globals.CaptureMode.COLLAGE
        globals.CURRENT_COLLAGE = globals.Collage("collage_3_by_2.png", [
            globals.ImagePosition(1, globals.Coordinates(60, 118), 5, 583, globals.Size(505, 360)),
            globals.ImagePosition(2, globals.Coordinates(60, 525), 356, 583, globals.Size(500, 350)),
            globals.ImagePosition(3, globals.Coordinates(60, 922), 5, 583, globals.Size(505, 360)),
        ])
        self.showImageControlButtons(False)
        self.stackedWidget.setCurrentIndex(1)
        self.capture_button.setEnabled(True)
        self.capture_button.setVisible(True)

    def templateSelected(self):
        logging.info("Template was selected")
        switch_canon_to_liveview()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        template_path = os.path.join(dir_path, "ui","collages",self.templateListWidget.selectedItems()[0].text())
        with open(template_path+"_positions.json") as f:
            collage_dict = json.load(f)
            template = cv2.imread(os.path.join(dir_path, "ui","collages", collage_dict["filename"]))
            template = cv2.cvtColor(template, cv2.COLOR_BGR2RGB)
            globals.SETTINGS["COLLAGE_TEMPLATE"] = template
            globals.SETTINGS["COLLAGE_POSITIONS"] = collage_dict["images"]
        globals.SETTINGS["COLLAGE_ID"] = 0
        self.original_preview_time = globals.SETTINGS["PREVIEW_TIME_SECONDS"]
        globals.SETTINGS["PREVIEW_TIME_SECONDS"] = 1                                   # only short preview during collag

        self.showImageControlButtons(False)
        self.capture_button.setEnabled(True)
        self.stackedWidget.setCurrentIndex(1)

    def captureButtonClicked(self):
        globals.FREEZE_STREAM = False                                       # stops the preview
        self.showImageControlButtons(False)
        self.work_requested.emit()

    def updateCountdown(self, secs_left):
        logging.info(f"Countdown: {secs_left}")
        if secs_left > 0:
            logging.info(f"More than 0 seconds left playing back sound")
            file = os.path.join(os.path.dirname(__file__), globals.SETTINGS["COUNTDOWN_SOUND"])
            # not working on macos
            #subprocess.Popen(["aplay", file])
            self.capture_button.setIcon(QIcon())
            self.capture_button.setText(str(secs_left))
            self.stream.setStyleSheet(f"border: 5px solid white")               # blinking border
        elif secs_left == 0:                                                    # at capture
            logging.info("Countdown finished")
            self.capture_button.setText("Click")
        
    def capture_finished(self):
        logging.info("Countdown at -1 resetting capture button?")                                                     # after capture
        self.capture_button.setText("")
        self.capture_button.setIcon(QIcon(":/files/icons/aperature.png"))
        logging.info(f"Current Capture Mode: {globals.CAPTURE_MODE}")
        if globals.CAPTURE_MODE is not None and globals.CAPTURE_MODE is globals.CaptureMode.COLLAGE:
            logging.info("Collage Image Captured")
            # Set the image path of the current image in the collage at the correct position
            globals.CURRENT_COLLAGE.images[globals.CURRENT_COLLAGE.currentImage].imagePath = globals.FILE_NAME
            
            # in case this was the last photo of the collage we need to save the collage
            if globals.CURRENT_COLLAGE.currentImage == len(globals.CURRENT_COLLAGE.images) - 1:
                globals.FREEZE_STREAM = True
                self.showImageControlButtons(True)
                self.capture_button.setEnabled(False)
                self.renderImagesToCollage(globals.CURRENT_COLLAGE)
                #globals.SETTINGS["PREVIEW_TIME_SECONDS"] = self.original_preview_time
                logging.info("Collage Finished")
            else:
                globals.CURRENT_COLLAGE.currentImage += 1
                time.sleep(2)
                switch_canon_to_liveview()
                self.showImageControlButtons(False)
                self.capture_button.setEnabled(True)
        else:
            logging.info("Single Image Captured showing control buttons")
            self.showImageControlButtons(True)
            
            
            
    def on_preview_finished(self):
        if globals.CAPTURE_MODE is not None and globals.CAPTURE_MODE is globals.CaptureMode.SINGLE and globals.SETTINGS["SHOW_RECAPTURE"] == False:
            globals.CAPTURE_MODE = None
            self.stackedWidget.setCurrentIndex(0)
        if globals.CAPTURE_MODE is not None and globals.CAPTURE_MODE is globals.CaptureMode.COLLAGE:
            logging.info("Collage Image finished how to preview this?")
        else:
            logging.info("Single Image Captured")
            self.showImageControlButtons(True)
            globals.CAPTURE_MODE = None
            self.homeButtonClicked()
            
           
    def renderImagesToCollage(self, collage: globals.Collage):
        renderer = globals.CollageRenderer()
        globals.FILE_NAME = os.path.join(globals.SETTINGS["TARGET_DIR"], "collage_%s.jpg" %datetime.now().strftime("%m%d%Y_%H%M%S"))
        renderer.renderImagesToCollage(collage, globals.FILE_NAME)
        #load the collage template
        # collage_template = cv2.imread(os.path.join(os.path.dirname(__file__), "ui", "collages", collage.name))
        # collage_template = cv2.cvtColor(collage_template, cv2.COLOR_BGR2RGB)
        
        # # render the images to the collage
        # for imagePosition in collage.images:
        #     image = cv2.imread(imagePosition.imagePath)
        #     image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        #     image = cv2.resize(image, (imagePosition.size.width, imagePosition.size.height ), interpolation = cv2.INTER_AREA)
        #     ycenter = imagePosition.position.y
        #     xcenter = imagePosition.position.x
        #     width = imagePosition.size.width
        #     height = imagePosition.size.height
        #     # now render the image to the template at the correct position with th ecorrect size
        #     collage_template[ycenter-int(height/2):ycenter+int(height/2), xcenter-int(width/2):xcenter+int(width/2)] = image
            
            
        # globals.FILE_NAME = os.path.join(globals.SETTINGS["TARGET_DIR"], "collage_%s.jpg" %datetime.now().strftime("%m%d%Y_%H%M%S"))
        # collage_template = cv2.cvtColor(collage_template, cv2.COLOR_BGR2RGB)
        # cv2.imwrite(globals.FILE_NAME, collage_template)

    def homeButtonClicked(self):
        logging.info("Home Button pressed")
        self.worker.cancel_preview_timer()
        globals.FREEZE_STREAM = False                                       # stops eventually running preview countdown
        globals.SETTINGS["COLLAGE_ID"] = None
        globals.CAPTURE_MODE = None

        self.stackedWidget.setCurrentIndex(0)
    
    def deleteButtonClicked(self):
        logging.info("Delete last Photo")
        try:
            os.remove(globals.FILE_NAME)
        except FileNotFoundError:
            pass
        self.homeButtonClicked()

    def printButtonClicked(self):
        logging.info("Printing photo")
        logging.info(f"Current Capture Mode: {globals.CAPTURE_MODE}")
        
        args = ["lpr", "-P", globals.SETTINGS["PRINTER_NAME"]]
        
        if globals.CAPTURE_MODE is not None and globals.CAPTURE_MODE is globals.CaptureMode.COLLAGE:
            # add argument to cut the image to the correct size
            args.append("-o Cutter=2Inch")
        
        args.append(globals.FILE_NAME)
        
        printing = subprocess.Popen(args)
        printing.communicate()
        self.homeButtonClicked()
        

    @pyqtSlot(QImage)
    def insertQRCode(self, image):
        self.qr_code.setPixmap(QPixmap.fromImage(image))
        self.instructions.setText("Bitte QR-Code scannen")

    def downloadButtonClicked(self):
        logging.info("Switch to download site")
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
        logging.info("Go to settings")
        # init settings view with current values
        self.lineEdit_welcome_message.setText(globals.SETTINGS["WELCOME_MESSAGE"])
        self.lineEdit_target_dir.setText(globals.SETTINGS["TARGET_DIR"])
        self.spinBox_countdown_time.setValue(globals.SETTINGS["COUNTDOWN_TIME_SECONDS"])
        self.spinBox_preview_time.setValue(globals.SETTINGS["PREVIEW_TIME_SECONDS"])
        self.checkBox_collage.setChecked(globals.SETTINGS["SHOW_COLLAGE"])
        self.checkBox_delete.setChecked(globals.SETTINGS["SHOW_DELETE"])
        self.checkBox_recapture.setChecked(globals.SETTINGS["SHOW_RECAPTURE"])
        self.checkBox_print.setChecked(globals.SETTINGS["SHOW_PRINT"])
        self.checkBox_share.setChecked(globals.SETTINGS["SHOW_SHARE"])
        self.checkBox_button_text.setChecked(globals.SETTINGS["SHOW_BUTTON_TEXT"])
        self.stackedWidget.setCurrentIndex(3)

    def openFileDialog(self):
        folderpath = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select Folder')
        if folderpath:
            self.lineEdit_target_dir.setText(folderpath)        

    def enableStartButtons(self, value):
        self.start_button.setVisible(value)
        self.start_button.setEnabled(value)
        if globals.SETTINGS["SHOW_COLLAGE"]:
            self.collage_button.setVisible(value)
            self.collage_button.setEnabled(value)

    def fillEmptySettingsWIthDefaults(self):
     # check for empty settings and fill them with defaults according to the initialization of the SETTINGS object
        if "WELCOME_MESSAGE" not in globals.SETTINGS:
            globals.SETTINGS["WELCOME_MESSAGE"] = globals.DEFAULT_WELCOME_MESSAGE
        if "TARGET_DIR" not in globals.SETTINGS:
            globals.SETTINGS["TARGET_DIR"] = globals.DEFAULT_TARGET_DIR
        if "COUNTDOWN_TIME_SECONDS" not in globals.SETTINGS:
            globals.SETTINGS["COUNTDOWN_TIME_SECONDS"] = globals.DEFAULT_COUNTDOWN_TIME_SECONDS
        if "PREVIEW_TIME_SECONDS" not in globals.SETTINGS:
            globals.SETTINGS["PREVIEW_TIME_SECONDS"] = globals.DEFAULT_PREVIEW_TIME_SECONDS
        if "SHOW_COLLAGE" not in globals.SETTINGS:
            globals.SETTINGS["SHOW_COLLAGE"] = globals.DEFAULT_SHOW_COLLAGE
        if "SHOW_DELETE" not in globals.SETTINGS:
            globals.SETTINGS["SHOW_DELETE"] = globals.DEFAULT_SHOW_DELETE
        if "SHOW_RECAPTURE" not in globals.SETTINGS:
            globals.SETTINGS["SHOW_RECAPTURE"] = globals.DEFAULT_SHOW_RECAPTURE
        if "SHOW_PRINT" not in globals.SETTINGS:
            globals.SETTINGS["SHOW_PRINT"] = globals.DEFAULT_SHOW_PRINT
        if "SHOW_SHARE" not in globals.SETTINGS:
            globals.SETTINGS["SHOW_SHARE"] = globals.DEFAULT_SHOW_SHARE
        if "SHOW_BUTTON_TEXT" not in globals.SETTINGS:
            globals.SETTINGS["SHOW_BUTTON_TEXT"] = globals.DEFAULT_SHOW_BUTTON_TEXT
        if "BACKGROUND_IMAGE" not in globals.SETTINGS:
            globals.SETTINGS["BACKGROUND_IMAGE"] = globals.DEFAULT_BACKGROUND_IMAGE
        if "CAMERA_INDEX" not in globals.SETTINGS:
            globals.SETTINGS["CAMERA_INDEX"] = globals.DEFAULT_CAMERA_INDEX
        if "COUNTDOWN_SOUND" not in globals.SETTINGS:
            globals.SETTINGS["COUNTDOWN_SOUND"] = globals.DEFAULT_COUNTDOWN_SOUND
        if "WELCOME_TEXT_COLOR" not in globals.SETTINGS:
            globals.SETTINGS["WELCOME_TEXT_COLOR"] = globals.DEFAULT_WELCOME_TEXT_COLOR
        if "IMAGE_BORDER_COLOR" not in globals.SETTINGS:
            globals.SETTINGS["IMAGE_BORDER_COLOR"] = globals.DEFAULT_IMAGE_BORDER_COLOR

    def show_loading_spinner(self):
        self.loading_label.show()
        self.loading_movie.start()

    def hide_loading_spinner(self):
        self.loading_movie.stop()
        self.loading_label.hide()


    def loadSettings(self):
        # load the settings from yaml to globals to use them as variables
        wasEmptyFile = False

        # check if settings file exists
        if not os.path.isfile(os.path.join(os.path.dirname(__file__), "settings.yaml")):
            logging.info("No settings file found. Creating default settings.")
            with open(os.path.join(os.path.dirname(__file__), "settings.yaml"), "w") as outfile:
                try:
                    # fill SETTINGS with default values
                    yaml.dump(globals.SETTINGS, outfile, default_flow_style=False)
                except yaml.YAMLError as exc:
                    logging.error(exc)

        with open(os.path.join(os.path.dirname(__file__), "settings.yaml"), "r") as stream:
            try:
                globals.SETTINGS = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                logging.error(exc)

        # in case of an empty settings file the SETTINGS object will be None
        # Initialization of the values is done in fillEmptySettingsWIthDefaults
        if globals.SETTINGS is None:
            wasEmptyFile = True
            globals.SETTINGS = {}

        self.fillEmptySettingsWIthDefaults()

        # if the settings file was empty we need to write the default values to the file
        if wasEmptyFile:
            with open(os.path.join(os.path.dirname(__file__), "settings.yaml"), "w") as outfile:
                try:
                    yaml.dump(globals.SETTINGS, outfile, default_flow_style=False)
                except yaml.YAMLError as exc:
                    logging.error(exc)

        # init some variables
        globals.SETTINGS["COLLAGE_TEMPLATE"] = None
        globals.SETTINGS["COLLAGE_ID"] = None

        # create the target dir if necessary
        try:
            os.makedirs(globals.SETTINGS["TARGET_DIR"],exist_ok=True)
        except PermissionError:
            logging.error(f"Couldn't create {globals.SETTINGS['TARGET_DIR']}")
            globals.SETTINGS["TARGET_DIR"] = globals.DEFAULT_TARGET_DIR
            os.makedirs(globals.SETTINGS["TARGET_DIR"],exist_ok=True)
            logging.error(f"Using {globals.SETTINGS['TARGET_DIR']} instead")

    def saveSettings(self):
        global SETTINGS

        globals.SETTINGS["WELCOME_MESSAGE"] = self.lineEdit_welcome_message.text()
        globals.SETTINGS["TARGET_DIR"] = self.lineEdit_target_dir.text()
        globals.SETTINGS["COUNTDOWN_TIME_SECONDS"] = self.spinBox_countdown_time.value()
        globals.SETTINGS["PREVIEW_TIME_SECONDS"] = self.spinBox_preview_time.value()
        globals.SETTINGS["SHOW_COLLAGE"] = self.checkBox_collage.isChecked()
        globals.SETTINGS["SHOW_DELETE"] = self.checkBox_delete.isChecked()
        globals.SETTINGS["SHOW_RECAPTURE"] = self.checkBox_recapture.isChecked()
        globals.SETTINGS["SHOW_PRINT"] = self.checkBox_print.isChecked()
        globals.SETTINGS["SHOW_SHARE"] = self.checkBox_share.isChecked()
        globals.SETTINGS["SHOW_BUTTON_TEXT"] = self.checkBox_button_text.isChecked()

        with open(os.path.join(os.path.dirname(__file__), "settings.yaml"), "w") as outfile:
            try:
                yaml.dump(SETTINGS, outfile, default_flow_style=False)
            except yaml.YAMLError as exc:
                logging.info(exc)

        self.loadSettings()
        self.loadBackgroundImage()
        self.refreshWelcomeText()
        self.setRecaptureMode()
        self.overlay_buttons_on_stream()
        self.stackedWidget.setCurrentIndex(0)

    def shutdown(self):
        logging.info("Goodbye. See you next time.")
        QApplication.quit()
    

if __name__ == "__main__":
    globals.init()
    logging.basicConfig(filename="photobox.log",
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont(os.path.join(os.path.dirname(__file__), "ui/font/Oxanium-Bold.ttf"))
    win = Window()
    #win.resize(1280, 800)

    # show window in fullscreen if -fullscreen is passed as argument
    if "-fullscreen" in sys.argv:
        win.showFullScreen()
    else:
        win.show()

    sys.exit(app.exec())
